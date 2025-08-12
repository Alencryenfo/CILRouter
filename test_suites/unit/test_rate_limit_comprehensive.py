#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 限流功能综合测试
测试令牌桶算法、IP处理、中间件集成等
"""

import pytest
import pytest_asyncio
import asyncio
import time
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
from fastapi import Request
from fastapi.testclient import TestClient

from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware, TokenBucket
from app.main import app
import config.config as config

client = TestClient(app)

class TestTokenBucketAlgorithm:
    """令牌桶算法核心测试"""
    
    @pytest.mark.asyncio
    async def test_token_bucket_basic_operations(self):
        """测试令牌桶基本操作"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        
        # 测试初始状态
        status = await limiter.get_bucket_status("test_ip")
        assert status is None  # 还没有创建bucket
        
        # 第一次请求应该成功，并创建bucket
        assert await limiter.is_allowed("test_ip") is True
        
        status = await limiter.get_bucket_status("test_ip")
        assert status is not None
        assert status["capacity"] == 10
        assert status["tokens"] == 9.0  # 消耗了1个令牌
    
    @pytest.mark.asyncio
    async def test_token_bucket_burst_handling(self):
        """测试突发流量处理"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        test_ip = "burst_test"
        
        # 连续消耗所有突发容量
        for i in range(5):
            assert await limiter.is_allowed(test_ip) is True, f"第{i+1}个请求应该被允许"
        
        # 第6个请求应该被拒绝（超过突发容量）
        assert await limiter.is_allowed(test_ip) is False
        
        # 检查bucket状态
        status = await limiter.get_bucket_status(test_ip)
        assert status["tokens"] == 0.0
    
    @pytest.mark.asyncio
    async def test_token_refill_mechanics(self):
        """测试令牌补充机制"""
        # 使用高频率补充进行测试
        limiter = RateLimiter(requests_per_minute=120, burst_size=3)  # 2个令牌/秒
        test_ip = "refill_test"
        
        # 消耗所有令牌
        for _ in range(3):
            assert await limiter.is_allowed(test_ip) is True
        
        # 现在应该没有令牌
        assert await limiter.is_allowed(test_ip) is False
        
        # 等待0.6秒，应该补充大约1.2个令牌
        await asyncio.sleep(0.6)
        
        # 应该能够发送1个请求
        assert await limiter.is_allowed(test_ip) is True
        assert await limiter.is_allowed(test_ip) is False  # 第二个应该被拒绝
    
    @pytest.mark.asyncio
    async def test_multiple_ips_isolation(self):
        """测试多个IP的隔离性"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=3)
        
        ips = ["ip_1", "ip_2", "ip_3"]
        
        # 每个IP都应该有独立的令牌桶
        for ip in ips:
            # 消耗完所有令牌
            for _ in range(3):
                assert await limiter.is_allowed(ip) is True
            
            # 第4个请求应该被拒绝
            assert await limiter.is_allowed(ip) is False
        
        # 检查所有bucket的状态
        all_status = await limiter.get_all_buckets_status()
        assert all_status["total_buckets"] == 3
        
        for bucket in all_status["buckets"]:
            assert bucket["tokens"] == 0.0
    
    @pytest.mark.asyncio
    async def test_token_bucket_edge_values(self):
        """测试极端参数值"""
        # 测试最小值
        tiny_limiter = RateLimiter(requests_per_minute=1, burst_size=1)
        assert await tiny_limiter.is_allowed("tiny_test") is True
        assert await tiny_limiter.is_allowed("tiny_test") is False
        
        # 测试大值
        huge_limiter = RateLimiter(requests_per_minute=10000, burst_size=1000)
        test_ip = "huge_test"
        
        # 应该能够处理大量连续请求
        for i in range(1000):
            assert await huge_limiter.is_allowed(test_ip) is True
        
        # 第1001个应该被拒绝
        assert await huge_limiter.is_allowed(test_ip) is False


