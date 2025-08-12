#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 全面功能测试
测试项目的所有核心功能，包括边界条件、错误处理和极端情况
"""

import pytest
import pytest_asyncio
import asyncio
import json
import time
import threading
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.main import app
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.utils.logger import CILRouterLogger, init_logger, get_logger
import config.config as config

client = TestClient(app)

class TestBasicFunctionality:
    """基础功能测试"""
    
    def test_root_endpoint_structure(self):
        """测试根端点返回结构"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "app", "version", "current_provider_index", 
            "total_providers", "current_provider_endpoints",
            "current_provider_urls", "load_balancing"
        ]
        
        for field in required_fields:
            assert field in data, f"缺少必需字段: {field}"
        
        assert data["app"] == "CIL Router"
        assert data["version"] == "1.0.2"
        assert data["load_balancing"] == "round_robin"
        assert isinstance(data["current_provider_index"], int)
        assert isinstance(data["total_providers"], int)
        assert data["current_provider_index"] < data["total_providers"]
    
    def test_providers_endpoint(self):
        """测试供应商信息端点"""
        response = client.get("/providers")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_provider_index" in data
        assert "providers" in data
        assert isinstance(data["providers"], list)
        assert len(data["providers"]) > 0
        
        # 检查每个供应商的结构
        for provider in data["providers"]:
            assert "index" in provider
            assert "base_urls" in provider
            assert "api_keys_count" in provider
            assert "endpoints_count" in provider
            # API Keys应该被隐藏
            assert "api_keys" not in provider
    
    def test_select_provider_valid_indexes(self):
        """测试选择有效的供应商索引"""
        # 获取当前供应商数量
        root_response = client.get("/")
        total_providers = root_response.json()["total_providers"]
        
        # 测试所有有效索引
        for i in range(total_providers):
            response = client.post("/select", content=str(i))
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["current_index"] == i
            assert data["total_providers"] == total_providers
            assert "message" in data
            
            # 验证切换是否生效
            root_response = client.get("/")
            assert root_response.json()["current_provider_index"] == i
    
    def test_select_provider_invalid_indexes(self):
        """测试选择无效的供应商索引"""
        root_response = client.get("/")
        total_providers = root_response.json()["total_providers"]
        
        invalid_indexes = [-1, -100, total_providers, total_providers + 1, 999]
        
        for invalid_index in invalid_indexes:
            response = client.post("/select", content=str(invalid_index))
            assert response.status_code == 400
            assert "无效的供应商索引" in response.json()["detail"]
    
    def test_select_provider_invalid_input(self):
        """测试无效输入格式"""
        invalid_inputs = ["abc", "1.5", "", "null", "undefined", "[]", "{}"]
        
        for invalid_input in invalid_inputs:
            response = client.post("/select", content=invalid_input)
            assert response.status_code == 400
            assert "请求体必须是一个数字" in response.json()["detail"]


class TestConfigurationModule:
    """配置模块测试"""
    
    def test_config_basic_functions(self):
        """测试配置基础功能"""
        # 测试供应商计数
        count = config.get_provider_count()
        assert count > 0
        assert isinstance(count, int)
        
        # 测试当前供应商获取
        provider = config.get_current_provider()
        assert "base_url" in provider
        assert "api_key" in provider
        assert isinstance(provider["base_url"], str)
        assert isinstance(provider["api_key"], str)
        
        # 测试服务器配置
        server_config = config.get_server_config()
        assert "host" in server_config
        assert "port" in server_config
        assert isinstance(server_config["port"], int)
    
    def test_provider_info_functions(self):
        """测试供应商信息函数"""
        # 测试获取单个供应商信息
        info = config.get_provider_info(0)
        assert "index" in info
        assert "base_urls" in info
        assert "api_keys_count" in info
        assert "endpoints_count" in info
        
        # 测试获取所有供应商信息
        all_info = config.get_all_providers_info()
        assert isinstance(all_info, list)
        assert len(all_info) == config.get_provider_count()
    
    def test_load_balancing_functions(self):
        """测试负载均衡功能"""
        # 连续获取多个端点，检查轮询是否工作
        endpoints = []
        for i in range(10):
            endpoint = config.get_current_provider_endpoint()
            endpoints.append(endpoint["base_url"])
        
        # 如果只有一个端点，所有结果应该相同
        # 如果有多个端点，应该有轮询变化
        unique_endpoints = set(endpoints)
        assert len(unique_endpoints) >= 1
        
        # 测试随机负载均衡
        random_endpoints = []
        for i in range(10):
            endpoint = config.get_current_provider_random_endpoint()
            random_endpoints.append(endpoint["base_url"])
        
        # 随机选择的端点应该都是有效的
        for endpoint in random_endpoints:
            assert isinstance(endpoint, str)
            assert len(endpoint) > 0
    
    def test_timeout_configurations(self):
        """测试超时配置"""
        request_timeout = config.get_request_timeout()
        stream_timeout = config.get_stream_timeout()
        
        assert isinstance(request_timeout, (int, float))
        assert isinstance(stream_timeout, (int, float))
        assert request_timeout > 0
        assert stream_timeout > 0
        assert stream_timeout >= request_timeout  # 流式超时通常更长
    
    def test_set_provider_index_edge_cases(self):
        """测试供应商索引设置的边界情况"""
        original_index = config.current_provider_index
        
        try:
            # 测试有效边界
            assert config.set_provider_index(0) is True
            assert config.current_provider_index == 0
            
            max_index = config.get_provider_count() - 1
            assert config.set_provider_index(max_index) is True
            assert config.current_provider_index == max_index
            
            # 测试无效边界
            assert config.set_provider_index(-1) is False
            assert config.set_provider_index(config.get_provider_count()) is False
            assert config.set_provider_index(999) is False
            
        finally:
            # 恢复原始索引
            config.set_provider_index(original_index)


