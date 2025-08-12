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
from urllib.parse import urlsplit
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.utils.logger import init_logger, get_logger

# 创建 FastAPI 应用
app = FastAPI(title="CIL Router", version="1.0.2")

# 初始化日志系统
log_config = config.get_log_config()
init_logger(log_level=log_config["level"], log_dir=log_config["dir"])

# 初始化限流器
rate_limiter = None
if config.is_rate_limit_enabled():
    rate_limit_config = config.get_rate_limit_config()
    rate_limiter = RateLimiter(
        requests_per_minute=rate_limit_config["requests_per_minute"],
        burst_size=rate_limit_config["burst_size"]
    )
    # 获取IP阻止配置
    ip_block_config = config.get_ip_block_config()
    
    # 添加限流中间件
    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=rate_limiter,
        enabled=True,
        trust_proxy=rate_limit_config["trust_proxy"],
        ip_block_enabled=ip_block_config["enabled"],
        blocked_ips_file=ip_block_config["blocked_ips_file"]
    )


@app.post("/select")
async def select_provider(request: Request):
    """
    选择供应商接口
    POST 一个数字表示要使用的供应商索引
    """
    logger = get_logger()
    old_index = config.current_provider_index
    
    try:
        # 获取请求体中的数字
        body = await request.body()
        if logger:
            logger.log_request_body(body)
        
        index = int(body.decode().strip())
        
        # 设置供应商索引
        if config.set_provider_index(index):
            if logger:
                logger.log_provider_switch(old_index, index, True)
            return {
                "success": True,
                "message": f"已切换到供应商 {index}",
                "current_index": index,
                "total_providers": config.get_provider_count()
            }
        else:
            if logger:
                logger.log_provider_switch(old_index, index, False)
                logger.log_error("provider_switch_error", f"无效的供应商索引 {index}")
            raise HTTPException(
                status_code=400,
                detail=f"无效的供应商索引 {index}，有效范围: 0-{config.get_provider_count() - 1}"
            )
    except ValueError as e:
        if logger:
            logger.log_error("provider_switch_value_error", "请求体必须是一个数字", {"error": str(e)})
        raise HTTPException(status_code=400, detail="请求体必须是一个数字")
    except HTTPException:
        # 重新抛出HTTPException，不要被通用异常捕获
        raise
    except Exception as e:
        if logger:
            logger.log_error("provider_switch_internal_error", f"内部错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.get("/")
async def root():
    """根路径，返回当前状态"""
    current_provider_info = config.get_provider_info(config.current_provider_index)
    return {
        "app": "CIL Router",
        "version": "1.0.2",
        "current_provider_index": config.current_provider_index,
        "total_providers": config.get_provider_count(),
        "current_provider_endpoints": current_provider_info.get("endpoints_count", 0),
        "current_provider_urls": current_provider_info.get("base_urls", []),
        "load_balancing": "round_robin"
    }


@app.get("/providers")
async def get_providers():
    """获取所有供应商的详细信息"""
    providers_info = config.get_all_providers_info()
    # 隐藏API Key信息
    for provider in providers_info:
        provider.pop("api_keys", None)  # 完全移除API Key信息
    return {
        "current_provider_index": config.current_provider_index,
        "providers": providers_info
    }


@app.options("/{path:path}")
async def cors_preflight(path: str, request: Request):
    """
    处理CORS预检请求，避免将OPTIONS请求转发到上游
    """
    allow_headers = request.headers.get("access-control-request-headers", "*")
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": allow_headers,
            "Access-Control-Max-Age": "600",
        },
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "TRACE"])
async def forward_request(path: str, request: Request):
    """
    通用转发接口
    支持所有HTTP方法，完全透明转发
    智能处理API Key：如果请求中有Authorization头部则替换，没有则添加
    支持流式响应
    """
    logger = get_logger()
    
    try:
        # 先取method变量，避免后面使用时未定义的问题
        method = request.method.upper()
        
        # 仅在需要时读取body（读一次）
        body = await request.body() if method in ["POST", "PUT", "PATCH"] else None
        if body and logger:
            logger.log_request_body(body)
        
        # 鉴权检查：如果启用了鉴权，验证Authorization头部
        if config.is_auth_enabled():
            auth_header = request.headers.get('authorization', '')
            if not auth_header.startswith('Bearer '):
                if logger:
                    logger.warning("鉴权失败：缺少Bearer token")
                # 静默拒绝的最接近做法：空体+403
                return Response(status_code=403, content=b"")

            provided_key = auth_header[7:]  # 移除 'Bearer ' 前缀
            if provided_key != config.get_auth_key():
                if logger:
                    logger.warning("鉴权失败：token无效")
                # 静默拒绝的最接近做法：空体+403
                return Response(status_code=403, content=b"")
        # 获取当前供应商配置（使用负载均衡）
        provider = config.get_current_provider_endpoint()
        if not provider["base_url"] or not provider["api_key"]:
            if logger:
                logger.error("供应商配置不完整")
            raise HTTPException(status_code=503, detail="供应商配置不完整")

        # 原始请求头拷贝并清洗
        headers = dict(request.headers)

        # 强制上游不压缩，避免解压错位问题（处理大小写重复键）
        for k in ('accept-encoding', 'Accept-Encoding'):
            headers.pop(k, None)
        headers['Accept-Encoding'] = 'identity'

        # 移除逐跳头（hop-by-hop headers）
        hop_by_hop_headers = [
            'host', 'content-length', 'transfer-encoding', 'connection', 'keep-alive',
            'proxy-connection', 'te', 'trailer', 'upgrade', 'expect'
        ]
        for hk in hop_by_hop_headers:
            headers.pop(hk, None)
            headers.pop(hk.title(), None)

        # 清洗认证类头部，防止冲突
        auth_headers = [
            'authorization', 'Authorization', 'x-api-key', 'X-Api-Key', 
            'api-key', 'Api-Key', 'x-authorization', 'X-Authorization',
            'proxy-authorization', 'Proxy-Authorization'
        ]
        for hk in auth_headers:
            headers.pop(hk, None)
        
        # 统一注入我们的认证
        headers["Authorization"] = f"Bearer {provider['api_key']}"

        # 目标URL（保留原 query）
        base_url = provider['base_url'].rstrip('/')
        # 用urlsplit拼原path+query
        split_req = urlsplit(str(request.url))
        target_url = f"{base_url}/{path}"
        if split_req.query:
            target_url = f"{target_url}?{split_req.query}"

        # 检查是否为流式请求
        is_streaming = _is_streaming_request(headers, body if body else b"")

        if is_streaming:
            # 处理流式请求（支持失败重试）
            return await _handle_streaming_request_with_retry(method, target_url, headers, request, body)
        else:
            # 处理普通请求（支持失败重试）
            return await _handle_normal_request_with_retry(method, target_url, headers, request, body)

    except httpx.HTTPError as e:
        if logger:
            logger.log_error("forward_http_error", f"转发请求失败: {str(e)}")
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")
    except Exception as e:
        if logger:
            logger.log_error("forward_internal_error", f"内部错误: {str(e)}")
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


