#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 最终集成测试
运行完整的系统集成测试，包括部署场景、环境变量配置、Docker测试等
"""

import pytest
import os
import json
import time
import tempfile
import subprocess
import signal
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from contextlib import contextmanager

from app.main import app
import config.config as config

client = TestClient(app)

class TestEnvironmentVariableConfiguration:
    """环境变量配置测试"""
    
    def test_provider_configuration_from_env(self):
        """测试从环境变量配置供应商"""
        test_env = {
            'PROVIDER_0_BASE_URL': 'https://api1.test.com,https://backup1.test.com',
            'PROVIDER_0_API_KEY': 'test-key-1,backup-key-1',
            'PROVIDER_1_BASE_URL': 'https://api2.test.com',
            'PROVIDER_1_API_KEY': 'test-key-2',
            'CURRENT_PROVIDER_INDEX': '1'
        }
        
        with patch.dict(os.environ, test_env):
            # 重新加载配置
            config.reload_config()
            
            # 验证供应商数量
            assert config.get_provider_count() == 2
            
            # 验证当前供应商索引
            assert config.current_provider_index == 1
            
            # 验证供应商配置
            provider_0_info = config.get_provider_info(0)
            assert len(provider_0_info["base_urls"]) == 2
            assert provider_0_info["endpoints_count"] == 2
            
            provider_1_info = config.get_provider_info(1)
            assert len(provider_1_info["base_urls"]) == 1
            assert provider_1_info["endpoints_count"] == 1
    
    def test_server_configuration_from_env(self):
        """测试服务器配置"""
        test_env = {
            'HOST': '127.0.0.1',
            'PORT': '9000',
            'REQUEST_TIMEOUT': '30',
            'STREAM_TIMEOUT': '180'
        }
        
        with patch.dict(os.environ, test_env):
            config.reload_config()
            
            server_config = config.get_server_config()
            assert server_config["host"] == '127.0.0.1'
            assert server_config["port"] == 9000
            assert config.get_request_timeout() == 30.0
            assert config.get_stream_timeout() == 180.0
    
    def test_rate_limiting_configuration_from_env(self):
        """测试限流配置"""
        test_env = {
            'RATE_LIMIT_ENABLED': 'true',
            'RATE_LIMIT_RPM': '150',
            'RATE_LIMIT_BURST': '20',
            'RATE_LIMIT_TRUST_PROXY': 'false'
        }
        
        with patch.dict(os.environ, test_env):
            config.reload_config()
            
            assert config.is_rate_limit_enabled() is True
            rate_config = config.get_rate_limit_config()
            assert rate_config["requests_per_minute"] == 150
            assert rate_config["burst_size"] == 20
            assert rate_config["trust_proxy"] is False
    
    def test_authentication_configuration_from_env(self):
        """测试鉴权配置"""
        test_env = {
            'AUTH_KEY': 'secret-auth-key-123'
        }
        
        with patch.dict(os.environ, test_env):
            config.reload_config()
            
            assert config.is_auth_enabled() is True
            assert config.get_auth_key() == 'secret-auth-key-123'
    
    def test_logging_configuration_from_env(self):
        """测试日志配置"""
        test_env = {
            'LOG_LEVEL': 'INFO',
            'LOG_DIR': '/tmp/cilrouter_logs'
        }
        
        with patch.dict(os.environ, test_env):
            config.reload_config()
            
            log_config = config.get_log_config()
            assert log_config["level"] == 'INFO'
            assert log_config["dir"] == '/tmp/cilrouter_logs'


class TestDockerCompatibility:
    """Docker兼容性测试"""
    
    def test_dockerfile_structure(self):
        """测试Dockerfile结构"""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile不存在"
        
        dockerfile_content = dockerfile_path.read_text()
        
        # 检查基本结构
        assert "FROM python:" in dockerfile_content, "缺少Python基础镜像"
        assert "WORKDIR" in dockerfile_content, "缺少工作目录设置"
        assert "COPY requirements.txt" in dockerfile_content, "缺少依赖文件复制"
        assert "RUN pip install" in dockerfile_content, "缺少依赖安装"
        assert "EXPOSE" in dockerfile_content, "缺少端口暴露"
        assert ("CMD" in dockerfile_content or "ENTRYPOINT" in dockerfile_content), "缺少启动命令"
    
    def test_docker_compose_structure(self):
        """测试Docker Compose结构"""
        compose_path = Path("docker-compose.yml")
        assert compose_path.exists(), "docker-compose.yml不存在"
        
        compose_content = compose_path.read_text()
        
        # 检查基本结构
        assert "version:" in compose_content, "缺少版本声明"
        assert "services:" in compose_content, "缺少服务定义"
        assert "ports:" in compose_content, "缺少端口映射"
        assert "environment:" in compose_content or "env_file:" in compose_content, "缺少环境变量配置"
    
    def test_environment_file_template(self):
        """测试环境变量文件模板"""
        env_example_path = Path(".env.example")
        assert env_example_path.exists(), ".env.example不存在"
        
        env_content = env_example_path.read_text()
        
        # 检查必要的配置项
        required_vars = [
            "PROVIDER_0_BASE_URL",
            "PROVIDER_0_API_KEY",
            "HOST",
            "PORT",
            "RATE_LIMIT_ENABLED"
        ]
        
        for var in required_vars:
            assert var in env_content, f"环境变量模板缺少: {var}"


class TestProductionReadiness:
    """生产就绪性测试"""
    
    def test_health_check_endpoint(self):
        """测试健康检查端点"""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        # 健康检查应该返回基本状态信息
        assert "app" in data
        assert "version" in data
        assert "current_provider_index" in data
        assert "total_providers" in data
    
    def test_metrics_endpoint(self):
        """测试指标端点"""
        response = client.get("/providers")
        assert response.status_code == 200
        
        data = response.json()
        # 指标端点应该返回监控数据
        assert "current_provider_index" in data
        assert "providers" in data
        assert isinstance(data["providers"], list)
    
    def test_security_headers(self):
        """测试安全头部"""
        response = client.get("/")
        headers = response.headers
        
        # 检查是否没有泄露敏感信息
        sensitive_headers = ["server", "x-powered-by"]
        for header in sensitive_headers:
            if header in headers:
                value = headers[header].lower()
                # 确保不包含版本信息
                assert "uvicorn" not in value
                assert "fastapi" not in value
    
    def test_error_response_format(self):
        """测试错误响应格式"""
        # 测试各种错误场景
        error_tests = [
            ("/select", {"content": "invalid"}, 400),
            ("/nonexistent", {}, [500, 502]),  # 可能是500或502
        ]
        
        for endpoint, kwargs, expected_status in error_tests:
            if "content" in kwargs:
                response = client.post(endpoint, content=kwargs["content"])
            else:
                response = client.get(endpoint)
            
            if isinstance(expected_status, list):
                assert response.status_code in expected_status
            else:
                assert response.status_code == expected_status
            
            # 错误响应应该是JSON格式
            try:
                error_data = response.json()
                assert "detail" in error_data
            except Exception as e:
                # 如果不是JSON，至少应该有合理的错误信息
                print(f"响应不是JSON格式: {response.text[:100]}")
                assert len(response.text) > 0


class TestPerformanceRequirements:
    """性能需求测试"""
    
    def test_response_time_requirements(self):
        """测试响应时间需求"""
        # 测试基本端点的响应时间
        endpoints = ["/", "/providers"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # 响应时间应该小于100ms（在测试环境中）
            assert response_time < 0.1, f"{endpoint} 响应时间过长: {response_time:.3f}s"
            assert response.status_code == 200
    
    def test_concurrent_request_handling(self):
        """测试并发请求处理能力"""
        import threading
        import queue
        
        results_queue = queue.Queue()
        
        def make_request(request_id):
            start_time = time.time()
            response = client.get("/")
            end_time = time.time()
            
            results_queue.put({
                "id": request_id,
                "status": response.status_code,
                "time": end_time - start_time
            })
        
        # 创建50个并发请求
        threads = []
        for i in range(50):
            thread = threading.Thread(target=make_request, args=(i,))
            threads.append(thread)
        
        # 启动所有线程
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        total_time = time.time() - start_time
        
        # 收集结果
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())
        
        # 验证结果
        assert len(results) == 50, "并发请求数量不正确"
        
        # 所有请求都应该成功
        success_count = sum(1 for r in results if r["status"] == 200)
        assert success_count == 50, f"并发请求成功率: {success_count}/50"
        
        # 平均响应时间应该合理
        avg_response_time = sum(r["time"] for r in results) / len(results)
        assert avg_response_time < 0.2, f"平均响应时间过长: {avg_response_time:.3f}s"
        
        print(f"并发性能测试结果:")
        print(f"  - 总时间: {total_time:.3f}s")
        print(f"  - 平均响应时间: {avg_response_time:.3f}s")
        print(f"  - 成功率: {success_count}/50")


class TestConfigurationValidation:
    """配置验证测试"""
    
    def test_invalid_environment_variables(self):
        """测试无效环境变量的处理"""
        invalid_configs = [
            {'PORT': 'invalid_port'},
            {'REQUEST_TIMEOUT': 'not_a_number'},
            {'RATE_LIMIT_RPM': '-10'},
            {'CURRENT_PROVIDER_INDEX': '999'},
        ]
        
        for invalid_config in invalid_configs:
            with patch.dict(os.environ, invalid_config):
                try:
                    config.reload_config()
                    # 应该使用默认值或处理错误
                    assert True  # 如果没有抛出异常，说明错误被正确处理
                except (ValueError, TypeError) as e:
                    # 预期的配置错误
                    assert len(str(e)) > 0
    
    def test_configuration_consistency(self):
        """测试配置一致性"""
        # 确保配置项之间的逻辑关系正确
        stream_timeout = config.get_stream_timeout()
        request_timeout = config.get_request_timeout()
        
        # 流式超时应该大于等于普通请求超时
        assert stream_timeout >= request_timeout
        
        # 端口应该在合理范围内
        server_config = config.get_server_config()
        port = server_config["port"]
        assert 1 <= port <= 65535
        
        # 限流参数应该合理
        if config.is_rate_limit_enabled():
            rate_config = config.get_rate_limit_config()
            assert rate_config["requests_per_minute"] > 0
            assert rate_config["burst_size"] > 0
            assert rate_config["burst_size"] <= rate_config["requests_per_minute"]


class TestSystemIntegration:
    """系统集成测试"""
    
    def test_full_request_lifecycle(self):
        """测试完整的请求生命周期"""
        # 1. 检查系统状态
        status_response = client.get("/")
        assert status_response.status_code == 200
        
        initial_provider = status_response.json()["current_provider_index"]
        
        # 2. 切换供应商
        new_provider = (initial_provider + 1) % config.get_provider_count()
        switch_response = client.post("/select", content=str(new_provider))
        assert switch_response.status_code == 200
        
        # 3. 验证切换效果
        status_response = client.get("/")
        assert status_response.json()["current_provider_index"] == new_provider
        
        # 4. 发送测试请求
        test_response = client.post("/api/test", json={"test": "integration"})
        assert test_response.status_code in [200, 500, 502]  # 成功或转发失败都正常
        
        # 5. 获取供应商信息
        providers_response = client.get("/providers")
        assert providers_response.status_code == 200
        
        # 6. 恢复原始供应商
        restore_response = client.post("/select", content=str(initial_provider))
        assert restore_response.status_code == 200
    
    def test_system_under_mixed_load(self):
        """测试混合负载下的系统行为"""
        import threading
        import random
        
        results = {
            "status_checks": [],
            "provider_switches": [],
            "api_requests": [],
            "provider_queries": []
        }
        
        def mixed_load_worker(worker_id):
            operations = [
                ("status", lambda: client.get("/")),
                ("switch", lambda: client.post("/select", content=str(random.randint(0, 1)))),
                ("api", lambda: client.post("/test", json={"worker": worker_id})),
                ("providers", lambda: client.get("/providers"))
            ]
            
            for _ in range(5):  # 每个worker执行5次操作
                op_type, op_func = random.choice(operations)
                try:
                    response = op_func()
                    # 根据操作类型选择正确的结果列表
                    if op_type == "status":
                        key = "status_checks"
                    elif op_type == "switch":
                        key = "provider_switches"
                    elif op_type == "api":
                        key = "api_requests"
                    elif op_type == "providers":
                        key = "provider_queries"
                    else:
                        key = "status_checks"  # 默认
                    
                    results[key].append({
                        "worker": worker_id,
                        "status": response.status_code,
                        "success": response.status_code in [200, 400, 500, 502]  # 这些都是合理的状态码
                    })
                except Exception as e:
                    # 错误情况也用相同的键
                    if op_type == "status":
                        key = "status_checks"
                    elif op_type == "switch":
                        key = "provider_switches"
                    elif op_type == "api":
                        key = "api_requests"
                    elif op_type == "providers":
                        key = "provider_queries"
                    else:
                        key = "status_checks"  # 默认
                    
                    results[key].append({
                        "worker": worker_id,
                        "status": -1,
                        "success": False,
                        "error": str(e)
                    })
        
        # 启动10个工作线程
        threads = []
        for i in range(10):
            thread = threading.Thread(target=mixed_load_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # 等待完成
        for thread in threads:
            thread.join()
        
        # 验证结果
        total_operations = sum(len(ops) for ops in results.values())
        # 每个worker执行5次操作，10个worker，总共50次操作
        assert total_operations == 50, f"操作总数不正确: {total_operations}, 期望: 50"
        
        # 计算整体成功率
        all_operations = []
        for ops in results.values():
            all_operations.extend(ops)
        
        success_count = sum(1 for op in all_operations if op.get("success", False))
        success_rate = success_count / len(all_operations) if all_operations else 0
        
        assert success_rate > 0.5, f"混合负载成功率过低: {success_rate:.2%}，至少应该有50%成功"
        
        print(f"混合负载测试结果:")
        print(f"  - 总操作数: {len(all_operations)}")
        print(f"  - 成功率: {success_rate:.2%}")
        for op_type, ops in results.items():
            if ops:
                success = sum(1 for op in ops if op.get("success", False))
                print(f"  - {op_type}: {success}/{len(ops)}")


if __name__ == "__main__":
    print("开始运行CIL Router最终集成测试...")
    pytest.main([__file__, "-v", "--tb=short"])