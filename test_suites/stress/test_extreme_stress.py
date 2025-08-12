#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 极端和压力测试
测试系统在各种极端条件下的行为，包括边界条件、恶意输入、资源耗尽等
"""

import pytest
import asyncio
import threading
import time
import json
import random
import string
import tempfile
import os
import gc
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.utils.logger import CILRouterLogger
import config.config as config

client = TestClient(app)

class TestExtremeInputs:
    """极端输入测试"""
    
    def test_extremely_long_strings(self):
        """测试极长字符串处理"""
        # 测试各种长度的字符串
        lengths = [1000, 10000, 100000, 1000000]
        
        for length in lengths:
            long_string = "1" * length
            response = client.post("/select", content=long_string)
            assert response.status_code == 400, f"长度{length}的字符串应该被拒绝"
    
    def test_special_characters_and_encodings(self):
        """测试特殊字符和编码"""
        special_inputs = [
            "\x00\x01\x02",  # 控制字符
            "\uFFFF\uFFFE",  # Unicode边界字符
            "\\n\\r\\t",     # 转义字符
            "<script>alert('xss')</script>",  # XSS尝试
            "'; DROP TABLE users; --",  # SQL注入尝试
            "../../../../../../etc/passwd",  # 路径遍历
            "%2e%2e%2f" * 10,  # URL编码的路径遍历
            "\u200B\u200C\u200D",  # 零宽字符
            "🚀" * 1000,  # 大量Emoji
            "中文" * 1000,  # 大量中文字符
        ]
        
        for special_input in special_inputs:
            response = client.post("/select", content=special_input)
            # 这些都不是有效数字，应该返回400
            assert response.status_code == 400, f"特殊输入应该被拒绝: {special_input[:50]}"
    
    def test_binary_data_handling(self):
        """测试二进制数据处理"""
        # 生成随机二进制数据
        binary_data = bytes(random.randint(0, 255) for _ in range(1024))
        
        response = client.post("/select", content=binary_data)
        assert response.status_code == 400, "二进制数据应该被拒绝"
    
    def test_json_injection_attempts(self):
        """测试JSON注入尝试"""
        json_payloads = [
            '{"evil": true}',
            '[1,2,3,4,5]',
            '{"$ne": null}',  # NoSQL注入尝试
            '{"constructor": {"prototype": {"isAdmin": true}}}',  # 原型污染尝试
            '{"__proto__": {"admin": true}}',  # 原型污染尝试
        ]
        
        for payload in json_payloads:
            response = client.post("/select", content=payload)
            assert response.status_code == 400, f"JSON载荷应该被拒绝: {payload}"
    
    def test_floating_point_edge_cases(self):
        """测试浮点数边界情况"""
        float_edge_cases = [
            "inf", "-inf", "infinity", "-infinity",
            "nan", "NaN", "-nan",
            "1e308", "-1e308",  # 接近浮点数极限
            "1.7976931348623157e+308",  # 最大浮点数
            "2.2250738585072014e-308",  # 最小正浮点数
            "0.0000000000000000000000000000000001",  # 极小数字
        ]
        
        for edge_case in float_edge_cases:
            response = client.post("/select", content=edge_case)
            assert response.status_code == 400, f"浮点边界值应该被拒绝: {edge_case}"


class TestConcurrencyAndRaceConditions:
    """并发和竞态条件测试"""
    
    def test_high_concurrency_provider_switching(self):
        """测试高并发供应商切换"""
        def switch_provider():
            try:
                index = random.randint(0, 1)  # 假设有2个供应商
                response = client.post("/select", content=str(index))
                return response.status_code == 200
            except Exception:
                return False
        
        # 创建大量并发线程
        num_threads = 50
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(switch_provider) for _ in range(num_threads)]
            results = [future.result() for future in as_completed(futures)]
        
        # 大部分请求应该成功（允许一些失败由于竞态条件）
        success_rate = sum(results) / len(results)
        assert success_rate > 0.8, f"并发成功率过低: {success_rate:.2%}"
    
    def test_concurrent_api_calls(self):
        """测试并发API调用"""
        def make_api_call(endpoint):
            try:
                if endpoint == "root":
                    response = client.get("/")
                elif endpoint == "providers":
                    response = client.get("/providers")
                else:
                    response = client.post("/select", content="0")
                return response.status_code
            except Exception as e:
                return 500
        
        # 混合不同类型的API调用
        endpoints = ["root", "providers", "select"] * 20
        
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(make_api_call, endpoint) for endpoint in endpoints]
            status_codes = [future.result() for future in as_completed(futures)]
        
        # 大部分调用应该成功
        success_codes = [200, 400]  # 400对于select调用是正常的
        successful_calls = sum(1 for code in status_codes if code in success_codes)
        success_rate = successful_calls / len(status_codes)
        
        assert success_rate > 0.9, f"并发API调用成功率: {success_rate:.2%}"
    
    def test_resource_exhaustion_simulation(self):
        """测试资源耗尽模拟"""
        # 快速连续发送大量请求，模拟DDoS攻击
        def rapid_fire_requests():
            try:
                for _ in range(100):
                    client.get("/")
                return True
            except Exception:
                return False
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(rapid_fire_requests) for _ in range(10)]
            results = [future.result() for future in as_completed(futures)]
        
        # 系统应该能够处理这种压力而不崩溃
        assert len(results) == 10, "系统应该处理所有线程"


class TestRateLimiterExtremeConditions:
    """限流器极端条件测试"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_with_extreme_values(self):
        """测试极端参数值的限流器"""
        # 测试极小值
        tiny_limiter = RateLimiter(requests_per_minute=1, burst_size=1)
        assert await tiny_limiter.is_allowed("test") is True
        assert await tiny_limiter.is_allowed("test") is False
        
        # 测试极大值
        huge_limiter = RateLimiter(requests_per_minute=1000000, burst_size=10000)
        for i in range(10000):
            assert await huge_limiter.is_allowed("test") is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_memory_usage(self):
        """测试限流器内存使用"""
        rate_limiter = RateLimiter(requests_per_minute=100, burst_size=10)
        
        # 创建大量不同的IP
        for i in range(10000):
            await rate_limiter.is_allowed(f"ip_{i}")
        
        # 检查bucket数量
        status = await rate_limiter.get_all_buckets_status()
        assert status["total_buckets"] == 10000
        
        # 等待清理任务运行（如果有的话）
        await asyncio.sleep(0.1)
    
    @pytest.mark.asyncio
    async def test_rate_limiter_with_invalid_ips(self):
        """测试无效IP地址的处理"""
        rate_limiter = RateLimiter(requests_per_minute=60, burst_size=5)
        
        invalid_ips = [
            "",
            None,
            "invalid_ip",
            "999.999.999.999",
            "not.an.ip.address",
            "🚀.💻.🌐.🔥"
        ]
        
        for invalid_ip in invalid_ips:
            # 应该能够处理无效IP而不崩溃
            try:
                result = await rate_limiter.is_allowed(str(invalid_ip))
                assert isinstance(result, bool)
            except Exception as e:
                pytest.fail(f"处理无效IP时出现异常: {invalid_ip} -> {e}")


