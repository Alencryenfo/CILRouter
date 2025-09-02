"""
Anti-Abuse（反滥用）中间件 - 极简实现
功能：按 IP 进行令牌桶限流，支持突发。
接口：保持 RateLimiter 与 AntiAbuseMiddleware 的签名不变，便于在 main 中直接使用。
"""

import time
import asyncio
import secrets
from typing import Dict
from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import ipaddress


@dataclass
class TokenBucket:
    tokens: float
    capacity: float
    refill_rate: float  # tokens per second
    last_refill: float


class RateLimiter:
    def __init__(self, rpm: int, burst_size: int):
        """
        极简令牌桶限流器（进程内长期保留 + 惰性清理）

        Args:
            rpm: 每分钟允许请求数
            burst_size: 突发容量
        """
        self.refill_rate = max(0.0, float(rpm) / 60.0)
        self.capacity = float(max(1, burst_size))
        self.ttl_seconds = 300
        self.sweep_interval = 60
        self.sweep_limit = 200
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._last_sweep = 0.0

    def _get_bucket(self, key: str) -> TokenBucket:
        b = self._buckets.get(key)
        if b is None:
            b = TokenBucket(tokens=self.capacity, capacity=self.capacity,
                            refill_rate=self.refill_rate, last_refill=time.time())
            self._buckets[key] = b
        return b

    @staticmethod
    def _refill(b: TokenBucket) -> None:
        now = time.time()
        elapsed = max(0.0, now - b.last_refill)
        if elapsed:
            b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_rate)
            b.last_refill = now

    async def check(self, key: str) -> bool:
        async with self._lock:
            now = time.time()
            # 惰性清理：按间隔清理过期桶，限制每次处理数量
            if now - self._last_sweep >= self.sweep_interval:
                self._last_sweep = now
                cutoff = now - self.ttl_seconds
                removed = 0
                # 使用 list() 快照避免遍历期间修改字典报错
                for k, b in list(self._buckets.items()):
                    if b.last_refill < cutoff:
                        self._buckets.pop(k, None)
                        removed += 1
                        if removed >= self.sweep_limit:
                            break

            b = self._get_bucket(key)
            self._refill(b)
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            return False


class AntiAbuseMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        rate_limiter: RateLimiter,
        enabled: bool = True,
        trust_proxy: bool = True,
        allow_paths: set[str] | None = None,
        allow_prefixes: tuple[str, ...] = (),
    ):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.enabled = enabled
        self.trust_proxy = trust_proxy
        self.allow_paths = allow_paths or set()
        self.allow_prefixes = allow_prefixes or tuple()

    @staticmethod
    def _is_valid_ip( ip: str) -> bool:
        try:
            ipaddress.ip_address(ip)
            return True
        except Exception:
            return False

    def _get_client_ip(self, request: Request) -> str:
        """按之前逻辑获取客户端 IP（含代理场景）。"""
        # 如果不信任代理，直接使用连接IP
        if not self.trust_proxy:
            if request.client and hasattr(request.client, 'host') and request.client.host:
                return request.client.host
            return "unknown-client"
        # 信任代理的情况下，按优先级获取真实IP
        # 1. CF-Connecting-IP: Cloudflare 提供的原始客户端IP（最可靠）
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip and self._is_valid_ip(cf_connecting_ip.strip()):
            return cf_connecting_ip.strip()
        # 2. CF-IPCountry 存在时，说明经过了 Cloudflare，但没有 CF-Connecting-IP
        # 这种情况下应该检查 X-Forwarded-For（取第一个）
        if request.headers.get("CF-IPCountry"):
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                first_ip = forwarded_for.split(",")[0].strip()
                if self._is_valid_ip(first_ip):
                    return first_ip
        # 3. X-Real-IP: nginx 等反向代理设置的真实IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and self._is_valid_ip(real_ip.strip()):
            return real_ip.strip()
        # 4. X-Forwarded-For: 标准代理头部（取第一个IP）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if self._is_valid_ip(first_ip):
                return first_ip
        # 5. 最后使用连接IP（在没有代理时最可靠）
        if request.client and hasattr(request.client, 'host') and request.client.host:
            return request.client.host
        # 6. 对于无法获取IP的情况，使用统一的限流策略
        return "unknown-client"

    @staticmethod
    def _get_trace_id() -> str:
        """生成一个简单的 Trace ID，用于日志跟踪。
        默认长度为 16，适合日志检索和关联。
        """
        # 去除视觉上不易区分的字符：0, 1, O, I, l, o
        alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
        return "".join(secrets.choice(alphabet) for _ in range(16))

    async def dispatch(self, request: Request, call_next):
        # 路径放行：命中白名单则不做限流
        path = request.url.path
        if (self.allow_paths and path in self.allow_paths) or any(
            path.startswith(p) for p in self.allow_prefixes
        ):
            return await call_next(request)

        request.state.ip = self._get_client_ip(request)
        request.state.trace_id = self._get_trace_id()
        if not self.enabled or not self.rate_limiter:
            return await call_next(request)
        allowed = await self.rate_limiter.check(request.state.ip)
        if not allowed:
            return JSONResponse({"detail": "触发限流"}, status_code=429)
        return await call_next(request)