async def _handle_normal_request_with_retry(method: str, original_target_url: str, headers: dict,
                                            request: Request, body: bytes = None) -> Response:
    """
    处理普通（非流式）请求，支持失败重试
    """
    # 使用传入的body参数，避免重复读取
    if body is None and method in ["POST", "PUT", "PATCH"]:
        body = await request.body()

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

                # 用urlsplit严格重建URL
                split_orig = urlsplit(original_target_url)
                base_url = provider['base_url'].rstrip('/')
                # 保留原path与query
                target_url = f"{base_url}{split_orig.path}"
                if split_orig.query:
                    target_url = f"{target_url}?{split_orig.query}"
            else:
                target_url = original_target_url

            return await _handle_normal_request(method, target_url, headers, body, attempt + 1)

        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_exception = e
            logger = get_logger()
            if logger:
                logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            else:
                print(f"⚠️ 请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                break
            continue
        except Exception as e:
            # 其他类型的异常不重试
            raise e

    # 所有重试都失败了
    logger = get_logger()
    if logger:
        logger.error(f"所有端点都失败了: {str(last_exception)}")
    raise HTTPException(status_code=502, detail=f"所有端点都失败了: {str(last_exception)}")


async def _handle_normal_request(method: str, target_url: str, headers: dict, body: bytes = None,
                                 attempt: int = 1) -> Response:
    """
    处理普通（非流式）请求
    """
    logger = get_logger()
    
    # 记录转发请求
    if logger:
        logger.log_forward_request(method, target_url, headers, body, attempt)
    else:
        # 如果没有日志，使用原来的控制台输出
        retry_info = f" (重试 {attempt})" if attempt > 1 else ""
        print(f"🔄 转发请求{retry_info}: {method} {target_url}")
        if attempt == 1:  # 只在第一次尝试时显示详细头部信息
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

        # 记录转发响应
        if logger:
            logger.log_forward_response(response.status_code, dict(response.headers), response.content)
        else:
            # 如果没有日志，使用原来的控制台输出
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

        # 移除逐跳头和可能导致问题的响应头部
        response_hop_headers = [
            'content-encoding', 'transfer-encoding', 'content-length', 
            'connection', 'keep-alive', 'proxy-connection', 'te', 'trailer', 'upgrade'
        ]
        for hk in response_hop_headers:
            response_headers.pop(hk, None)

        # 记录响应信息，处理media_type大小写问题
        content_type = response.headers.get("content-type") or response_headers.get("content-type")
        final_response = Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
            media_type=content_type
        )
        
        if logger:
            logger.log_response(final_response, response.content)
        
        # 返回完全相同的响应
        return final_response


