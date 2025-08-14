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
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
import json
import re
import asyncio

provider_lock = asyncio.Lock()
ALLOWED_HEADERS = {
    "authorization", "content-type", "accept", "user-agent",
    "accept-language", "accept-encoding",
    "anthropic-version", "anthropic-beta", "x-app"
}
RETRY_STATUS_CODES = {500, 502, 503, 504}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 只在启用时创建并启动
    rate_limit_config = config.get_rate_limit_config()
    rl = None
    if rate_limit_config["RATE_LIMIT_ENABLED"]:
        rl = RateLimiter(
            rpm=rate_limit_config["RATE_LIMIT_RPM"],  # 注意参数名是 rpm
            burst_size=rate_limit_config["RATE_LIMIT_BURST_SIZE"]
        )
        await rl.start()
        # 中间件此时才需要添加（拿到 rl 实例）
        app.add_middleware(
            RateLimitMiddleware,
            rate_limiter=rl,
            enabled=True,
            trust_proxy=rate_limit_config["RATE_LIMIT_TRUST_PROXY"]
        )
    try:
        yield
    finally:
        if rl:
            await rl.close()


app = FastAPI(title="CILRouter", description="Claude Code透明代理", version="1.0.2",
              docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/")
async def root():
    """根路径，返回当前状态"""
    current_provider_info = config.get_provider_info(config.CURRENT_PROVIDER_INDEX)
    return {
        "应用名称": "CIL Router",
        "当前版本": "1.0.2",
        "当前供应商": config.CURRENT_PROVIDER_INDEX,
        "全部供应商信息": config.get_all_providers_info(),
        "供应商端点数目": current_provider_info.get("供应商端点数目"),
        "供应商端点": current_provider_info.get("供应商端点", [])
    }


@app.post("/select")
async def select_provider(request: Request):
    """
    选择供应商接口
    POST 一个数字表示要使用的供应商索引
    """
    try:
        body = await request.body()
        index = int(body.decode().strip())
        if config.set_provider_index(index):
            return {
                "success": True,
                "message": f"已切换到供应商 {index}",
                "供应商信息": config.get_provider_info(index)
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"无效的供应商索引 {index}"
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="请求体必须是一个数字")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
async def forward_request(path: str, request: Request):
    """
    通用转发接口
    支持所有HTTP方法，完全透明转发
    智能处理API Key：如果请求中有Authorization头部则替换，没有则添加
    支持流式响应
    """
    try:
        # 鉴权检查
        auth_key = (config.get_request_config()["AUTH_KEY"]).strip()
        if auth_key:
            auth_header = (request.headers.get('authorization', '')).strip()
            if not auth_header.lower().startswith('bearer '):
                return
            if auth_header[7:] != auth_key:
                return

        # 请求方法
        method = request.method.upper()

        # 目标URL
        query_params = str(request.url.query)

        # 请求头
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() in ALLOWED_HEADERS
        }
        headers.pop('authorization', None)
        headers.pop('Authorization', None)
        # 请求体
        body = await request.body() if method in ["POST", "PUT", "PATCH"] else b""

        is_streaming = _is_streaming_request(headers, body)

        config.get_current_provider_endpoint()
        if is_streaming:
            return await _streaming_request(method, path, query_params, headers, body)
        else:
            return await normal_request(method, path, query_params, headers, body)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


def _is_streaming_request(headers: dict, body: bytes) -> bool:
    """
    判断是否为流式请求
    检查请求头中的Accept、Content-Type以及请求体中的stream参数
    """
    h = {k.lower(): v for k, v in headers.items()}
    accept = (h.get("accept") or "").lower()
    if "text/event-stream" in accept or "application/stream" in accept:
        return True

    if body:
        try:
            data = json.loads(body)
            # 只检查顶层的 stream 参数，避免误判嵌套对象中的stream
            if isinstance(data, dict):
                # 直接检查顶层 stream
                if data.get("stream") is True or str(data.get("stream")).lower() == "true":
                    return True
                # 检查 stream_options
                if "stream_options" in data and data["stream_options"] not in (None, False, {}, []):
                    return True
        except Exception:
            # 正则兜底 - 匹配顶层的stream参数
            if re.search(r'"stream"\s*:\s*(true|1|"true")', body.decode("utf-8", "ignore"), re.I):
                return True

    return False