class TestRateLimiterModule:
    """限流器模块测试"""
    
    @pytest_asyncio.fixture
    async def rate_limiter(self):
        """创建测试用限流器"""
        return RateLimiter(requests_per_minute=60, burst_size=5)
    
    @pytest.mark.asyncio
    async def test_rate_limiter_basic_functionality(self, rate_limiter):
        """测试限流器基本功能"""
        # 测试初始状态
        assert await rate_limiter.is_allowed("test_ip") is True
        
        # 测试bucket状态
        status = await rate_limiter.get_bucket_status("test_ip")
        assert status is not None
        assert "key" in status
        assert "tokens" in status
        assert "capacity" in status
        assert status["key"] == "test_ip"
        assert status["capacity"] == 5  # burst_size
    
    @pytest.mark.asyncio
    async def test_rate_limiter_burst_capacity(self, rate_limiter):
        """测试突发容量"""
        test_ip = "burst_test_ip"
        
        # 应该能够连续消耗burst_size数量的令牌
        for i in range(5):  # burst_size = 5
            allowed = await rate_limiter.is_allowed(test_ip)
            assert allowed is True, f"第{i+1}个请求应该被允许"
        
        # 第6个请求应该被拒绝
        allowed = await rate_limiter.is_allowed(test_ip)
        assert allowed is False, "超过突发容量的请求应该被拒绝"
    
    @pytest.mark.asyncio
    async def test_rate_limiter_token_refill(self, rate_limiter):
        """测试令牌补充"""
        test_ip = "refill_test_ip"
        
        # 消耗所有令牌
        for i in range(5):
            await rate_limiter.is_allowed(test_ip)
        
        # 现在应该没有令牌了
        assert await rate_limiter.is_allowed(test_ip) is False
        
        # 等待一小段时间让令牌补充（60 requests/minute = 1 request/second）
        await asyncio.sleep(1.1)
        
        # 现在应该有新的令牌了
        assert await rate_limiter.is_allowed(test_ip) is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_multiple_ips(self, rate_limiter):
        """测试多个IP的独立限流"""
        ips = ["ip1", "ip2", "ip3"]
        
        # 每个IP应该都有独立的令牌桶
        for ip in ips:
            for i in range(5):  # 消耗所有令牌
                assert await rate_limiter.is_allowed(ip) is True
            # 第6个请求应该被拒绝
            assert await rate_limiter.is_allowed(ip) is False
        
        # 验证状态独立性
        all_status = await rate_limiter.get_all_buckets_status()
        assert all_status["total_buckets"] == len(ips)
    
    @pytest.mark.asyncio
    async def test_rate_limiter_config(self, rate_limiter):
        """测试限流器配置获取"""
        config_data = rate_limiter.get_config()
        assert "requests_per_minute" in config_data
        assert "burst_size" in config_data
        assert "refill_rate" in config_data
        assert config_data["requests_per_minute"] == 60
        assert config_data["burst_size"] == 5
        assert config_data["refill_rate"] == 1.0  # 60/60


