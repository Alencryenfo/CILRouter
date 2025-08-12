# -*- coding: utf-8 -*-
"""
CIL Router - 极简版 Claude API 转发器
支持所有HTTP方法，完全透明转发，智能处理API Key和流式请求
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, StreamingResponse
import httpx
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.utils.logger import init_logger, get_logger

# 创建 FastAPI 应用
app = FastAPI(title="CIL Router", version="1.0.2")

# 初始化日志模块
log_config = config.get_log_config()
init_logger(log_level=log_config["level"], log_dir=log_config["dir"])

# 初始化限流器和中间件
rate_limit_config = config.get_rate_limit_config()
ip_block_config = config.get_ip_block_config()

# 如果限流或IP阻止任一功能启用，就添加中间件
if config.is_rate_limit_enabled() or config.is_ip_block_enabled():
    rate_limiter = None
    if config.is_rate_limit_enabled():
        rate_limiter = RateLimiter(
            requests_per_minute=rate_limit_config["requests_per_minute"],
            burst_size=rate_limit_config["burst_size"]
        )
    else:
        # 即使不限流，也需要一个虚拟的限流器
        rate_limiter = RateLimiter(requests_per_minute=999999, burst_size=999999)
    
    # 添加中间件
    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=rate_limiter,
        enabled=config.is_rate_limit_enabled(),
        trust_proxy=rate_limit_config["trust_proxy"],
        ip_block_enabled=ip_block_config["enabled"],
        blocked_ips_file=ip_block_config["blocked_ips_file"]
    )


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    if 'rate_limiter' in globals() and rate_limiter:
        try:
            await rate_limiter.shutdown()
        except Exception:
            pass


@app.post("/select")
async def select_provider(request: Request):
    """
    选择供应商接口
    POST 一个数字表示要使用的供应商索引
    """
    logger = get_logger()
    try:
        # 获取请求体中的数字
        body = await request.body()
        old_index = config.current_provider_index
        
        # 记录请求体
        if logger:
            logger.log_request_body(body)
        try:
            body_str = body.decode('utf-8').strip()
        except UnicodeDecodeError:
            # 处理无法解码的二进制数据
            raise ValueError("请求体包含无效的字符编码")
        index = int(body_str)
        
        # 设置供应商索引
        if config.set_provider_index(index):
            # 记录成功切换
            if logger:
                logger.log_provider_switch(old_index, index, True)
            
            response_data = {
                "success": True, 
                "message": f"已切换到供应商 {index}",
                "current_index": index,
                "total_providers": config.get_provider_count()
            }
            
            # 记录响应体
            if logger:
                response_json = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
                from fastapi import Response as FastAPIResponse
                temp_response = FastAPIResponse(
                    content=response_json,
                    status_code=200
                )
                logger.log_response(temp_response, response_json)
            
            return response_data
        else:
            # 记录切换失败
            if logger:
                logger.log_provider_switch(old_index, index, False)
            
            raise HTTPException(
                status_code=400, 
                detail=f"无效的供应商索引 {index}，有效范围: 0-{config.get_provider_count()-1}"
            )
    except ValueError as ve:
        if logger:
            try:
                body_preview = body.decode('utf-8', errors='replace')[:100] if body else ""
            except:
                body_preview = f"<binary data: {len(body)} bytes>" if body else ""
            logger.log_error("provider_switch", str(ve), {"body": body_preview})
        raise HTTPException(status_code=400, detail=str(ve) if "字符编码" in str(ve) else "请求体必须是一个数字")
    except HTTPException:
        # HTTPException直接重新抛出，保持原有状态码和详情
        raise
    except Exception as e:
        if logger:
            logger.log_error("provider_switch", f"内部错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.get("/")
async def root(request: Request):
    """根路径，返回当前状态"""
    logger = get_logger()
    
    try:
        # 记录请求信息
        if logger:
            logger.log_request_start(request, "root")
        
        current_provider_info = config.get_provider_info(config.current_provider_index)
        response_data = {
            "app": "CIL Router",
            "version": "1.0.2",
            "current_provider_index": config.current_provider_index,
            "total_providers": config.get_provider_count(),
            "current_provider_endpoints": current_provider_info.get("endpoints_count", 0),
            "current_provider_urls": current_provider_info.get("base_urls", []),
            "load_balancing": "round_robin"
        }
        
        # 记录响应
        if logger:
            response_json = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            from fastapi import Response as FastAPIResponse
            temp_response = FastAPIResponse(
                content=response_json,
                status_code=200
            )
            logger.log_response(temp_response, response_json)
        
        return response_data
    
    except HTTPException:
        # HTTPException直接重新抛出，保持原有状态码和详情
        raise
    except Exception as e:
        if logger:
            logger.log_error("root", f"内部错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.get("/providers")
async def get_providers(request: Request):
    """获取所有供应商的详细信息"""
    logger = get_logger()
    
    try:
        # 记录请求信息
        if logger:
            logger.log_request_start(request, "providers")
        
        providers_info = config.get_all_providers_info()
        # 隐藏API Key信息
        for provider in providers_info:
            provider.pop("api_keys", None)  # 完全移除API Key信息
        
        response_data = {
            "current_provider_index": config.current_provider_index,
            "providers": providers_info
        }
        
        # 记录响应
        if logger:
            response_json = json.dumps(response_data, ensure_ascii=False).encode('utf-8')
            from fastapi import Response as FastAPIResponse
            temp_response = FastAPIResponse(
                content=response_json,
                status_code=200
            )
            logger.log_response(temp_response, response_json)
        
        return response_data
    
    except HTTPException:
        # HTTPException直接重新抛出，保持原有状态码和详情
        raise
    except Exception as e:
        if logger:
            logger.log_error("providers", f"内部错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")



@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
async def forward_request(path: str, request: Request):
    """
    通用转发接口
    支持所有HTTP方法，完全透明转发
    智能处理API Key：如果请求中有Authorization头部则替换，没有则添加
    支持流式响应
    """
    logger = get_logger()
    try:
        # 鉴权检查：如果启用了鉴权，验证Authorization头部
        if config.is_auth_enabled():
            auth_header = request.headers.get('authorization', '')
            if not auth_header.startswith('Bearer '):
                # 鉴权失败，返回401未授权
                raise HTTPException(
                    status_code=401, 
                    detail="未提供有效的Authorization头部",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            provided_key = auth_header[7:]  # 移除 'Bearer ' 前缀
            if provided_key != config.get_auth_key():
                # 鉴权失败，返回401未授权
                raise HTTPException(
                    status_code=401, 
                    detail="无效的授权密钥",
                    headers={"WWW-Authenticate": "Bearer"}
                )
        # 获取当前供应商配置（使用负载均衡）
        provider = config.get_current_provider_endpoint()
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
        
        # 预读取请求体（只读一次，后续所有处理都使用这个body）
        body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
            except Exception as e:
                print(f"⚠️ 读取请求体失败: {str(e)}")
                body = b""
        
        # 记录请求体
        if logger and body is not None:
            logger.log_request_body(body)
        
        # 检查是否为流式请求
        is_streaming = _is_streaming_request(headers, body or b"")
        
        if is_streaming:
            # 处理流式请求
            return await _handle_streaming_request_with_body(method, target_url, headers, body)
        else:
            # 处理普通请求（支持失败重试）
            return await _handle_normal_request_with_retry_and_body(method, target_url, headers, body)
            
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
            # 首先尝试判断是否为文本内容
            body_str = body.decode('utf-8', errors='ignore')
            
            # 检查content-type是否为JSON
            content_type = headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                # 只有确定是JSON时才尝试JSON解析
                try:
                    body_json = json.loads(body_str)
                    if isinstance(body_json, dict) and body_json.get('stream') is True:
                        return True
                except (json.JSONDecodeError, ValueError):
                    # JSON解析失败，fallback到字符串匹配
                    pass
            
            # 对所有文本内容使用字符串匹配（兼容性更好）
            if '"stream"' in body_str and ('"stream":true' in body_str.replace(' ', '') or 
                                         '"stream": true' in body_str):
                return True
        except UnicodeDecodeError:
            # 二进制数据无法解码为UTF-8，肯定不包含stream参数
            pass
        except Exception:
            # 其他异常也跳过
            pass
    
    return False


async def _handle_normal_request_with_retry_and_body(method: str, original_target_url: str, headers: dict, body: bytes = None) -> Response:
    """
    处理普通（非流式）请求，支持失败重试（使用预读取的body）
    """
    
    # 获取当前供应商的所有端点数量
    current_provider_info = config.get_provider_info(config.current_provider_index)
    max_retries = current_provider_info.get("endpoints_count", 1)
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            # 为每次重试获取新的端点
            if attempt > 0:
                provider = config.get_current_provider_endpoint()
                if not provider["base_url"] or not provider["api_key"]:
                    continue
                
                # 更新请求头中的API Key 
                headers["Authorization"] = f"Bearer {provider['api_key']}"
                
                # 重新构建URL，保持查询参数
                from urllib.parse import urlparse, urlunparse, parse_qs
                parsed_original = urlparse(original_target_url)
                
                # 提取路径和查询参数
                path = parsed_original.path.lstrip('/')  # 移除开头的/
                query = parsed_original.query
                
                # 构建新的URL
                base_url = provider['base_url'].rstrip('/')
                if query:
                    target_url = f"{base_url}/{path}?{query}"
                else:
                    target_url = f"{base_url}/{path}"
            else:
                target_url = original_target_url
            
            return await _handle_normal_request_without_request(method, target_url, headers, body, attempt + 1)
            
        except Exception as e:
            # 所有错误都重试，直到用完所有端点
            last_exception = e
            error_type = type(e).__name__
            print(f"⚠️ 请求失败，尝试下个端点 (尝试 {attempt + 1}/{max_retries}) [{error_type}]: {str(e)}")
            if attempt == max_retries - 1:
                break
            continue
    
    # 所有重试都失败了
    raise HTTPException(status_code=502, detail=f"所有端点都失败了: {str(last_exception)}")


async def _handle_normal_request_without_request(method: str, target_url: str, headers: dict, body: bytes = None, attempt: int = 1) -> Response:
    """
    处理普通（非流式）请求（使用预读取的body）
    """
    logger = get_logger()
    
    # 记录请求详情
    retry_info = f" (重试 {attempt})" if attempt > 1 else ""
    print(f"🔄 转发请求{retry_info}: {method} {target_url}")
    if attempt == 1:  # 只在第一次尝试时显示详细头部信息
        print(f"📤 请求头: {dict((k, v[:50] + '...' if len(v) > 50 else v) for k, v in headers.items())}")
    if body:
        body_preview = body.decode('utf-8', errors='ignore')[:200] + ('...' if len(body) > 200 else '')
        print(f"📤 请求体预览: {body_preview}")
    
    # 详细日志记录
    if logger:
        logger.log_forward_request(method, target_url, headers, body, attempt)
    
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
        
        # 详细日志记录响应
        if logger:
            logger.log_forward_response(response.status_code, dict(response.headers), response.content)
        
        # 复制响应头部
        response_headers = dict(response.headers)
        
        # 移除可能导致问题的响应头部
        response_headers.pop('content-encoding', None)
        response_headers.pop('transfer-encoding', None)
        response_headers.pop('content-length', None)
        
        # 记录响应体
        logger = get_logger()
        if logger:
            # 创建一个临时的Response对象用于日志记录
            from fastapi import Response as FastAPIResponse
            temp_response = FastAPIResponse(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers
            )
            logger.log_response(temp_response, response.content)
        
        # 返回完全相同的响应
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response_headers.get('content-type')
        )




async def _handle_streaming_request_with_body(method: str, target_url: str, headers: dict, body: bytes = None) -> StreamingResponse:
    """
    处理流式请求（使用预读取的body）
    """
    
    async def stream_generator():
        """
        流式响应生成器
        """
        logger = get_logger()
        max_preview = 10 * 1024  # 仅保留前10KB用于日志
        stream_preview = bytearray() if logger and logger.is_enabled() else None
        total_bytes = 0
        
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
                            total_bytes += len(chunk)
                            if stream_preview is not None and len(stream_preview) < max_preview:
                                slice_end = min(len(chunk), max_preview - len(stream_preview))
                                stream_preview.extend(chunk[:slice_end])
                            yield chunk

                    # 流式传输完成后记录内容预览
                    if logger and stream_preview:
                        try:
                            # 尝试解析为可读格式
                            content_text = stream_preview.decode('utf-8')
                            # 对于SSE流，清理格式以便阅读
                            if 'data: ' in content_text:
                                # 提取所有的data字段
                                import re
                                data_matches = re.findall(r'data: (.*?)\n\n', content_text, re.DOTALL)
                                if data_matches:
                                    # 尝试解析每个data块
                                    parsed_data = []
                                    for data_match in data_matches:
                                        try:
                                            parsed_json = json.loads(data_match)
                                            parsed_data.append(parsed_json)
                                        except json.JSONDecodeError:
                                            parsed_data.append(data_match)
                                    
                                    logger.debug("流式响应完成", {
                                        "type": "stream_response_complete",
                                        "total_chunks": len(bytes(stream_preview).split(b'data: ')),
                                        "parsed_data": parsed_data[:5],  # 只记录前5个块避免日志过长
                                        "total_bytes": total_bytes
                                    })
                                else:
                                    logger.debug("流式响应完成", {
                                        "type": "stream_response_complete",
                                        "content_preview": content_text[:500] + "..." if len(content_text) > 500 else content_text,
                                        "total_bytes": total_bytes
                                    })
                            else:
                                # 非SSE格式的流式响应
                                logger.debug("流式响应完成", {
                                    "type": "stream_response_complete",
                                    "content_preview": content_text[:500] + "..." if len(content_text) > 500 else content_text,
                                    "total_bytes": total_bytes
                                })
                        except UnicodeDecodeError:
                            # 二进制流式响应
                            logger.debug("流式响应完成", {
                                "type": "stream_response_complete",
                                "content_type": "binary",
                                "total_bytes": total_bytes
                            })
        except Exception as e:
            # 记录流式响应错误
            if logger:
                logger.error("流式响应失败", {
                    "type": "stream_response_error",
                    "error": str(e),
                    "target_url": target_url,
                    "method": method
                })
            
            # 统一使用Claude API标准的错误格式
            error_data = {
                "error": {
                    "type": "stream_error",
                    "message": f"Stream connection failed: {str(e)}"
                }
            }
            
            # 根据Accept头部决定错误响应格式
            accept_header = headers.get('accept', '').lower()
            
            if 'text/event-stream' in accept_header:
                # SSE格式错误 (Server-Sent Events)
                error_msg = f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
                yield error_msg.encode()
            else:
                # 默认使用NDJSON格式（符合Claude streaming API标准）
                yield (json.dumps(error_data, ensure_ascii=False) + "\n").encode()
    
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
    uvicorn.run(app, host=server_config['host'], port=server_config['port'], access_log=False)