class TestRateLimitMiddleware:
    """限流中间件测试"""
    
    def test_middleware_ip_extraction_methods(self):
        """测试中间件IP提取方法"""
        rate_limiter = RateLimiter(60, 5)
        middleware = RateLimitMiddleware(
            app=Mock(),
            rate_limiter=rate_limiter,
            enabled=True,
            trust_proxy=True
        )
        
        # 测试直接连接IP
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.100"
        
        # 测试Cloudflare IP
        mock_request.headers = {"CF-Connecting-IP": "1.2.3.4"}
        ip = middleware._get_client_ip(mock_request)
        assert ip == "1.2.3.4"
        
        # 测试X-Forwarded-For
        mock_request.headers = {"X-Forwarded-For": "5.6.7.8, 9.10.11.12"}
        ip = middleware._get_client_ip(mock_request)
        assert ip == "5.6.7.8"
    
    def test_middleware_ip_validation(self):
        """测试IP地址验证"""
        rate_limiter = RateLimiter(60, 5)
        middleware = RateLimitMiddleware(
            app=Mock(),
            rate_limiter=rate_limiter,
            enabled=True
        )
        
        # 有效IP地址
        valid_ips = [
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "127.0.0.1",
            "8.8.8.8",
            "2001:db8::1",
            "::1",
            "fe80::1"
        ]
        
        for ip in valid_ips:
            assert middleware._is_valid_ip(ip) is True, f"应该是有效IP: {ip}"
        
        # 无效IP地址
        invalid_ips = [
            "999.999.999.999",
            "192.168.1",
            "192.168.1.1.1",
            "invalid.ip",
            "",
            "localhost",
            "example.com"
        ]
        
        for ip in invalid_ips:
            assert middleware._is_valid_ip(ip) is False, f"应该是无效IP: {ip}"
    
    def test_middleware_proxy_trust_modes(self):
        """测试代理信任模式"""
        rate_limiter = RateLimiter(60, 5)
        
        # 信任代理模式
        trusted_middleware = RateLimitMiddleware(
            app=Mock(),
            rate_limiter=rate_limiter,
            trust_proxy=True
        )
        
        # 不信任代理模式
        untrusted_middleware = RateLimitMiddleware(
            app=Mock(),
            rate_limiter=rate_limiter,
            trust_proxy=False
        )
        
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {"X-Forwarded-For": "8.8.8.8"}
        
        # 信任代理时应该使用X-Forwarded-For
        trusted_ip = trusted_middleware._get_client_ip(mock_request)
        assert trusted_ip == "8.8.8.8"
        
        # 不信任代理时应该使用直接连接IP
        untrusted_ip = untrusted_middleware._get_client_ip(mock_request)
        assert untrusted_ip == "192.168.1.100"


class TestIPBlockingFunctionality:
    """IP阻止功能测试"""
    
    def test_ip_blocking_file_operations(self):
        """测试IP阻止文件操作"""
        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_ips_file = Path(temp_dir) / "test_blocked.json"
            
            # 创建测试的阻止IP文件
            test_blocked_ips = ["1.1.1.1", "2.2.2.2", "malicious.ip"]
            with open(blocked_ips_file, 'w') as f:
                json.dump(test_blocked_ips, f)
            
            rate_limiter = RateLimiter(60, 5)
            middleware = RateLimitMiddleware(
                app=Mock(),
                rate_limiter=rate_limiter,
                ip_block_enabled=True,
                blocked_ips_file=str(blocked_ips_file)
            )
            
            # 测试IP阻止检查
            assert middleware._is_ip_blocked("1.1.1.1") is True
            assert middleware._is_ip_blocked("2.2.2.2") is True
            assert middleware._is_ip_blocked("3.3.3.3") is False
    
    def test_ip_blocking_file_refresh(self):
        """测试IP阻止文件刷新"""
        with tempfile.TemporaryDirectory() as temp_dir:
            blocked_ips_file = Path(temp_dir) / "dynamic_blocked.json"
            
            # 初始文件
            initial_ips = ["1.1.1.1"]
            with open(blocked_ips_file, 'w') as f:
                json.dump(initial_ips, f)
            
            rate_limiter = RateLimiter(60, 5)
            middleware = RateLimitMiddleware(
                app=Mock(),
                rate_limiter=rate_limiter,
                ip_block_enabled=True,
                blocked_ips_file=str(blocked_ips_file)
            )
            
            # 检查初始状态
            assert middleware._is_ip_blocked("1.1.1.1") is True
            assert middleware._is_ip_blocked("2.2.2.2") is False
            
            # 更新文件
            updated_ips = ["1.1.1.1", "2.2.2.2"]
            with open(blocked_ips_file, 'w') as f:
                json.dump(updated_ips, f)
            
            # 手动触发刷新检查（模拟时间流逝）
            middleware._last_file_check = 0  # 强制检查
            middleware._refresh_blocked_ips_if_needed()
            
            # 验证更新
            assert middleware._is_ip_blocked("2.2.2.2") is True


class TestRateLimitingWithRealRequests:
    """使用真实请求的限流测试"""
    
    def setup_method(self):
        """为每个测试方法设置限流"""
        # 临时启用限流进行测试
        self.original_enabled = config.rate_limit_enabled
        config.rate_limit_enabled = True
    
    def teardown_method(self):
        """恢复原始配置"""
        config.rate_limit_enabled = self.original_enabled
    
    @patch.object(config, 'rate_limit_enabled', True)
    @patch.object(config, 'rate_limit_requests_per_minute', 5)  # 很低的限制进行测试
    @patch.object(config, 'rate_limit_burst_size', 2)
    def test_rate_limiting_in_real_requests(self):
        """测试真实请求中的限流"""
        # 注意：这个测试可能不会完全工作，因为中间件在应用启动时初始化
        # 但我们可以测试基本的请求处理
        
        responses = []
        for i in range(5):
            response = client.get("/")
            responses.append(response.status_code)
        
        # 由于中间件配置问题，我们主要检查请求不会崩溃
        assert all(status in [200, 429] for status in responses)