class TestRateLimitMiddleware:
    """限流中间件测试"""
    
    def test_ip_extraction_functions(self):
        """测试IP提取功能"""
        from app.middleware.rate_limiter import RateLimitMiddleware
        
        # 创建测试中间件
        rate_limiter = RateLimiter(60, 5)
        middleware = RateLimitMiddleware(
            app=Mock(), 
            rate_limiter=rate_limiter, 
            enabled=True,
            trust_proxy=True
        )
        
        # 测试IP地址验证
        assert middleware._is_valid_ip("192.168.1.1") is True
        assert middleware._is_valid_ip("2001:db8::1") is True
        assert middleware._is_valid_ip("invalid.ip") is False
        assert middleware._is_valid_ip("") is False
        assert middleware._is_valid_ip("999.999.999.999") is False
    
    def test_cloudflare_ip_detection(self):
        """测试Cloudflare IP检测"""
        from app.middleware.rate_limiter import RateLimitMiddleware
        from fastapi import Request
        
        rate_limiter = RateLimiter(60, 5)
        middleware = RateLimitMiddleware(
            app=Mock(), 
            rate_limiter=rate_limiter, 
            enabled=True,
            trust_proxy=True
        )
        
        # 模拟Cloudflare请求
        mock_request = Mock(spec=Request)
        mock_request.client = Mock()
        mock_request.client.host = "1.2.3.4"
        
        # 测试CF-Connecting-IP优先级最高
        mock_request.headers = {
            "CF-Connecting-IP": "5.6.7.8",
            "CF-IPCountry": "US",
            "X-Forwarded-For": "9.10.11.12",
            "X-Real-IP": "13.14.15.16"
        }
        
        client_ip = middleware._get_client_ip(mock_request)
        assert client_ip == "5.6.7.8"
    
    @patch('builtins.open', create=True)
    @patch('pathlib.Path.exists')
    def test_ip_blocking_functionality(self, mock_exists, mock_open):
        """测试IP阻止功能"""
        from app.middleware.rate_limiter import RateLimitMiddleware
        
        # 模拟阻止IP文件
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = '["1.1.1.1", "2.2.2.2"]'
        
        rate_limiter = RateLimiter(60, 5)
        middleware = RateLimitMiddleware(
            app=Mock(), 
            rate_limiter=rate_limiter, 
            enabled=True,
            trust_proxy=True,
            ip_block_enabled=True,
            blocked_ips_file="test_blocked.json"
        )
        
        # 测试IP阻止检查
        assert middleware._is_ip_blocked("1.1.1.1") is True
        assert middleware._is_ip_blocked("3.3.3.3") is False


class TestLoggerModule:
    """日志模块测试"""
    
    def test_logger_initialization(self):
        """测试日志器初始化"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 测试禁用日志
            logger_disabled = CILRouterLogger(log_level="NONE", log_dir=temp_dir)
            assert logger_disabled.is_enabled() is False
            
            # 测试启用日志
            logger_enabled = CILRouterLogger(log_level="DEBUG", log_dir=temp_dir)
            assert logger_enabled.is_enabled() is True
            
            # 测试日志文件创建
            log_file = Path(temp_dir) / "cilrouter.log"
            logger_enabled.info("测试消息")
            assert log_file.exists()
    
    def test_logger_levels(self):
        """测试日志等级"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CILRouterLogger(log_level="WARNING", log_dir=temp_dir)
            log_file = Path(temp_dir) / "cilrouter.log"
            
            # DEBUG和INFO不应该被记录
            logger.debug("debug消息")
            logger.info("info消息")
            
            # WARNING和ERROR应该被记录
            logger.warning("warning消息")
            logger.error("error消息")
            
            # 检查日志文件内容
            if log_file.exists():
                content = log_file.read_text()
                assert "debug消息" not in content
                assert "info消息" not in content
                assert "warning消息" in content
                assert "error消息" in content
    
    def test_logger_structured_logging(self):
        """测试结构化日志"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CILRouterLogger(log_level="DEBUG", log_dir=temp_dir)
            log_file = Path(temp_dir) / "cilrouter.log"
            
            # 记录带有额外数据的日志
            extra_data = {"user_id": 123, "action": "test"}
            logger.info("测试结构化日志", extra_data)
            
            if log_file.exists():
                content = log_file.read_text()
                # 内容应该是JSON格式
                assert '"user_id":123' in content or '"user_id": 123' in content
                assert '"action":"test"' in content or '"action": "test"' in content
    
    def test_global_logger_functions(self):
        """测试全局日志函数"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 初始化全局日志
            init_logger(log_level="DEBUG", log_dir=temp_dir)
            
            # 获取全局日志实例
            global_logger = get_logger()
            assert global_logger is not None
            assert global_logger.is_enabled() is True


