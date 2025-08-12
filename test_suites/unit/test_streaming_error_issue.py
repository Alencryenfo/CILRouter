#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试流式错误处理的格式兼容性问题
验证不同Content-Type下的错误响应格式
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import httpx

from app.main import app

client = TestClient(app)

class TestStreamingErrorFormat:
    """流式错误格式测试"""
    
    @patch('httpx.AsyncClient.stream')
    def test_sse_error_format_compatibility(self, mock_stream):
        """测试SSE格式错误的兼容性问题"""
        # 模拟连接错误
        mock_stream.side_effect = httpx.ConnectError("连接失败")
        
        # 测试不同的Accept头部
        test_cases = [
            {
                "accept": "text/event-stream",
                "description": "标准SSE请求",
                "expect_sse": True
            },
            {
                "accept": "application/json", 
                "description": "JSON流式请求",
                "expect_sse": False  # 但实际会返回SSE格式！
            },
            {
                "accept": "application/x-ndjson",
                "description": "NDJSON流式请求", 
                "expect_sse": False
            },
            {
                "accept": "text/plain",
                "description": "纯文本流式请求",
                "expect_sse": False
            }
        ]
        
        for case in test_cases:
            print(f"\n测试案例: {case['description']}")
            
            response = client.post(
                "/v1/messages",
                headers={"Accept": case["accept"]},
                json={"model": "claude-3", "stream": True, "messages": []}
            )
            
            print(f"响应状态码: {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type')}")
            
            if response.status_code == 200:
                content = response.text
                print(f"响应内容: {content[:200]}...")
                
                # 检查是否强制返回了SSE格式
                is_sse_format = content.startswith("data: ") and "\n\n" in content
                
                if case["expect_sse"]:
                    assert is_sse_format, f"期望SSE格式但收到: {content[:100]}"
                else:
                    # 这里会失败，因为代码强制返回SSE格式！
                    if is_sse_format:
                        print(f"❌ 问题确认: Accept为{case['accept']}但强制返回SSE格式")
                        print(f"   实际响应: {content[:100]}")
    
    @patch('httpx.AsyncClient.stream') 
    def test_claude_api_standard_compliance(self, mock_stream):
        """测试Claude API标准兼容性"""
        mock_stream.side_effect = httpx.TimeoutException("请求超时")
        
        # Claude API标准的JSON流式请求
        response = client.post(
            "/v1/messages",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-3-sonnet-20240229",
                "stream": True,
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100
            }
        )
        
        if response.status_code == 200:
            content = response.text
            print(f"Claude API响应: {content}")
            
            # 检查是否符合Claude API错误格式标准
            try:
                import json
                # 尝试解析为JSON
                error_data = json.loads(content)
                assert "error" in error_data, "缺少error字段"
                assert "type" in error_data["error"], "缺少error.type字段"
                print("✅ 符合Claude API标准")
            except json.JSONDecodeError:
                # 如果是SSE格式
                if content.startswith("data: "):
                    print("❌ 不符合Claude API标准，强制返回了SSE格式")
                    print(f"   应该返回JSON: {{'error': {{'type': 'timeout', 'message': '请求超时'}}}}")
    
    def test_error_format_inconsistency_demo(self):
        """演示错误格式不一致问题"""
        print("\n=== 错误格式不一致问题演示 ===")
        
        # 客户端期望的标准格式
        expected_json_error = {
            "error": {
                "type": "connection_error",
                "message": "Failed to connect to upstream"
            }
        }
        
        # 实际返回的SSE格式
        actual_sse_error = "data: {\"error\": \"Stream error: Connection failed\"}\n\n"
        
        print("客户端期望 (application/json):")
        import json
        print(json.dumps(expected_json_error, indent=2))
        
        print("\n实际返回 (强制SSE格式):")
        print(repr(actual_sse_error))
        
        print("\n问题分析:")
        print("1. 格式不匹配: JSON客户端无法解析SSE格式")
        print("2. 协议违反: 违反了HTTP Content-Type约定") 
        print("3. 兼容性问题: 与标准Claude API不兼容")


def demonstrate_correct_implementation():
    """演示正确的实现方式"""
    print("\n=== 建议的修复方案 ===")
    
    correct_code = '''
async def stream_generator():
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(...) as response:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
    except Exception as e:
        # 根据Accept头部返回相应格式的错误
        accept_header = headers.get('accept', '').lower()
        
        if 'text/event-stream' in accept_header:
            # SSE格式错误
            error_msg = f"data: {{\\"error\\": \\"Stream error: {str(e)}\\"}}\n\n"
            yield error_msg.encode()
        else:
            # JSON格式错误 (标准Claude API格式)
            error_data = {
                "error": {
                    "type": "stream_error",
                    "message": str(e)
                }
            }
            yield json.dumps(error_data).encode() + b"\n"
    '''
    
    print("修复要点:")
    print("1. 检查Accept头部决定错误格式")
    print("2. SSE请求返回SSE格式错误") 
    print("3. JSON请求返回JSON格式错误")
    print("4. 保持与Claude API标准一致")
    
    return correct_code


if __name__ == "__main__":
    print("🔍 流式错误处理兼容性问题测试")
    
    tester = TestStreamingErrorFormat()
    
    # 运行测试
    try:
        tester.test_sse_error_format_compatibility()
    except Exception as e:
        print(f"测试异常: {e}")
    
    try:
        tester.test_claude_api_standard_compliance()
    except Exception as e:
        print(f"测试异常: {e}")
    
    tester.test_error_format_inconsistency_demo()
    demonstrate_correct_implementation()