# -*- coding: utf-8 -*-
"""
CIL Router - 极简版 Claude API 转发器
支持所有HTTP方法，完全透明转发，智能处理API Key和流式请求
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, StreamingResponse
import httpx
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config

# 创建 FastAPI 应用
app = FastAPI(title="CIL Router", version="1.0.0")


@app.post("/select")
async def select_provider(request: Request):
    """
    选择供应商接口
    POST 一个数字表示要使用的供应商索引
    """
    try:
        # 获取请求体中的数字
        body = await request.body()
        index = int(body.decode().strip())
        
        # 设置供应商索引
        if config.set_provider_index(index):
            return {
                "success": True, 
                "message": f"已切换到供应商 {index}",
                "current_index": index,
                "total_providers": config.get_provider_count()
            }
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"无效的供应商索引 {index}，有效范围: 0-{config.get_provider_count()-1}"
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是一个数字")
    except HTTPException:
        # 重新抛出HTTPException，不要被通用异常捕获
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.get("/")
async def root():
    """根路径，返回当前状态"""
    provider = config.get_current_provider()
    return {
        "app": "CIL Router",
        "version": "1.0.0",
        "current_provider_index": config.current_provider_index,
        "total_providers": config.get_provider_count(),
        "current_provider_url": provider["base_url"]
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
async def forward_request(path: str, request: Request):
    """
    通用转发接口
    支持所有HTTP方法，完全透明转发
    智能处理API Key：如果请求中有Authorization头部则替换，没有则添加
    支持流式响应
    """
    try:
        # 鉴权检查：如果启用了鉴权，验证Authorization头部
        if config.is_auth_enabled():
            auth_header = request.headers.get('authorization', '')
            if not auth_header.startswith('Bearer '):
                # 鉴权失败，直接丢弃数据包，不返回任何响应
                return
            
            provided_key = auth_header[7:]  # 移除 'Bearer ' 前缀
            if provided_key != config.get_auth_key():
                # 鉴权失败，直接丢弃数据包，不返回任何响应
                return
        # 获取当前供应商配置
        provider = config.get_current_provider()
        if not provider["base_url"] or not provider["api_key"]:
            raise HTTPException(status_code=503, detail="供应商配置不完整")
        
        # 获取原始请求数据
        headers = dict(request.headers)
        method = request.method.upper()
        query_params = str(request.url.query)
        
        # 移除可能干扰转发的头部
        headers.pop('host', None)
        headers.pop('content-length', None)
        headers.pop('transfer-encoding', None)
        
        # 智能处理API Key：移除所有现有的认证头部，然后添加供应商的
        headers.pop('authorization', None)
        headers.pop('Authorization', None)
        headers["Authorization"] = f"Bearer {provider['api_key']}"
        
        # 构建完整的目标URL
        base_url = provider['base_url'].rstrip('/')
        if query_params:
            target_url = f"{base_url}/{path}?{query_params}"
        else:
            target_url = f"{base_url}/{path}"
        
        # 检查是否为流式请求
        is_streaming = _is_streaming_request(headers, await request.body() if method in ["POST", "PUT", "PATCH"] else b"")
        
        if is_streaming:
            # 处理流式请求
            return await _handle_streaming_request(method, target_url, headers, request)
        else:
            # 处理普通请求
            return await _handle_normal_request(method, target_url, headers, request)
            
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


def _is_streaming_request(headers: dict, body: bytes) -> bool:
    """
    判断是否为流式请求
    检查请求头中的Accept、Content-Type以及请求体中的stream参数
    """
    # 检查Accept头部是否包含流式类型
    accept = headers.get('accept', '').lower()
    if 'text/event-stream' in accept or 'application/stream' in accept:
        return True
    
    # 检查请求体中是否有stream参数
    if body:
        try:
            body_str = body.decode('utf-8', errors='ignore')
            if '"stream"' in body_str and '"stream":true' in body_str.replace(' ', ''):
                return True
        except:
            pass
    
    return False


async def _handle_normal_request(method: str, target_url: str, headers: dict, request: Request) -> Response:
    """
    处理普通（非流式）请求
    """
    # 获取请求体
    if method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    else:
        body = None
    
    # 记录请求详情
    print(f"🔄 转发请求: {method} {target_url}")
    print(f"📤 请求头: {dict((k, v[:50] + '...' if len(v) > 50 else v) for k, v in headers.items())}")
    if body:
        body_preview = body.decode('utf-8', errors='ignore')[:200] + ('...' if len(body) > 200 else '')
        print(f"📤 请求体预览: {body_preview}")
    
    # 发送请求
    async with httpx.AsyncClient(timeout=httpx.Timeout(config.get_request_timeout())) as client:
        response = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body
        )
        
        # 记录响应详情
        print(f"📥 响应状态: {response.status_code}")
        print(f"📥 响应头: {dict(response.headers)}")
        
        # 如果不是200，记录错误详情
        if response.status_code != 200:
            error_content = response.text[:500] + ('...' if len(response.text) > 500 else '')
            print(f"❌ 错误响应内容: {error_content}")
        else:
            success_preview = response.text[:200] + ('...' if len(response.text) > 200 else '')
            print(f"✅ 成功响应预览: {success_preview}")
        
        # 复制响应头部
        response_headers = dict(response.headers)
        
        # 移除可能导致问题的响应头部
        response_headers.pop('content-encoding', None)
        response_headers.pop('transfer-encoding', None)
        response_headers.pop('content-length', None)
        
        # 返回完全相同的响应
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response_headers.get('content-type')
        )


async def _handle_streaming_request(method: str, target_url: str, headers: dict, request: Request) -> StreamingResponse:
    """
    处理流式请求
    """
    # 获取请求体
    if method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    else:
        body = None
    
    async def stream_generator():
        """
        流式响应生成器
        """
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(config.get_stream_timeout())) as client:
                async with client.stream(
                    method=method,
                    url=target_url,
                    headers=headers,
                    content=body
                ) as response:
                    # 流式传输响应内容
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except Exception as e:
            # 流式错误处理
            error_msg = f"data: {{\"error\": \"Stream error: {str(e)}\"}}\n\n"
            yield error_msg.encode()
    
    # 设置流式响应头部
    streaming_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用nginx缓冲
    }
    
    # 如果原请求期望特定的媒体类型，使用它
    content_type = headers.get('accept', 'text/event-stream')
    if 'application/json' in content_type:
        content_type = 'text/event-stream'
    
    return StreamingResponse(
        stream_generator(),
        media_type=content_type,
        headers=streaming_headers
    )


if __name__ == "__main__":
    import uvicorn
    server_config = config.get_server_config()
    print(f"🚀 启动 CIL Router 在 {server_config['host']}:{server_config['port']}")
    print(f"📡 配置了 {config.get_provider_count()} 个供应商")
    print(f"🎯 当前使用供应商 {config.current_provider_index}")
    uvicorn.run(app, host=server_config['host'], port=server_config['port'])