async def _handle_streaming_request_with_retry(method: str, original_target_url: str, headers: dict,
                                               request: Request, body: bytes = None) -> StreamingResponse:
    """
    处理流式请求，支持失败重试
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
                
                # 用urlsplit严格重建URL
                split_orig = urlsplit(original_target_url)
                base_url = provider['base_url'].rstrip('/')
                # 保留原path与query
                target_url = f"{base_url}{split_orig.path}"
                if split_orig.query:
                    target_url = f"{target_url}?{split_orig.query}"
            else:
                target_url = original_target_url
            
            return await _handle_streaming_request(method, target_url, headers, body, attempt + 1)
            
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_exception = e
            logger = get_logger()
            if logger:
                logger.warning(f"流式请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            else:
                print(f"⚠️ 流式请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                break
            continue
        except Exception as e:
            # 其他类型的异常不重试
            raise e
    
    # 所有重试都失败了
    logger = get_logger()
    if logger:
        logger.error(f"所有流式端点都失败了: {str(last_exception)}")
    raise HTTPException(status_code=502, detail=f"所有流式端点都失败了: {str(last_exception)}")


async def _handle_streaming_request(method: str, target_url: str, headers: dict, body: bytes = None,
                                   attempt: int = 1) -> StreamingResponse:
    """
    处理流式请求
    """
    logger = get_logger()
    
    # 记录流式转发请求
    if logger:
        logger.log_forward_request(method, target_url, headers, body, attempt)
    else:
        # 如果没有日志，使用原来的控制台输出
        retry_info = f" (重试 {attempt})" if attempt > 1 else ""
        print(f"🔄 流式转发{retry_info}: {method} {target_url}")

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
                    # 记录流式响应开始
                    if logger:
                        logger.log_forward_response(response.status_code, dict(response.headers))
                    
                    # 如果是错误状态码，发送错误消息结束流
                    if response.status_code >= 400:
                        error_content = await response.aread()
                        error_text = error_content.decode('utf-8', errors='ignore')
                        msg = {
                            "error": f"HTTP {response.status_code}",
                            "detail": error_text[:200],
                            "status_code": response.status_code
                        }
                        error_msg = f"data: {json.dumps(msg, ensure_ascii=False)}\\n\\n"
                        yield error_msg.encode()
                        return
                    
                    # 流式传输响应内容
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except Exception as e:
            # 流式错误处理
            if logger:
                logger.log_error("streaming_error", f"Stream error: {str(e)}")
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
    uvicorn.run(app, host=server_config['host'], port=server_config['port'],access_log=False)