async def _streaming_request(
        method: str,
        path: str,
        query_params: str,
        headers: dict,
        body: bytes,
):
    """
    简洁版：仅替换上游 key，透明流式转发；网络异常最多重试 3 次。
    假设上下游都规范（Content-Type/分块等正确）。
    """
    last_exc = None
    for attempt in range(3):
        # 1) 加锁获取端点
        async with provider_lock:
            ep = config.get_current_provider_endpoint()

        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if query_params:
            url = f"{url}?{query_params}"

        # 2) 补 Authorization
        up_headers = dict(headers)
        up_headers["authorization"] = f"Bearer {ep['api_key']}"
        up_headers.pop("host", None)

        try:
            timeout = httpx.Timeout(connect=10.0, read=None, write=10.0)
            async with httpx.AsyncClient(http2=True, timeout=timeout) as client:
                async with client.stream(method, url, headers=up_headers, content=body) as resp:
                    # 状态码检查
                    if resp.status_code in RETRY_STATUS_CODES and attempt < 2:
                        await resp.aclose()
                        await asyncio.sleep(2)
                        continue  # 直接进入下一次重试

                    # 正常流式透传
                    async def byte_iter():
                        async for chunk in resp.aiter_raw():
                            yield chunk

                    return StreamingResponse(
                        byte_iter(),
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                    )
        except Exception as e:
            last_exc = e
            continue

    raise HTTPException(status_code=502, detail=f"上游连接失败：{last_exc}")


async def normal_request(
        method: str,
        path: str,
        query_params: str,
        headers: dict,  # 白名单后的 headers，已去掉 Authorization
        body: bytes,
):
    """
    极简普通请求代理：
    - 加锁获取上游端点
    - 补 Authorization
    - 上游状态码在 RETRY_STATUS_CODES 内或网络异常时重试（最多 3 次）
    """
    last_exc = None
    for attempt in range(3):
        async with provider_lock:
            ep = config.get_current_provider_endpoint()

        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if query_params:
            url = f"{url}?{query_params}"

        up_headers = dict(headers)
        up_headers["authorization"] = f"Bearer {ep['api_key']}"
        up_headers.pop("host", None)

        try:
            timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0)
            async with httpx.AsyncClient(http2=True, timeout=timeout) as client:
                resp = await client.request(method, url, headers=up_headers, content=body)

                if resp.status_code in RETRY_STATUS_CODES and attempt < 2:
                    await asyncio.sleep(2)
                    continue  # 直接重试

                # 一次性读取全部内容并返回
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                )
        except Exception as e:
            last_exc = e
            continue

    raise HTTPException(status_code=502, detail=f"上游连接失败：{last_exc}")


