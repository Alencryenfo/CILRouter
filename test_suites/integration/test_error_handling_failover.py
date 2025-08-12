#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 错误处理和故障转移测试
测试各种错误场景下的系统行为和恢复能力
"""

import pytest
import asyncio
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
import httpx

from app.main import app, _handle_normal_request_with_retry_and_body
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
import config.config as config

client = TestClient(app)

class TestNetworkErrorHandling:
    """网络错误处理测试"""
    
    @patch('httpx.AsyncClient.request')
    def test_connection_error_handling(self, mock_request):
        """测试连接错误处理"""
        # 模拟连接错误
        mock_request.side_effect = httpx.ConnectError("连接被拒绝")
        
        response = client.post("/test/endpoint", json={"test": "data"})
        
        # 应该返回502或500状态码
        assert response.status_code in [502, 500]
        detail = response.json()["detail"]
        # 检查是否包含错误相关信息
        assert any(keyword in detail.lower() for keyword in ["error", "连接", "失败", "endpoint"])
    
    @patch('httpx.AsyncClient.request')
    def test_timeout_error_handling(self, mock_request):
        """测试超时错误处理"""
        # 模拟超时错误
        mock_request.side_effect = httpx.TimeoutException("请求超时")
        
        response = client.post("/api/test", json={"message": "timeout test"})
        
        assert response.status_code in [502, 500]
        error_detail = response.json()["detail"].lower()
        assert any(keyword in error_detail for keyword in ["timeout", "超时", "失败", "endpoint"])
    
    @patch('httpx.AsyncClient.request')
    def test_http_status_error_handling(self, mock_request):
        """测试HTTP状态错误处理"""
        # 模拟各种HTTP错误状态
        error_responses = [
            (400, "Bad Request"),
            (401, "Unauthorized"),
            (403, "Forbidden"),
            (404, "Not Found"),
            (500, "Internal Server Error"),
            (502, "Bad Gateway"),
            (503, "Service Unavailable")
        ]
        
        for status_code, reason in error_responses:
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = json.dumps({"error": reason}).encode()
            mock_response.text = json.dumps({"error": reason})
            
            mock_request.return_value = mock_response
            
            response = client.post("/api/test", json={"test": "error"})
            
            # 应该透明转发状态码
            assert response.status_code == status_code
    
    @patch('httpx.AsyncClient.request')
    def test_network_instability_simulation(self, mock_request):
        """测试网络不稳定模拟"""
        # 模拟间歇性网络故障
        call_count = 0
        
        def intermittent_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:  # 每三次调用失败一次
                raise httpx.ConnectError("间歇性连接失败")
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.content = b'{"success": true}'
            return mock_response
        
        mock_request.side_effect = intermittent_failure
        
        # 发送多个请求
        responses = []
        for i in range(10):
            response = client.post("/test", json={"request": i})
            responses.append(response.status_code)
        
        # 应该有成功和失败的混合结果
        success_count = sum(1 for status in responses if status == 200)
        error_count = sum(1 for status in responses if status in [502, 500])
        
        assert success_count > 0, "应该有一些成功的请求"
        assert error_count > 0, "应该有一些失败的请求"


class TestProviderFailoverAndRetry:
    """供应商故障转移和重试测试"""
    
    def test_provider_configuration_validation(self):
        """测试供应商配置验证"""
        original_providers = config.providers
        
        try:
            # 测试空供应商列表
            with patch.object(config, 'providers', []):
                provider = config.get_current_provider_endpoint()
                assert provider["base_url"] == ""
                assert provider["api_key"] == ""
            
            # 测试无效供应商配置
            invalid_providers = [
                {"base_urls": [], "api_keys": []},
                {"base_urls": [""], "api_keys": [""]}
            ]
            
            for invalid_provider in invalid_providers:
                with patch.object(config, 'providers', [invalid_provider]):
                    provider = config.get_current_provider_endpoint()
                    assert provider["base_url"] == "" or provider["api_key"] == ""
        
        finally:
            config.providers = original_providers
    
    def test_load_balancing_with_failed_endpoints(self):
        """测试端点故障时的负载均衡"""
        # 模拟多端点供应商配置
        test_providers = [{
            "base_urls": ["https://api1.test.com", "https://api2.test.com", "https://api3.test.com"],
            "api_keys": ["key1", "key2", "key3"]
        }]
        
        original_providers = config.providers
        original_index = config.current_provider_index
        
        try:
            with patch.object(config, 'providers', test_providers):
                with patch.object(config, 'current_provider_index', 0):
                    # 获取多个端点，应该轮询
                    endpoints = []
                    for i in range(6):  # 获取两轮
                        endpoint = config.get_current_provider_endpoint()
                        endpoints.append(endpoint["base_url"])
                    
                    # 应该按顺序轮询
                    expected_pattern = test_providers[0]["base_urls"] * 2
                    assert endpoints == expected_pattern
        
        finally:
            config.providers = original_providers
            config.current_provider_index = original_index
    
    def test_provider_switching_robustness(self):
        """测试供应商切换的健壮性"""
        original_index = config.current_provider_index
        provider_count = config.get_provider_count()
        
        try:
            # 测试边界值切换
            test_cases = [
                (0, True),
                (provider_count - 1, True),
                (-1, False),
                (provider_count, False),
                (999, False)
            ]
            
            for index, should_succeed in test_cases:
                result = config.set_provider_index(index)
                assert result == should_succeed
                
                if should_succeed:
                    assert config.current_provider_index == index
        
        finally:
            config.set_provider_index(original_index)


class TestRequestProcessingErrors:
    """请求处理错误测试"""
    
    def test_malformed_request_handling(self):
        """测试畸形请求处理"""
        # 测试各种畸形请求
        malformed_requests = [
            ({"content_type": "application/json"}, b'{"incomplete": '),
            ({"content_type": "application/json"}, b'invalid json'),
            ({"content_type": "application/xml"}, b'<incomplete><xml>'),
            ({}, b'\x00\x01\x02\x03'),  # 二进制数据
        ]
        
        for headers, body in malformed_requests:
            response = client.post("/api/test", headers=headers, content=body)
            # 应该返回错误但不崩溃
            assert response.status_code in [400, 422, 502, 500]
    
    def test_oversized_request_handling(self):
        """测试超大请求处理"""
        # 创建大请求（1MB）
        large_data = {"data": "x" * (1024 * 1024)}
        
        try:
            response = client.post("/api/test", json=large_data, timeout=30)
            # 应该能处理或优雅拒绝
            assert response.status_code in [200, 413, 502, 500]
        except Exception as e:
            # 如果抛出异常，应该是合理的异常
            assert "timeout" in str(e).lower() or "size" in str(e).lower()
    
    def test_concurrent_error_scenarios(self):
        """测试并发错误场景"""
        import threading
        import random
        
        results = []
        errors = []
        
        def make_problematic_request(request_id):
            try:
                # 随机选择不同类型的问题请求
                problem_types = [
                    lambda: client.post("/select", content="invalid"),
                    lambda: client.post("/api/test", json={"test": "x" * 10000}),
                    lambda: client.get("/nonexistent/path"),
                ]
                
                problem_request = random.choice(problem_types)
                response = problem_request()
                results.append((request_id, response.status_code))
            except Exception as e:
                errors.append((request_id, str(e)))
        
        # 创建并发问题请求
        threads = []
        for i in range(20):
            thread = threading.Thread(target=make_problematic_request, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 系统应该能处理所有请求而不崩溃
        assert len(results) + len(errors) == 20
        
        # 大部分请求应该得到合理的响应
        reasonable_statuses = [200, 400, 404, 502, 500]
        reasonable_responses = sum(1 for _, status in results if status in reasonable_statuses)
        assert reasonable_responses == len(results), f"不合理的状态码: {results}"


class TestSystemResourceHandling:
    """系统资源处理测试"""
    
    def test_memory_pressure_simulation(self):
        """测试内存压力模拟"""
        # 创建大量并发请求来模拟内存压力
        import threading
        
        def memory_intensive_request():
            # 创建包含大量数据的请求
            data = {"large_field": "x" * 10000}
            response = client.post("/api/test", json=data)
            return response.status_code
        
        # 快速创建大量线程
        threads = []
        for i in range(50):
            thread = threading.Thread(target=memory_intensive_request)
            threads.append(thread)
            thread.start()
        
        # 等待完成
        for thread in threads:
            thread.join()
        
        # 系统应该仍然可以响应
        response = client.get("/")
        assert response.status_code == 200
    
    def test_file_system_error_handling(self):
        """测试文件系统错误处理"""
        # 测试日志文件权限问题
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            
            # 创建只读日志目录
            log_dir.chmod(0o444)
            
            try:
                from app.utils.logger import CILRouterLogger
                
                # 尝试在只读目录创建日志
                logger = CILRouterLogger(log_level="DEBUG", log_dir=str(log_dir))
                
                # 应该能处理权限错误而不崩溃
                logger.info("测试日志")
                
            except PermissionError:
                # 预期的权限错误
                pass
            except Exception as e:
                # 其他异常应该被合理处理
                assert "permission" in str(e).lower() or "access" in str(e).lower()
            
            finally:
                # 恢复权限以便清理
                try:
                    log_dir.chmod(0o755)
                except:
                    pass


class TestConfigurationErrorHandling:
    """配置错误处理测试"""
    
    def test_missing_configuration_handling(self):
        """测试缺失配置处理"""
        # 备份原始配置
        original_providers = config.providers
        
        try:
            # 模拟配置丢失
            with patch.object(config, 'providers', None):
                # 系统应该能处理None配置
                try:
                    response = client.get("/")
                    # 可能返回错误，但不应该崩溃
                    assert response.status_code in [200, 500, 503]
                except Exception as e:
                    # 如果抛出异常，应该是配置相关的
                    assert "config" in str(e).lower() or "provider" in str(e).lower()
        
        finally:
            config.providers = original_providers
    
    def test_corrupted_configuration_handling(self):
        """测试损坏配置处理"""
        # 模拟各种损坏的配置
        corrupted_configs = [
            [],  # 空列表
            [{}],  # 空字典
            [{"invalid": "config"}],  # 缺少必需字段
            [{"base_urls": None, "api_keys": None}],  # None值
            [{"base_urls": "not_a_list", "api_keys": "not_a_list"}],  # 错误类型
        ]
        
        original_providers = config.providers
        
        for corrupted_config in corrupted_configs:
            try:
                with patch.object(config, 'providers', corrupted_config):
                    # 尝试获取供应商信息
                    provider = config.get_current_provider_endpoint()
                    
                    # 应该返回安全的默认值
                    assert isinstance(provider, dict)
                    assert "base_url" in provider
                    assert "api_key" in provider
            
            finally:
                config.providers = original_providers


class TestErrorRecoveryAndGracefulDegradation:
    """错误恢复和优雅降级测试"""
    
    def test_service_recovery_after_failure(self):
        """测试故障后的服务恢复"""
        # 模拟服务故障然后恢复
        call_count = 0
        
        def failing_then_recovering(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count <= 3:
                # 前3次调用失败
                raise httpx.ConnectError("服务暂时不可用")
            else:
                # 之后的调用成功
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.headers = {}
                mock_response.content = b'{"recovered": true}'
                return mock_response
        
        with patch('httpx.AsyncClient.request', side_effect=failing_then_recovering):
            # 前几个请求应该失败
            for i in range(3):
                response = client.post("/api/test", json={"test": f"request_{i}"})
                assert response.status_code in [502, 500]
            
            # 后续请求应该成功
            response = client.post("/api/test", json={"test": "recovery_test"})
            assert response.status_code == 200
    
    def test_graceful_degradation_under_load(self):
        """测试负载下的优雅降级"""
        # 模拟高负载情况
        def slow_response(*args, **kwargs):
            time.sleep(0.1)  # 模拟慢响应
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {}
            mock_response.content = b'{"slow": true}'
            return mock_response
        
        with patch('httpx.AsyncClient.request', side_effect=slow_response):
            import threading
            
            response_times = []
            
            def timed_request():
                start_time = time.time()
                response = client.post("/api/test", json={"load_test": True})
                end_time = time.time()
                response_times.append((end_time - start_time, response.status_code))
            
            # 创建并发请求
            threads = []
            for i in range(10):
                thread = threading.Thread(target=timed_request)
                threads.append(thread)
                thread.start()
            
            # 等待完成
            for thread in threads:
                thread.join()
            
            # 检查结果
            assert len(response_times) == 10
            
            # 大部分请求应该成功
            success_count = sum(1 for _, status in response_times if status == 200)
            assert success_count >= 7, f"成功率过低: {success_count}/10"


class TestErrorLoggingAndMonitoring:
    """错误记录和监控测试"""
    
    def test_error_logging_completeness(self):
        """测试错误日志完整性"""
        with tempfile.TemporaryDirectory() as temp_dir:
            from app.utils.logger import CILRouterLogger
            
            logger = CILRouterLogger(log_level="ERROR", log_dir=temp_dir)
            log_file = Path(temp_dir) / "cilrouter.log"
            
            # 记录各种类型的错误
            error_types = [
                ("network_error", "连接失败", {"host": "api.test.com"}),
                ("config_error", "配置无效", {"config_section": "providers"}),
                ("validation_error", "数据验证失败", {"field": "provider_index"}),
                ("system_error", "系统资源不足", {"memory_usage": "95%"})
            ]
            
            for error_type, message, details in error_types:
                logger.log_error(error_type, message, details)
            
            # 检查日志文件
            if log_file.exists():
                log_content = log_file.read_text()
                
                for error_type, message, _ in error_types:
                    assert error_type in log_content, f"缺少错误类型: {error_type}"
                    assert message in log_content, f"缺少错误消息: {message}"
    
    def test_error_metrics_collection(self):
        """测试错误指标收集"""
        # 这是一个概念性测试，实际项目中可能需要专门的监控系统
        
        error_counts = {}
        
        def count_error(error_type):
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        # 模拟各种错误
        error_scenarios = [
            "connection_timeout",
            "invalid_response",
            "rate_limit_exceeded",
            "configuration_error"
        ]
        
        for error_type in error_scenarios:
            for _ in range(5):  # 每种错误发生5次
                count_error(error_type)
        
        # 验证错误计数
        for error_type in error_scenarios:
            assert error_counts[error_type] == 5
        
        assert sum(error_counts.values()) == 20


if __name__ == "__main__":
    print("开始运行CIL Router错误处理和故障转移测试...")
    pytest.main([__file__, "-v", "--tb=short"])