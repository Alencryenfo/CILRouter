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
from typing import Optional
from urllib.parse import urlparse
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.utils.logger import init_logger, get_logger, truncate_model_content

# 创建 FastAPI 应用
app = FastAPI(title="CIL Router", version="1.0.2")

# 初始化日志模块
log_config = config.get_log_config()
init_logger(log_level=log_config["level"], log_dir=log_config["dir"])

# 初始化限流器和中间件
rate_limit_config = config.get_rate_limit_config()
ip_block_config = config.get_ip_block_config()
rate_limiter: Optional[RateLimiter] = None

# 如果限流或IP阻止任一功能启用，就添加中间件
if config.is_rate_limit_enabled() or config.is_ip_block_enabled():
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

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
HOP_BY_HOP = {
    'connection', 'keep-alive', 'proxy-connection', 'upgrade',
    'te', 'trailers',
}
def _strip_hop_by_hop_resp(h: dict):
    for k in list(h.keys()):
        kl = k.lower()
        if kl in HOP_BY_HOP or kl in {'content-length','transfer-encoding'}:
            h.pop(k, None)
def _strip_hop_by_hop(h: dict):
    for k in list(h.keys()):
        if k.lower() in HOP_BY_HOP:
            h.pop(k, None)
def _client_ip_for_logging(request: Request) -> str:
    """尽量还原真实客户端 IP（与中间件策略一致：优先代理头，回落到连接IP）"""
    try:
        trust_proxy = config.get_rate_limit_config().get("trust_proxy", True)
    except Exception:
        trust_proxy = True

    if trust_proxy:
        ip = request.headers.get("CF-Connecting-IP")
        if ip:
            return ip.strip()

        xff = request.headers.get("X-Forwarded-For")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first

        rip = request.headers.get("X-Real-IP")
        if rip:
            return rip.strip()

    # 直连或不信任代理时
    if request.client and getattr(request.client, "host", None):
        return request.client.host

    return "unknown-client"


@app.on_event("shutdown")
async def _shutdown_event() -> None:
    if rate_limiter:
        await rate_limiter.shutdown()


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
            client_ip = _client_ip_for_logging(request)
            logger.log_request_start(request, client_ip)

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
            client_ip = _client_ip_for_logging(request)
            logger.log_request_start(request, client_ip)

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

def build_target_url(base_url: str, forward_path: str, query: str) -> str:
    """将 provider.base_url 与客户端原始 forward_path 安全拼接，自动去重前缀。
    - base_url 可能形如: https://open.bigmodel.cn 或 https://open.bigmodel.cn/api/anthropic
    - forward_path 形如: "api/anthropic/v1/messages" 或 "v1/messages"
    - query 为原请求的查询串（不含开头 ?）
    """
    base = base_url.rstrip('/')
    p = '/' + forward_path.lstrip('/')

    base_path = urlparse(base).path.rstrip('/')  # e.g. "/api/anthropic"
    if base_path and p.startswith(base_path + '/'):
        # 避免重复：当 base 已含 "/api/anthropic"，而 forward_path 又以该前缀开头
        p = p[len(base_path):]  # 去掉重复前缀，保留从 "/v1/..." 开始的部分

    if query:
        return f"{base}{p}?{query}"
    return f"{base}{p}"

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
            scheme, _, token = auth_header.partition(' ')
            if scheme.lower() != 'bearer' or not token:
                raise HTTPException(status_code=401, detail="未提供有效的Authorization头部",
                                    headers={"WWW-Authenticate": "Bearer"})
            if token != config.get_auth_key():
                raise HTTPException(status_code=401, detail="无效的授权密钥",
                                    headers={"WWW-Authenticate": "Bearer"})
        # 获取当前供应商配置（使用负载均衡）
        provider = config.get_current_provider_endpoint()
        if not provider["base_url"] or not provider["api_key"]:
            raise HTTPException(status_code=503, detail="供应商配置不完整")

        # 获取原始请求数据
        headers = dict(request.headers)
        method = request.method.upper()
        query_params = str(request.url.query)

        # 移除可能干扰转发的头部
        for k in ['host', 'content-length', 'transfer-encoding']:
            headers.pop(k, None)
        _strip_hop_by_hop(headers)

        # 智能处理API Key：移除所有现有的认证头部，然后添加供应商的
        headers.pop('authorization', None)
        headers.pop('Authorization', None)
        headers["Authorization"] = f"Bearer {provider['api_key']}"

        body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
            except Exception as e:
                print(f"⚠️ 读取请求体失败: {str(e)}")
                body = b""

        logger = get_logger()
        if logger and body is not None:
            logger.log_request_body(body)

        is_streaming = _is_streaming_request(headers, body or b"")

        if is_streaming:
            return await _handle_streaming_request_with_retry(
                method, provider, path, query_params, headers, body
            )
        else:
            # >>> PATCH: 传入 forward_path 与 query，而不是 original_target_url
            return await _handle_normal_request_with_retry_and_body(
                method,
                provider,  # 首个端点
                path,  # forward_path（原始相对路径）
                query_params,  # 原始查询串
                headers,
                body
            )

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