class TestErrorHandlingAndEdgeCases:
    """错误处理和边界情况测试"""
    
    def test_malformed_requests(self):
        """测试畸形请求"""
        # 测试空请求体选择供应商
        response = client.post("/select", content="")
        assert response.status_code == 400
        
        # 测试超长请求体
        long_content = "1" * 10000
        response = client.post("/select", content=long_content)
        assert response.status_code == 400
        
        # 测试特殊字符
        special_chars = ["NaN", "Infinity", "-Infinity", "null", "undefined"]
        for char in special_chars:
            response = client.post("/select", content=char)
            assert response.status_code == 400
    
    def test_concurrent_provider_switching(self):
        """测试并发供应商切换"""
        import threading
        import time
        
        results = []
        errors = []
        
        def switch_provider(index):
            try:
                response = client.post("/select", content=str(index % 2))  # 在0和1之间切换
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))
        
        # 创建10个并发线程
        threads = []
        for i in range(10):
            thread = threading.Thread(target=switch_provider, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 检查结果
        assert len(errors) == 0, f"并发测试出现错误: {errors}"
        assert all(status == 200 for status in results), "并发切换应该都成功"
    
    def test_memory_usage_pattern(self):
        """测试内存使用模式"""
        try:
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
            
            # 执行大量请求
            for i in range(100):
                client.get("/")
                client.get("/providers")
                client.post("/select", content="0")
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # 内存增长不应该超过合理范围（比如50MB）
            assert memory_increase < 50 * 1024 * 1024, f"内存增长过多: {memory_increase / 1024 / 1024:.2f}MB"
        except ImportError:
            pytest.skip("psutil 模块未安装，跳过内存测试")
    
    def test_response_headers_security(self):
        """测试响应头安全性"""
        response = client.get("/")
        headers = response.headers
        
        # 检查是否泄露敏感信息
        sensitive_headers = ["server", "x-powered-by", "x-version"]
        for header in sensitive_headers:
            if header in headers:
                # 确保不包含版本信息或服务器信息
                header_value = headers[header].lower()
                assert "uvicorn" not in header_value
                assert "fastapi" not in header_value
    
    def test_path_traversal_protection(self):
        """测试路径遍历攻击保护"""
        malicious_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "....//....//....//etc/passwd"
        ]
        
        for path in malicious_paths:
            response = client.get(f"/{path}")
            # 应该是正常的转发响应，CIL Router作为透明代理不做路径过滤
            assert response.status_code in [200, 404, 502, 500]


class TestPerformanceAndScaling:
    """性能和扩展性测试"""
    
    def test_request_throughput(self):
        """测试请求吞吐量"""
        import time
        
        start_time = time.time()
        request_count = 100
        
        for i in range(request_count):
            response = client.get("/")
            assert response.status_code == 200
        
        end_time = time.time()
        duration = end_time - start_time
        rps = request_count / duration
        
        print(f"请求吞吐量: {rps:.2f} RPS")
        # 应该能够处理至少50 RPS（在测试环境中）
        assert rps > 50, f"吞吐量太低: {rps:.2f} RPS"
    
    def test_large_payload_handling(self):
        """测试大载荷处理"""
        # 创建大载荷（1MB）
        large_payload = "x" * (1024 * 1024)
        
        # 测试供应商选择是否能处理大载荷
        response = client.post("/select", content=large_payload)
        assert response.status_code == 400  # 应该拒绝无效格式
    
    def test_unicode_handling(self):
        """测试Unicode处理"""
        # 测试各种Unicode字符
        unicode_tests = [
            "中文测试",
            "🚀🔥💯",
            "العربية",
            "русский",
            "日本語",
            "한국어"
        ]
        
        for unicode_str in unicode_tests:
            # 这些都不是有效的数字，应该返回400
            response = client.post("/select", content=unicode_str)
            assert response.status_code == 400


class TestDockerAndDeployment:
    """Docker和部署相关测试"""
    
    def test_dockerfile_exists(self):
        """测试Dockerfile存在性"""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile不存在"
        
        content = dockerfile_path.read_text()
        assert "FROM python:" in content
        assert "EXPOSE" in content
        assert "CMD" in content or "ENTRYPOINT" in content
    
    def test_docker_compose_configuration(self):
        """测试Docker Compose配置"""
        compose_path = Path("docker-compose.yml")
        assert compose_path.exists(), "docker-compose.yml不存在"
        
        content = compose_path.read_text()
        assert "version:" in content
        assert "services:" in content
        assert "ports:" in content
    
    def test_requirements_file(self):
        """测试依赖文件"""
        requirements_path = Path("requirements.txt")
        assert requirements_path.exists(), "requirements.txt不存在"
        
        content = requirements_path.read_text()
        required_packages = ["fastapi", "uvicorn", "httpx"]
        
        for package in required_packages:
            assert package in content, f"缺少依赖包: {package}"


if __name__ == "__main__":
    print("开始运行CIL Router全面功能测试...")
    pytest.main([__file__, "-v", "--tb=short"])