# async def _handle_normal_request_with_retry(method: str, original_target_url: str, headers: dict,
#                                             request: Request) -> Response:
#     """
#     处理普通（非流式）请求，支持失败重试
#     """
#     # 获取请求体（只读取一次）
#     if method in ["POST", "PUT", "PATCH"]:
#         body = await request.body()
#     else:
#         body = None
#
#     # 获取当前供应商的所有端点数量
#     current_provider_info = config.get_provider_info(config.CURRENT_PROVIDER_INDEX)
#     max_retries = current_provider_info.get("endpoints_count", 1)
#
#     last_exception = None
#
#     for attempt in range(max_retries):
#         try:
#             # 为每次重试获取新的端点
#             if attempt > 0:
#                 provider = config.get_current_provider_endpoint()
#                 if not provider["base_url"] or not provider["api_key"]:
#                     continue
#
#                 # 更新请求头中的API Key
#                 headers["Authorization"] = f"Bearer {provider['api_key']}"
#
#                 # 重新构建URL
#                 path = original_target_url.split('/', 3)[-1] if '/' in original_target_url else ""
#                 base_url = provider['base_url'].rstrip('/')
#                 target_url = f"{base_url}/{path}"
#             else:
#                 target_url = original_target_url
#
#             return await _handle_normal_request(method, target_url, headers, request, body, attempt + 1)
#
#         except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
#             last_exception = e
#             print(f"⚠️ 请求失败 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
#             if attempt == max_retries - 1:
#                 break
#             continue
#         except Exception as e:
#             # 其他类型的异常不重试
#             raise e
#
#     # 所有重试都失败了
#     raise HTTPException(status_code=502, detail=f"所有端点都失败了: {str(last_exception)}")
# async def _handle_normal_request(method: str, target_url: str, headers: dict, request: Request, body: bytes = None,
#                                  attempt: int = 1) -> Response:
#     """
#     处理普通（非流式）请求
#     """
#     # 如果没有提供body，则获取请求体
#     if body is None and method in ["POST", "PUT", "PATCH"]:
#         body = await request.body()
#
#     # 记录请求详情
#     retry_info = f" (重试 {attempt})" if attempt > 1 else ""
#     print(f"🔄 转发请求{retry_info}: {method} {target_url}")
#     if attempt == 1:  # 只在第一次尝试时显示详细头部信息
#         print(f"📤 请求头: {dict((k, v[:50] + '...' if len(v) > 50 else v) for k, v in headers.items())}")
#     if body:
#         body_preview = body.decode('utf-8', errors='ignore')[:200] + ('...' if len(body) > 200 else '')
#         print(f"📤 请求体预览: {body_preview}")
#
#     # 发送请求
#     async with httpx.AsyncClient(timeout=httpx.Timeout(config.get_request_timeout())) as client:
#         response = await client.request(
#             method=method,
#             url=target_url,
#             headers=headers,
#             content=body
#         )
#
#         # 记录响应详情
#         print(f"📥 响应状态: {response.status_code}")
#         print(f"📥 响应头: {dict(response.headers)}")
#
#         # 如果不是200，记录错误详情
#         if response.status_code != 200:
#             error_content = response.text[:500] + ('...' if len(response.text) > 500 else '')
#             print(f"❌ 错误响应内容: {error_content}")
#         else:
#             success_preview = response.text[:200] + ('...' if len(response.text) > 200 else '')
#             print(f"✅ 成功响应预览: {success_preview}")
#
#         # 复制响应头部
#         response_headers = dict(response.headers)
#
#         # 移除可能导致问题的响应头部
#         response_headers.pop('content-encoding', None)
#         response_headers.pop('transfer-encoding', None)
#         response_headers.pop('content-length', None)
#
#         # 返回完全相同的响应
#         return Response(
#             content=response.content,
#             status_code=response.status_code,
#             headers=response_headers,
#             media_type=response_headers.get('content-type')
#         )
# async def _handle_streaming_request(method: str, target_url: str, headers: dict, request: Request) -> StreamingResponse:
#     """
#     处理流式请求
#     """
#     # 获取请求体
#     if method in ["POST", "PUT", "PATCH"]:
#         body = await request.body()
#     else:
#         body = None
#
#     async def stream_generator():
#         """
#         流式响应生成器
#         """
#         try:
#             async with httpx.AsyncClient(timeout=httpx.Timeout(config.get_stream_timeout())) as client:
#                 async with client.stream(
#                         method=method,
#                         url=target_url,
#                         headers=headers,
#                         content=body
#                 ) as response:
#                     # 流式传输响应内容
#                     async for chunk in response.aiter_bytes():
#                         if chunk:
#                             yield chunk
#         except Exception as e:
#             # 流式错误处理
#             error_msg = f"data: {{\"error\": \"Stream error: {str(e)}\"}}\n\n"
#             yield error_msg.encode()
#
#     # 设置流式响应头部
#     streaming_headers = {
#         "Cache-Control": "no-cache",
#         "Connection": "keep-alive",
#         "X-Accel-Buffering": "no",  # 禁用nginx缓冲
#     }
#
#     # 如果原请求期望特定的媒体类型，使用它
#     content_type = headers.get('accept', 'text/event-stream')
#     if 'application/json' in content_type:
#         content_type = 'text/event-stream'
#
#     return StreamingResponse(
#         stream_generator(),
#         media_type=content_type,
#         headers=streaming_headers
#     )


if __name__ == "__main__":
    import uvicorn

    server_config = config.get_server_config()
    print(f"🚀 启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}")
    print(f"📡 配置了 {len(config.get_all_providers_info())} 个供应商")
    print(f"🎯 当前使用供应商 {config.CURRENT_PROVIDER_INDEX}")
    uvicorn.run(app, host=server_config['HOST'], port=server_config['PORT'])