async def _handle_normal_request_with_retry_and_body(
    method: str,
    first_provider: dict,
    forward_path: str,
    query: str,
    headers: dict,
    body: bytes = None
) -> Response:
    current_provider_info = config.get_provider_info(config.current_provider_index)
    max_retries = current_provider_info.get("endpoints_count", 1)

    last_exception = None
    provider = first_provider

    # 每次尝试从这份头部副本复制，避免跨尝试“串味”
    base_headers = headers.copy()

    for attempt in range(max_retries):
        try:
            # 选择端点 + 组装本次尝试用头部
            if attempt > 0:
                provider = config.get_current_provider_endpoint()
                if not provider.get("base_url") or not provider.get("api_key"):
                    raise RuntimeError("下一个端点配置不完整")

            attempt_headers = base_headers.copy()
            attempt_headers["Authorization"] = f"Bearer {provider['api_key']}"
            target_url = build_target_url(provider['base_url'], forward_path, query)

            # 发起一次请求（里层函数保持原有打印/日志逻辑）
            resp = await _handle_normal_request_without_request(
                method, target_url, attempt_headers, body, attempt + 1
            )

            # 命中可重试状态码且还有下一端点 → 重试
            if resp.status_code in RETRYABLE_STATUS and attempt < max_retries - 1:
                print(f"↻ 命中可重试状态码 {resp.status_code}，切换端点重试 (第 {attempt + 1}/{max_retries})")
                try:
                    await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))
                except Exception:
                    pass
                continue

            # 否则直接返回（包括最后一次仍是错误，也原样返回上游响应）
            return resp

        except Exception as e:
            last_exception = e
            err = type(e).__name__
            print(f"⚠️ 请求失败，尝试下个端点 (尝试 {attempt + 1}/{max_retries}) [{err}]: {str(e)}")
            if attempt == max_retries - 1:
                break
            try:
                await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))
            except Exception:
                pass
            continue

    # 所有端点都因异常失败（状态码错误已在上面 return 掉）
    raise HTTPException(status_code=502, detail=f"所有端点请求失败: {str(last_exception)}")


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

        response_headers = dict(response.headers)
        _strip_hop_by_hop_resp(response_headers)

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
        headers=response_headers,  # 保留其中的 content-type
        )