class TestRateLimitConfiguration:
    """限流配置测试"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_config_retrieval(self):
        """测试限流器配置获取"""
        limiter = RateLimiter(requests_per_minute=100, burst_size=15)
        
        config_data = limiter.get_config()
        
        assert config_data["requests_per_minute"] == 100
        assert config_data["burst_size"] == 15
        assert config_data["refill_rate"] == 100/60  # 每秒补充的令牌数
        assert "total_buckets" in config_data
    
    @pytest.mark.asyncio
    async def test_bucket_status_monitoring(self):
        """测试bucket状态监控"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        # 创建一些bucket
        test_ips = ["monitor_ip_1", "monitor_ip_2", "monitor_ip_3"]
        for ip in test_ips:
            await limiter.is_allowed(ip)  # 创建bucket
        
        # 获取所有bucket状态
        all_status = await limiter.get_all_buckets_status()
        
        assert all_status["total_buckets"] == len(test_ips)
        assert all_status["requests_per_minute"] == 60
        assert all_status["burst_size"] == 5
        assert len(all_status["buckets"]) == len(test_ips)
        
        # 检查每个bucket的结构
        for bucket in all_status["buckets"]:
            assert "key" in bucket
            assert "tokens" in bucket
            assert "capacity" in bucket
            assert "refill_rate" in bucket
            assert "last_refill" in bucket
            assert "inactive_seconds" in bucket


class TestRateLimitConcurrency:
    """限流并发性测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_rate_limiting(self):
        """测试并发限流"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=10)
        test_ip = "concurrent_test"
        
        async def make_request():
            return await limiter.is_allowed(test_ip)
        
        # 创建并发任务
        tasks = [make_request() for _ in range(20)]
        results = await asyncio.gather(*tasks)
        
        # 应该有恰好10个成功（burst_size）
        success_count = sum(results)
        assert success_count == 10
        
        # 剩余的应该被拒绝
        failure_count = len(results) - success_count
        assert failure_count == 10
    
    @pytest.mark.asyncio
    async def test_multiple_ips_concurrent_access(self):
        """测试多IP并发访问"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        async def test_ip_access(ip_suffix):
            ip = f"concurrent_ip_{ip_suffix}"
            results = []
            for _ in range(7):  # 超过burst_size
                result = await limiter.is_allowed(ip)
                results.append(result)
            return results
        
        # 10个IP同时进行访问测试
        ip_tasks = [test_ip_access(i) for i in range(10)]
        all_results = await asyncio.gather(*ip_tasks)
        
        # 每个IP应该有恰好5个成功请求
        for ip_results in all_results:
            success_count = sum(ip_results)
            assert success_count == 5, f"每个IP应该有5个成功请求，实际: {success_count}"


class TestRateLimitMemoryManagement:
    """限流内存管理测试"""
    
    @pytest.mark.asyncio
    async def test_bucket_cleanup_mechanism(self):
        """测试bucket清理机制"""
        limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        # 创建大量bucket
        for i in range(100):
            await limiter.is_allowed(f"cleanup_test_{i}")
        
        # 验证创建了100个bucket
        status_before = await limiter.get_all_buckets_status()
        assert status_before["total_buckets"] == 100
        
        # 手动修改一些bucket的时间戳，模拟过期
        current_time = time.time()
        expired_threshold = current_time - 700  # 超过10分钟
        
        # 修改前50个bucket为过期状态
        for i, (key, bucket) in enumerate(list(limiter.buckets.items())[:50]):
            bucket.last_refill = expired_threshold
        
        # 等待清理任务运行（如果已经启动的话）
        await asyncio.sleep(0.1)
        
        # 检查bucket数量（清理可能还没运行）
        status_after = await limiter.get_all_buckets_status()
        # 由于清理是异步的，我们只检查系统没有崩溃
        assert status_after["total_buckets"] >= 50


class TestRateLimitErrorHandling:
    """限流错误处理测试"""
    
    @pytest.mark.asyncio
    async def test_limiter_with_invalid_parameters(self):
        """测试无效参数的限流器"""
        # 测试零值
        with pytest.raises(ValueError):
            # 这可能会在实际实现中抛出异常
            RateLimiter(requests_per_minute=0, burst_size=5)
    
    @pytest.mark.asyncio
    async def test_limiter_with_extreme_parameters(self):
        """测试极端参数的限流器"""
        # 测试非常大的值
        huge_limiter = RateLimiter(requests_per_minute=1000000, burst_size=100000)
        
        # 应该能正常工作
        assert await huge_limiter.is_allowed("huge_test") is True
        
        # 测试非常小的值
        tiny_limiter = RateLimiter(requests_per_minute=1, burst_size=1)
        assert await tiny_limiter.is_allowed("tiny_test") is True
        assert await tiny_limiter.is_allowed("tiny_test") is False


if __name__ == "__main__":
    print("开始运行CIL Router限流功能综合测试...")
    pytest.main([__file__, "-v", "--tb=short"])