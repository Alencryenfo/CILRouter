# -*- coding: utf-8 -*-
"""
基于令牌桶算法的限流中间件
支持基于IP的请求速率限制，允许突发流量
"""

import time
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class TokenBucket:
    """令牌桶数据结构"""
    tokens: float          # 当前令牌数量
    capacity: int          # 桶容量（最大令牌数）
    refill_rate: float     # 令牌补充速率（每秒）
    last_refill: float     # 上次补充时间


class RateLimiter:
    """基于令牌桶算法的限流器"""
    
    def __init__(self, requests_per_minute: int = 100, burst_size: int = 10):
        """
        初始化限流器
        
        Args:
            requests_per_minute: 每分钟允许的请求数
            burst_size: 突发容量（允许短时间内超过平均速率的请求数）
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.refill_rate = requests_per_minute / 60.0  # 每秒补充的令牌数
        self.buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        
        # 清理过期bucket的任务
        self._cleanup_task = None
        # 延迟启动清理任务，等到有事件循环时再启动
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_buckets())
    
    async def _cleanup_expired_buckets(self):
        """定期清理长时间未使用的bucket"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                now = time.time()
                expired_keys = []
                
                async with self._lock:
                    for key, bucket in self.buckets.items():
                        # 如果bucket 10分钟没有活动，则清理
                        if now - bucket.last_refill > 600:
                            expired_keys.append(key)
                    
                    for key in expired_keys:
                        del self.buckets[key]
                
                if expired_keys:
                    print(f"🧹 清理了 {len(expired_keys)} 个过期的限流bucket")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ 清理expired buckets时出错: {e}")
    
    def _create_bucket(self) -> TokenBucket:
        """创建新的令牌桶"""
        return TokenBucket(
            tokens=float(self.burst_size),  # 初始令牌数等于突发容量
            capacity=self.burst_size,
            refill_rate=self.refill_rate,
            last_refill=time.time()
        )
    
    def _refill_tokens(self, bucket: TokenBucket) -> None:
        """为令牌桶补充令牌"""
        now = time.time()
        elapsed = now - bucket.last_refill
        
        if elapsed > 0:
            # 计算应该补充的令牌数
            tokens_to_add = elapsed * bucket.refill_rate
            bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
            bucket.last_refill = now
    
    async def is_allowed(self, key: str, tokens_requested: int = 1) -> bool:
        """
        检查是否允许请求
        
        Args:
            key: 限流键（通常是IP地址）
            tokens_requested: 请求的令牌数量
            
        Returns:
            bool: 是否允许请求
        """
        # 首次调用时启动清理任务
        if self._cleanup_task is None:
            try:
                self._start_cleanup_task()
            except RuntimeError:
                # 如果没有事件循环，跳过清理任务
                pass
        
        async with self._lock:
            # 获取或创建bucket
            if key not in self.buckets:
                self.buckets[key] = self._create_bucket()
            
            bucket = self.buckets[key]
            
            # 补充令牌
            self._refill_tokens(bucket)
            
            # 检查是否有足够的令牌
            if bucket.tokens >= tokens_requested:
                bucket.tokens -= tokens_requested
                return True
            
            return False
    
    async def get_bucket_status(self, key: str) -> Optional[Dict]:
        """
        获取指定key的bucket状态
        
        Args:
            key: 限流键
            
        Returns:
            Dict: bucket状态信息，如果不存在则返回None
        """
        async with self._lock:
            if key not in self.buckets:
                return None
            
            bucket = self.buckets[key]
            self._refill_tokens(bucket)  # 更新令牌数
            
            return {
                "key": key,
                "tokens": round(bucket.tokens, 2),
                "capacity": bucket.capacity,
                "refill_rate": bucket.refill_rate,
                "last_refill": bucket.last_refill
            }
    
    async def get_all_buckets_status(self) -> Dict:
        """获取所有bucket的状态"""
        async with self._lock:
            now = time.time()
            buckets_info = []
            
            for key, bucket in self.buckets.items():
                self._refill_tokens(bucket)  # 更新令牌数
                buckets_info.append({
                    "key": key,
                    "tokens": round(bucket.tokens, 2),
                    "capacity": bucket.capacity,
                    "refill_rate": bucket.refill_rate,
                    "last_refill": bucket.last_refill,
                    "inactive_seconds": round(now - bucket.last_refill, 1)
                })
            
            return {
                "total_buckets": len(self.buckets),
                "requests_per_minute": self.requests_per_minute,
                "burst_size": self.burst_size,
                "buckets": buckets_info
            }
    
    def get_config(self) -> Dict:
        """获取限流器配置"""
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst_size": self.burst_size,
            "refill_rate": self.refill_rate,
            "total_buckets": len(self.buckets)
        }


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
            import ipaddress
            ipaddress.ip_address(ip)
            return True
        except (ValueError, ipaddress.AddressValueError):
            return False
    
    def _should_skip_rate_limit(self, request: Request) -> bool:
        """判断是否应该跳过限流检查"""
        # 所有请求都进行限流检查，不跳过任何路径
        return False
    
    async def dispatch(self, request: Request, call_next):
        """中间件处理逻辑"""
        # 如果限流未启用，直接通过
        if not self.enabled:
            return await call_next(request)
        
        # 检查是否需要跳过限流
        if self._should_skip_rate_limit(request):
            return await call_next(request)
        
        # 获取客户端IP
        client_ip = self._get_client_ip(request)
        
        # 检查是否允许请求
        if not await self.rate_limiter.is_allowed(client_ip):
            # 获取bucket状态用于返回剩余信息
            bucket_status = await self.rate_limiter.get_bucket_status(client_ip)
            
            # 计算重试时间（基于令牌补充速率）
            retry_after = int(60 / self.rate_limiter.requests_per_minute) + 1
            
            # 返回429状态码
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "请求频率限制",
                    "message": f"来自 {client_ip} 的请求过于频繁",
                    "requests_per_minute": self.rate_limiter.requests_per_minute,
                    "burst_size": self.rate_limiter.burst_size,
                    "current_tokens": bucket_status["tokens"] if bucket_status else 0,
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": str(int(bucket_status["tokens"]) if bucket_status else 0),
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after)
                }
            )
        
        # 请求通过，继续处理
        response = await call_next(request)
        
        # 在响应头中添加限流信息
        bucket_status = await self.rate_limiter.get_bucket_status(client_ip)
        if bucket_status:
            response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(int(bucket_status["tokens"]))
            response.headers["X-RateLimit-Reset"] = str(int(bucket_status["last_refill"]) + 60)
        
        return response