async def _handle_streaming_request_with_retry(
    method: str,
    first_provider: dict,
    forward_path: str,
    query: str,
    headers: dict,
    body: bytes | None = None
) -> StreamingResponse | Response:
    """
    流式请求重试：
    - 仅在拿到首包前重试：建连异常 / 非2xx且命中 RETRYABLE_STATUS
    - 一旦开始向下游写字节，不再重试
    - 上游状态码与响应头透传
    """
    current_provider_info = config.get_provider_info(config.current_provider_index)
    max_retries = current_provider_info.get("endpoints_count", 1)
    provider = first_provider
    last_err = None

    # 基础头（不添加 Idempotency-Key）
    base_headers = headers.copy()

    for attempt in range(max_retries):
        try:
            # 选端点 + 每次尝试使用 headers 副本，避免串味
            if attempt > 0:
                provider = config.get_current_provider_endpoint()
            if not provider.get("base_url") or not provider.get("api_key"):
                raise RuntimeError("端点配置不完整")

            attempt_headers = base_headers.copy()
            attempt_headers["Authorization"] = f"Bearer {provider['api_key']}"
            target_url = build_target_url(provider["base_url"], forward_path, query)

            client = httpx.AsyncClient(timeout=httpx.Timeout(config.get_stream_timeout()))
            cm = client.stream(method=method, url=target_url, headers=attempt_headers, content=body)
            response = await cm.__aenter__()

            status = response.status_code
            out_headers = dict(response.headers)
            out_headers = dict(response.headers)
            _strip_hop_by_hop_resp(out_headers)

            # 可重试状态码：关闭并切下一个端点
            if status in RETRYABLE_STATUS:

                if attempt < max_retries - 1:
                    await response.aclose()
                    await client.aclose()
                    await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))
                    continue
                # 无可用端点了：把上游错误体直接返回
                data = await response.aread()
                await response.aclose()
                await client.aclose()
                return Response(content=data, status_code=status, headers=out_headers)

            # 非重试型 4xx：直接透传
            if status >= 400:
                data = await response.aread()
                await response.aclose()
                await client.aclose()
                return Response(content=data, status_code=status, headers=out_headers)

            # 2xx：开始真正流式转发
            media_type = out_headers.get("content-type", "text/event-stream")
            logger = get_logger()
            stream_content = bytearray() if logger else None

            async def gen():
                nonlocal stream_content
                try:
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            if stream_content is not None:
                                stream_content.extend(chunk)
                            yield chunk
                finally:
                    if logger and stream_content:
                        content_bytes = bytes(stream_content)
                        try:
                            text = content_bytes.decode("utf-8")
                            if "data:" in text:
                                import re, json
                                def _tr(m):
                                    s = m.group(1)
                                    try:
                                        parsed = json.loads(s)
                                        truncated = truncate_model_content(parsed)
                                        return f"data: {json.dumps(truncated, ensure_ascii=False)}\n\n"
                                    except json.JSONDecodeError:
                                        return m.group(0)
                                text = re.sub(r"data: (.*?)\n\n", _tr, text, flags=re.DOTALL)
                            else:
                                import json
                                try:
                                    parsed = json.loads(text)
                                    text = json.dumps(truncate_model_content(parsed), ensure_ascii=False)
                                except json.JSONDecodeError:
                                    pass
                            logger.debug("流式响应完成", {
                                "type": "stream_response_complete",
                                "content": text,
                                "total_bytes": len(content_bytes)
                            })
                        except UnicodeDecodeError:
                            logger.debug("流式响应完成", {
                                "type": "stream_response_complete",
                                "content_type": "binary",
                                "total_bytes": len(content_bytes)
                            })
                        finally:
                            del stream_content
                    await response.aclose()
                    await client.aclose()

            return StreamingResponse(
                gen(),
                status_code=status,
                media_type=media_type,
                headers={
                    **out_headers,
                    "Cache-Control": out_headers.get("Cache-Control", "no-cache"),
                    "X-Accel-Buffering": "no",
                }
            )

        except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.HTTPError) as e:
            last_err = e
            if attempt < max_retries - 1:
                await asyncio.sleep(min(0.25 * (2 ** attempt), 2.0))
                continue
            break
        except Exception as e:
            last_err = e
            break

    error_data = {"error": {"type": "api_error", "message": f"Stream failed: {str(last_err)}"}}
    return Response(content=(json.dumps(error_data, ensure_ascii=False) + "\n").encode(),
                    status_code=502, media_type="application/json")





if __name__ == "__main__":
    import uvicorn
    server_config = config.get_server_config()
    print(f"🚀 启动 CIL Router 在 {server_config['host']}:{server_config['port']}")
    print(f"📡 配置了 {config.get_provider_count()} 个供应商")
    print(f"🎯 当前使用供应商 {config.current_provider_index}")
    uvicorn.run(app, host=server_config['host'], port=server_config['port'], access_log=False)