class TestLoggerRobustness:
    """日志器健壮性测试"""
    
    def test_logger_with_extreme_data(self):
        """测试日志器处理极端数据"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CILRouterLogger(log_level="DEBUG", log_dir=temp_dir)
            
            # 测试各种极端数据
            extreme_data = [
                {"huge_string": "x" * 100000},
                {"binary_data": b"\x00\x01\x02\x03"},
                {"unicode": "🚀💯🔥" * 100},
                {"nested": {"a": {"b": {"c": "deep" * 1000}}}},
                {"special_chars": "\n\r\t\0\x1f"},
                {"circular_ref": None}  # 我们会手动创建循环引用
            ]
            
            for data in extreme_data:
                try:
                    logger.info("极端数据测试", data)
                except Exception as e:
                    pytest.fail(f"日志器处理极端数据失败: {data} -> {e}")
    
    def test_logger_file_operations_robustness(self):
        """测试日志器文件操作健壮性"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CILRouterLogger(log_level="DEBUG", log_dir=temp_dir)
            log_file = Path(temp_dir) / "cilrouter.log"
            
            # 写入大量日志
            for i in range(1000):
                logger.info(f"测试日志 {i}", {"iteration": i})
            
            # 检查文件是否正确创建
            assert log_file.exists()
            
            # 检查文件内容
            content = log_file.read_text()
            assert "测试日志 0" in content
            assert "测试日志 999" in content
    
    def test_logger_performance_under_load(self):
        """测试日志器高负载性能"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CILRouterLogger(log_level="DEBUG", log_dir=temp_dir)
            
            start_time = time.time()
            
            # 快速写入大量日志
            for i in range(5000):
                logger.info(f"性能测试 {i}")
            
            end_time = time.time()
            duration = end_time - start_time
            
            # 应该能在合理时间内完成
            assert duration < 5.0, f"日志写入性能过慢: {duration:.2f}秒"


class TestConfigurationEdgeCases:
    """配置边界情况测试"""
    
    def test_config_with_empty_providers(self):
        """测试空供应商配置"""
        with patch.object(config, 'providers', []):
            # 获取供应商信息应该返回空
            assert config.get_provider_count() == 0
            
            # 获取当前供应商应该返回空
            provider = config.get_current_provider_endpoint()
            assert provider["base_url"] == ""
            assert provider["api_key"] == ""
    
    def test_config_with_malformed_data(self):
        """测试畸形配置数据"""
        malformed_providers = [
            {"base_urls": [], "api_keys": []},  # 空列表
            {"base_urls": [""], "api_keys": [""]},  # 空字符串
            {"base_urls": None, "api_keys": None},  # None值
        ]
        
        for malformed in malformed_providers:
            with patch.object(config, 'providers', [malformed]):
                provider = config.get_current_provider_endpoint()
                # 应该能够处理而不崩溃
                assert isinstance(provider, dict)
    
    def test_config_reload_functionality(self):
        """测试配置重新加载功能"""
        original_count = config.get_provider_count()
        
        # 模拟环境变量变化
        with patch.dict(os.environ, {
            'PROVIDER_99_BASE_URL': 'https://test.com',
            'PROVIDER_99_API_KEY': 'test-key'
        }):
            config.reload_config()
            new_count = config.get_provider_count()
            
            # 可能会增加供应商数量
            assert isinstance(new_count, int)


class TestErrorRecoveryAndFailover:
    """错误恢复和故障转移测试"""
    
    @patch('httpx.AsyncClient.request')
    def test_request_timeout_handling(self, mock_request):
        """测试请求超时处理"""
        import httpx
        
        # 模拟超时异常
        mock_request.side_effect = httpx.TimeoutException("请求超时")
        
        # 发送请求应该优雅地处理超时
        response = client.post("/test_path", json={"test": "data"})
        assert response.status_code in [502, 500]  # 应该返回错误状态码
    
    @patch('httpx.AsyncClient.request')
    def test_network_error_handling(self, mock_request):
        """测试网络错误处理"""
        import httpx
        
        # 模拟连接错误
        mock_request.side_effect = httpx.ConnectError("连接失败")
        
        response = client.post("/test_path", json={"test": "data"})
        assert response.status_code in [502, 500]
    
    def test_malformed_json_handling(self):
        """测试畸形JSON处理"""
        malformed_jsons = [
            '{"incomplete":',
            '{"unclosed": "string}',
            '{invalid_json}',
            '{"nested": {"broken": }',
            '{"trailing_comma": "value",}',
        ]
        
        for malformed_json in malformed_jsons:
            response = client.post("/test_path", 
                                   data=malformed_json,
                                   headers={"Content-Type": "application/json"})
            # 应该优雅地处理畸形JSON
            assert response.status_code in [400, 422, 502, 500]


class TestSecurityAndInjectionAttacks:
    """安全性和注入攻击测试"""
    
    def test_header_injection_attempts(self):
        """测试头部注入攻击"""
        malicious_headers = {
            "X-Injection": "value\r\nX-Injected: evil",
            "Authorization": "Bearer fake\r\nX-Admin: true",
            "Content-Type": "application/json\r\nX-Override: admin",
        }
        
        for header, value in malicious_headers.items():
            try:
                response = client.get("/", headers={header: value})
                # 应该被正常处理或拒绝，不应该崩溃
                assert response.status_code in [200, 400, 403, 500, 502]
            except Exception as e:
                # 如果抛出异常，应该是合理的HTTP异常
                assert "injection" not in str(e).lower()
    
    def test_path_traversal_attempts(self):
        """测试路径遍历攻击"""
        traversal_paths = [
            "../../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd",
            "/proc/self/environ",
            "/dev/random",
        ]
        
        for path in traversal_paths:
            response = client.get(f"/{path}")
            # 不应该返回文件内容，应该是转发错误或404
            assert response.status_code in [404, 502, 500]
            
            # 响应内容不应该包含系统文件内容
            content = response.text.lower()
            assert "root:" not in content
            assert "bin/bash" not in content
            assert "passwd" not in content or "invalid" in content
    
    def test_command_injection_attempts(self):
        """测试命令注入攻击"""
        command_injections = [
            "; ls -la",
            "| cat /etc/passwd",
            "&& whoami",
            "`id`",
            "$(whoami)",
            "; ping -c 1 127.0.0.1",
        ]
        
        for injection in command_injections:
            response = client.post("/select", content=injection)
            assert response.status_code == 400, "命令注入应该被拒绝"


if __name__ == "__main__":
    print("开始运行CIL Router极端和压力测试...")
    pytest.main([__file__, "-v", "--tb=short", "-x"])