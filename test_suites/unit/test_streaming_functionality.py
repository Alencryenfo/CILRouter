#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CIL Router 流式处理功能测试
测试流式响应、WebSocket、SSE等功能
"""

import pytest
import asyncio
import json
import time
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app, _is_streaming_request
import config.config as config

client = TestClient(app)

class TestStreamingDetection:
    """流式请求检测测试"""
    
    def test_streaming_detection_by_accept_header(self):
        """测试通过Accept头部检测流式请求"""
        # 测试各种流式Accept头部
        streaming_headers = [
            {"accept": "text/event-stream"},
            {"accept": "application/stream"},
            {"accept": "text/event-stream, application/json"},
            {"accept": "application/json, text/event-stream"},
            {"accept": "TEXT/EVENT-STREAM"},  # 大小写不敏感
        ]
        
        for headers in streaming_headers:
            body = b'{"test": "data"}'
            assert _is_streaming_request(headers, body) is True, f"应该检测为流式: {headers}"
        
        # 测试非流式头部
        non_streaming_headers = [
            {"accept": "application/json"},
            {"accept": "text/html"},
            {"accept": "*/*"},
            {"accept": "text/plain"},
        ]
        
        for headers in non_streaming_headers:
            body = b'{"test": "data"}'
            assert _is_streaming_request(headers, body) is False, f"不应该检测为流式: {headers}"
    
    def test_streaming_detection_by_request_body(self):
        """测试通过请求体检测流式请求"""
        headers = {}
        
        # 测试各种流式请求体
        streaming_bodies = [
            b'{"stream": true}',
            b'{"model": "gpt-4", "stream": true, "messages": []}',
            b'{"stream":true}',  # 无空格
            b'{"other": "data", "stream": true}',
            b'  {"stream": true}  ',  # 带空格
        ]
        
        for body in streaming_bodies:
            assert _is_streaming_request(headers, body) is True, f"应该检测为流式: {body}"
        
        # 测试非流式请求体
        non_streaming_bodies = [
            b'{"stream": false}',
            b'{"model": "gpt-4", "messages": []}',
            b'{"streaming": true}',  # 错误的字段名
            b'{"stream": "true"}',   # 字符串而非布尔值
            b'invalid json',
            b'',
        ]
        
        for body in non_streaming_bodies:
            assert _is_streaming_request(headers, body) is False, f"不应该检测为流式: {body}"
    
    def test_streaming_detection_combined_conditions(self):
        """测试组合条件的流式检测"""
        # Accept头部和请求体都指示流式
        headers = {"accept": "text/event-stream"}
        body = b'{"stream": true}'
        assert _is_streaming_request(headers, body) is True
        
        # 只有Accept头部指示流式
        headers = {"accept": "text/event-stream"}
        body = b'{"stream": false}'
        assert _is_streaming_request(headers, body) is True
        
        # 只有请求体指示流式
        headers = {"accept": "application/json"}
        body = b'{"stream": true}'
        assert _is_streaming_request(headers, body) is True


class TestStreamingRequestHandling:
    """流式请求处理测试"""
    
    @patch('httpx.AsyncClient.stream')
    def test_streaming_request_mock(self, mock_stream):
        """测试流式请求处理（使用Mock）"""
        # 模拟流式响应
        mock_response = Mock()
        async def mock_aiter_bytes():
            for chunk in [b'data: {"chunk": 1}\n\n', b'data: {"chunk": 2}\n\n', b'data: [DONE]\n\n']:
                yield chunk
        
        mock_response.aiter_bytes = mock_aiter_bytes
        
        mock_stream.return_value.__aenter__.return_value = mock_response
        
        # 发送流式请求
        response = client.post(
            "/v1/chat/completions",
            headers={"Accept": "text/event-stream"},
            json={"model": "test", "stream": True, "messages": []}
        )
        
        # 检查响应
        assert response.status_code in [200, 502]  # 可能成功或转发失败
    
    def test_streaming_headers_setup(self):
        """测试流式响应头部设置"""
        # 由于我们不能直接测试实际的流式响应，我们测试相关的逻辑
        from app.main import _handle_streaming_request_with_body
        
        # 这个测试主要确保函数存在且可调用
        assert callable(_handle_streaming_request_with_body)


class TestErrorHandlingInStreaming:
    """流式处理中的错误处理测试"""
    
    @patch('httpx.AsyncClient.stream')
    def test_streaming_error_handling(self, mock_stream):
        """测试流式处理中的错误处理"""
        import httpx
        
        # 模拟连接错误
        mock_stream.side_effect = httpx.ConnectError("连接失败")
        
        response = client.post(
            "/v1/chat/completions",
            headers={"Accept": "text/event-stream"},
            json={"model": "test", "stream": True}
        )
        
        # 应该返回错误状态码（流式错误在响应体中处理）
        assert response.status_code in [200, 502, 500]
    
    @patch('httpx.AsyncClient.stream')
    def test_streaming_timeout_handling(self, mock_stream):
        """测试流式处理中的超时处理"""
        import httpx
        
        # 模拟超时
        mock_stream.side_effect = httpx.TimeoutException("请求超时")
        
        response = client.post(
            "/v1/chat/completions", 
            headers={"Accept": "text/event-stream"},
            json={"model": "test", "stream": True}
        )
        
        # 应该返回错误状态码（流式错误在响应体中处理）
        assert response.status_code in [200, 502, 500]


class TestStreamingVsNormalRequestRouting:
    """流式与普通请求路由测试"""
    
    def test_normal_request_routing(self):
        """测试普通请求路由"""
        # 普通的JSON请求
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": []}
        )
        
        # 应该被路由到普通请求处理
        assert response.status_code in [200, 401, 502, 500]  # 取决于后端是否可用和API Key
    
    def test_streaming_request_routing(self):
        """测试流式请求路由"""
        # 流式请求
        response = client.post(
            "/v1/chat/completions",
            headers={"Accept": "text/event-stream"},
            json={"model": "test", "stream": True, "messages": []}
        )
        
        # 应该被路由到流式请求处理
        assert response.status_code in [200, 502, 500]


class TestStreamingPerformance:
    """流式处理性能测试"""
    
    def test_streaming_detection_performance(self):
        """测试流式检测的性能"""
        headers = {"accept": "text/event-stream"}
        body = b'{"stream": true, "model": "test"}'
        
        start_time = time.time()
        
        # 执行大量检测操作
        for _ in range(10000):
            _is_streaming_request(headers, body)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 检测应该很快
        assert duration < 1.0, f"流式检测性能过慢: {duration:.3f}秒"
        
        print(f"流式检测性能: {10000/duration:.0f} 次/秒")
    
    def test_large_body_streaming_detection(self):
        """测试大请求体的流式检测性能"""
        headers = {}
        
        # 创建包含大量数据的请求体
        large_data = {"messages": ["test message"] * 1000, "stream": True}
        body = json.dumps(large_data).encode()
        
        start_time = time.time()
        result = _is_streaming_request(headers, body)
        end_time = time.time()
        
        # 应该能正确检测
        assert result is True
        
        # 即使对大请求体，检测也应该相对快速
        duration = end_time - start_time
        assert duration < 0.1, f"大请求体检测过慢: {duration:.3f}秒"


class TestStreamingEdgeCases:
    """流式处理边界情况测试"""
    
    def test_malformed_streaming_body(self):
        """测试畸形流式请求体"""
        headers = {}
        
        malformed_bodies = [
            b'{"stream": tru',  # 不完整JSON
            b'{"stream": null}',  # null值
            b'{"stream": []}',   # 数组值
            b'{"stream": {}}',   # 对象值
            b'stream: true',     # 非JSON格式
        ]
        
        for body in malformed_bodies:
            # 应该能够处理而不崩溃
            try:
                result = _is_streaming_request(headers, body)
                assert isinstance(result, bool)
            except Exception as e:
                pytest.fail(f"处理畸形请求体时出错: {body} -> {e}")
    
    def test_empty_and_none_inputs(self):
        """测试空和None输入"""
        # 测试空头部和空请求体
        assert _is_streaming_request({}, b'') is False
        assert _is_streaming_request({}, b'{}') is False
        
        # 测试None值（虽然实际不太可能出现）
        try:
            _is_streaming_request({}, None)
        except (TypeError, AttributeError):
            # 预期的异常
            pass
    
    def test_unicode_in_streaming_detection(self):
        """测试Unicode字符在流式检测中的处理"""
        headers = {}
        
        unicode_bodies = [
            '{"stream": true, "content": "你好世界"}'.encode('utf-8'),
            '{"stream": true, "emoji": "🚀💯"}'.encode('utf-8'),
            '{"stream": true, "text": "Ελληνικά"}'.encode('utf-8'),
        ]
        
        for body in unicode_bodies:
            result = _is_streaming_request(headers, body)
            assert result is True
    
    def test_very_large_accept_header(self):
        """测试非常大的Accept头部"""
        # 创建一个很长的Accept头部
        large_accept = "application/json, " * 1000 + "text/event-stream"
        headers = {"accept": large_accept}
        
        result = _is_streaming_request(headers, b'{}')
        assert result is True  # 应该能检测到text/event-stream


class TestStreamingConfiguration:
    """流式处理配置测试"""
    
    def test_streaming_timeout_configuration(self):
        """测试流式超时配置"""
        stream_timeout = config.get_stream_timeout()
        request_timeout = config.get_request_timeout()
        
        # 流式超时应该比普通请求超时更长
        assert stream_timeout >= request_timeout
        assert stream_timeout > 0
        
        # 应该是合理的值（不会太小或太大）
        assert 10 <= stream_timeout <= 1800  # 10秒到30分钟之间


if __name__ == "__main__":
    print("开始运行CIL Router流式处理功能测试...")
    pytest.main([__file__, "-v", "--tb=short"])