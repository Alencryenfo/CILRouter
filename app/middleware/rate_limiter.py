# -*- coding: utf-8 -*-
"""
基于令牌桶算法的限流中间件
支持基于IP的请求速率限制，允许突发流量
"""

import time
import asyncio
from typing import Dict
from dataclasses import dataclass
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import ipaddress
from app.log import setup_logger

logger = setup_logger(log_level="INFO")
@dataclass
class TokenBucket:
    """令牌桶数据结构"""
    tokens: float  # 当前令牌数量
    capacity: float  # 桶容量（最大令牌数）
    refill_rate: float  # 令牌补充速率（每秒）
    last_refill: float  # 上次补充时间


class RateLimiter:
    """基于令牌桶算法的限流器"""

    def __init__(self, rpm: int, burst_size: int):
        """
        初始化限流器
        
        Args:
            rpm: 每分钟允许的请求数
            burst_size: 突发容量（允许短时间内超过平均速率的请求数）
        """
        self.rpm = rpm
        self.burst_size = burst_size
        self.refill_rate = rpm / 60.0  # 每秒补充的令牌数
        self.buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._cleanup_handle = None

    async def start(self):
        self._cleanup_handle = asyncio.create_task(self._cleanup_task())

    async def close(self):
        self._cleanup_handle.cancel()
        try:
            await self._cleanup_handle
        except asyncio.CancelledError:
            pass

    async def _cleanup_task(self):
        """后台每隔 cleanup_interval 秒清理过期桶"""
        logger.info("✅ 限流清理任务已启动")
        try:
            while True:
                await asyncio.sleep(60)
                now = time.time()
                async with self._lock:
                    keys_to_delete = [
                        k for k, b in self.buckets.items()
                        if now - b.last_refill > 120  # 120秒未使用的桶将被清理
                    ]
                    if keys_to_delete:
                        logger.info(f"限流清理任务➡️清理过期桶➡️数量:{len(keys_to_delete)}➡️IP列表:{keys_to_delete}")
                    for k in keys_to_delete:
                        del self.buckets[k]
                    logger.info(f"限流清理任务➡️当前活跃桶数:{len(self.buckets)}")
        except asyncio.CancelledError:
            logger.info("✅ 限流清理任务已停止")
            return

    def _create_bucket(self) -> TokenBucket:
        """创建新的令牌桶"""
        return TokenBucket(
            tokens=float(self.burst_size),
            capacity=float(self.rpm),
            refill_rate=self.refill_rate,
            last_refill=time.time()
        )

    def _update_tokens(self, bucket: TokenBucket) -> None:
        """更新令牌桶"""
        now = time.time()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            # 计算应该补充的令牌数
            tokens_to_add = elapsed * bucket.refill_rate
            bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
            bucket.last_refill = now

    async def check(self, key: str) -> bool:
        """
        检查是否允许请求

        Args:
            key: 限流键（通常是IP地址）
            
        Returns:
            bool: 是否允许请求
        """
        # 首次调用时启动清理任务
        async with self._lock:
            # 首次调用时清理过期的桶
            if key not in self.buckets:
                self.buckets[key] = self._create_bucket()
                logger.info(f"IP:{key}➡️创建新令牌桶➡️容量:{self.rpm}➡️突发:{self.burst_size}")
            bucket = self.buckets[key]
            self._update_tokens(bucket)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                logger.info(f"限流检查➡️IP:{key}➡️结果:允许➡️令牌:{bucket.tokens:.1f}/{bucket.capacity}")
                return True
            else:
                logger.warning(f"限流检查➡️IP:{key}➡️结果:拒绝➡️令牌:{bucket.tokens:.1f}/{bucket.capacity}➡️速率:{bucket.refill_rate:.2f}/秒")
                return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI限流中间件"""

    def __init__(self, app, rate_limiter: RateLimiter, enabled: bool = True, trust_proxy: bool = True):
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.enabled = enabled
        self.trust_proxy = trust_proxy

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址"""
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
        # 这种情况下应该检查 X-Forwarded-For
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

    def _is_valid_ip(self, ip: str) -> bool:
        """验证IP地址格式（支持IPv4和IPv6）"""
        try:
            ipaddress.ip_address(ip)
            return True
        except:
            return False

    async def dispatch(self, request: Request, call_next):
        """中间件处理逻辑"""
        # 如果限流未启用，直接通过
        if not self.enabled:
            return await call_next(request)
        # 获取客户端IP
        client_ip = self._get_client_ip(request)
        # 检查是否允许请求
        if not await self.rate_limiter.check(client_ip):
            logger.warning(f"限流检查➡️IP:{client_ip}➡️触发限流➡️返回429错误")
            raise HTTPException(status_code=429, detail="Too Many Requests")

        return await call_next(request)
