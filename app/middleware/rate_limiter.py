# -*- coding: utf-8 -*-
"""
基于令牌桶算法的限流中间件
支持基于IP的请求速率限制，允许突发流量
"""

import asyncio
import ipaddress
import time
from dataclasses import dataclass
from typing import Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import config
from app.log import get_logger, get_trace_id

logger = get_logger()
LOCALHOST_IPS = {"127.0.0.1", "::1"}


@dataclass
class TokenBucket:
    """令牌桶数据结构"""

    tokens: float
    capacity: float
    refill_rate: float
    last_refill: float


class RateLimiter:
    """基于令牌桶算法的限流器"""

    def __init__(self, rpm: int, burst_size: int):
        self.rpm = rpm
        self.burst_size = burst_size
        self.refill_rate = rpm / 60.0
        self.buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._cleanup_handle = None

    async def start(self):
        if self._cleanup_handle is not None:
            return
        self._cleanup_handle = asyncio.create_task(self._cleanup_task())

    async def close(self):
        if self._cleanup_handle is None:
            return
        self._cleanup_handle.cancel()
        try:
            await self._cleanup_handle
        except asyncio.CancelledError:
            pass
        finally:
            self._cleanup_handle = None

    async def _cleanup_task(self):
        logger.info("✅ ♻️限流清理任务已启动", 信息="限流清理任务已经启动")
        try:
            while True:
                await asyncio.sleep(60)
                now = time.monotonic()
                async with self._lock:
                    keys_to_delete = [
                        key for key, bucket in self.buckets.items()
                        if now - bucket.last_refill > 120
                    ]
                    if keys_to_delete:
                        logger.info(
                            f"♻️限流清理任务➡️清理过期桶➡️数量:{len(keys_to_delete)}➡️IP列表:{keys_to_delete}",
                            信息=f"清理过期令牌桶, 数量: {len(keys_to_delete)}, IP列表: {keys_to_delete}",
                        )
                        for key in keys_to_delete:
                            del self.buckets[key]
        except asyncio.CancelledError:
            logger.info("✅ ♻️限流清理任务已停止", 信息="限流清理任务已停止")
            return

    def _create_bucket(self) -> TokenBucket:
        return TokenBucket(
            tokens=float(self.burst_size),
            capacity=float(self.burst_size),
            refill_rate=self.refill_rate,
            last_refill=time.monotonic(),
        )

    def _update_tokens(self, bucket: TokenBucket) -> None:
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.last_refill = now

    async def check(self, key: str) -> bool:
        async with self._lock:
            if key not in self.buckets:
                self.buckets[key] = self._create_bucket()
                if key not in LOCALHOST_IPS:
                    logger.info(
                        f"🆕IP:{key}➡️创建新令牌桶➡️容量:{self.rpm}➡️突发:{self.burst_size}",
                        IP=key,
                        信息=f"创建新的令牌桶, 容量: {self.rpm}, 突发: {self.burst_size}",
                    )

            bucket = self.buckets[key]
            self._update_tokens(bucket)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                if key not in LOCALHOST_IPS:
                    logger.info(
                        f"🔋限流检查➡️IP:{key}➡️结果:允许➡️令牌:{bucket.tokens:.1f}/{bucket.capacity}",
                        IP=key,
                        信息=f"限流检查通过, 令牌: {bucket.tokens:.1f}/{bucket.capacity}, 速率: {bucket.refill_rate:.2f}/秒",
                    )
                return True

            logger.warning(
                f"🪫限流检查➡️IP:{key}➡️结果:拒绝➡️令牌:{bucket.tokens:.1f}/{bucket.capacity}➡️速率:{bucket.refill_rate:.2f}/秒",
                IP=key,
                信息=f"限流检查拒绝, 令牌: {bucket.tokens:.1f}/{bucket.capacity}, 速率: {bucket.refill_rate:.2f}/秒",
            )
            return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI限流中间件"""

    def __init__(self, app, rate_limiter: RateLimiter | None, enabled: bool = True, trust_proxy: bool = True):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.enabled = enabled
        self.trust_proxy = trust_proxy
        self._runtime_lock = asyncio.Lock()
        self._config_signature: tuple[bool, int, int, bool] | None = None

    async def _sync_runtime_config(self) -> None:
        rate_limit_config = config.get_rate_limit_config()
        signature = (
            rate_limit_config["RATE_LIMIT_ENABLED"],
            rate_limit_config["RATE_LIMIT_RPM"],
            rate_limit_config["RATE_LIMIT_BURST_SIZE"],
            rate_limit_config["RATE_LIMIT_TRUST_PROXY"],
        )
        if signature == self._config_signature:
            return

        async with self._runtime_lock:
            if signature == self._config_signature:
                return

            enabled, rpm, burst_size, trust_proxy = signature
            self.enabled = enabled
            self.trust_proxy = trust_proxy

            if not enabled:
                old_limiter = self.rate_limiter
                self.rate_limiter = None
                self._config_signature = signature
                if old_limiter is not None:
                    await old_limiter.close()
                return

            if self.rate_limiter is None or (
                self.rate_limiter.rpm != rpm or self.rate_limiter.burst_size != burst_size
            ):
                new_limiter = RateLimiter(rpm=rpm, burst_size=burst_size)
                await new_limiter.start()
                old_limiter = self.rate_limiter
                self.rate_limiter = new_limiter
                self._config_signature = signature
                if old_limiter is not None:
                    await old_limiter.close()
                return

            self._config_signature = signature

    def _get_client_ip(self, request: Request) -> str:
        if not self.trust_proxy:
            if request.client and hasattr(request.client, "host") and request.client.host:
                return request.client.host
            return "unknown-client"

        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip and self._is_valid_ip(cf_connecting_ip.strip()):
            return cf_connecting_ip.strip()

        if request.headers.get("CF-IPCountry"):
            forwarded_for = request.headers.get("X-Forwarded-For")
            if forwarded_for:
                first_ip = forwarded_for.split(",")[0].strip()
                if self._is_valid_ip(first_ip):
                    return first_ip

        real_ip = request.headers.get("X-Real-IP")
        if real_ip and self._is_valid_ip(real_ip.strip()):
            return real_ip.strip()

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if self._is_valid_ip(first_ip):
                return first_ip

        if request.client and hasattr(request.client, "host") and request.client.host:
            return request.client.host

        return "unknown-client"

    def _is_valid_ip(self, ip: str) -> bool:
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    async def dispatch(self, request: Request, call_next):
        await self._sync_runtime_config()
        trace_id = get_trace_id()
        request.state.trace_id = trace_id
        client_ip = self._get_client_ip(request)
        request.state.ip = client_ip

        if not self.enabled:
            return await call_next(request)

        if self.rate_limiter is None:
            return await call_next(request)

        if not await self.rate_limiter.check(client_ip):
            logger.warning(
                f"❌限流检查➡️IP:{client_ip},➡️触发限流➡️返回429错误",
                IP=client_ip,
                trace_id=trace_id,
                信息="触发限流",
            )
            return JSONResponse(
                {"detail": "触发限流⚠️频繁请求将会被封锁", "跟踪ID": trace_id},
                status_code=429,
            )

        return await call_next(request)
