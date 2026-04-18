# -*- coding: utf-8 -*-
import logging
import asyncio
from typing import AsyncIterator

import anyio
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.auth import is_passthrough_models_request, should_use_provider_authorization
from app.config import config
from app.constants import HOP_HEADERS, PROHIBIT_HEADERS, TRANSIENT_EXC
from app.http_client.http_pool import get_client_for
from app.log.logger import get_logger

router = APIRouter()
logger = get_logger()
SENSITIVE_HEADERS = {"cookie", "set-cookie"}
CORS_ALLOW_METHODS = "GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, TRACE"
CORS_FALLBACK_ALLOW_HEADERS = "Authorization, Content-Type"


def _strip_hop_headers(headers: httpx.Headers) -> list[tuple[bytes, bytes]]:
    return [
        (key.lower(), value)
        for key, value in headers.raw
        if key.decode("latin-1").lower() not in HOP_HEADERS
    ]


def _sanitize_headers_for_log(headers: dict) -> dict:
    return {
        k: ("***" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }


def _log_body_preview(level: int, message: str, *, IP: str, trace_id: str, info: str, **fields) -> None:
    if level == logging.DEBUG:
        logger.debug(message, IP=IP, trace_id=trace_id, 信息=info, **fields)
        return
    logger.info(message, IP=IP, trace_id=trace_id, 信息=info, **fields)


def _build_preflight_response(request: Request) -> Response:
    origin = request.headers.get("origin")
    requested_headers = request.headers.get("access-control-request-headers")

    response_headers = {
        "Access-Control-Allow-Origin": origin or "*",
        "Access-Control-Allow-Methods": CORS_ALLOW_METHODS,
        "Access-Control-Allow-Headers": requested_headers or CORS_FALLBACK_ALLOW_HEADERS,
        "Access-Control-Max-Age": "600",
    }

    vary_values = []
    if origin:
        vary_values.append("Origin")
    if requested_headers:
        vary_values.append("Access-Control-Request-Headers")
    if vary_values:
        response_headers["Vary"] = ", ".join(vary_values)

    return Response(status_code=204, headers=response_headers)


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"],
)
async def forward_request(path: str, request: Request):
    """通用透明转发，支持流式响应。"""
    IP = getattr(request.state, "ip", "unknown-client")
    trace_id = getattr(request.state, "trace_id", "")
    method = request.method.upper()
    logger.info(f"IP:{IP}访问端点 /{path}", IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path}")
    try:
        if method == "OPTIONS":
            logger.info(
                f"IP:{IP}访问端点 /{path}➡️处理浏览器预检请求，本地直接返回204",
                IP=IP,
                trace_id=trace_id,
                信息=f"访问端点 /{path} 处理浏览器预检请求",
            )
            return _build_preflight_response(request)

        passthrough = is_passthrough_models_request(path)
        incoming_authorization = request.headers.get("authorization", "").strip()
        auth_keys = config.get_request_config()["AUTH_KEYS"]
        use_provider_authorization = should_use_provider_authorization(
            path=path,
            incoming_authorization=incoming_authorization,
            auth_keys=auth_keys,
            IP=IP,
            trace_id=trace_id,
        )

        query_params = str(request.url.query)

        # 清洗请求头
        headers = {k: v for k, v in request.headers.items() if k.lower() not in PROHIBIT_HEADERS}
        headers = {k: v for k, v in headers.items() if not k.lower().startswith(("cf-", "cf-access-"))}

        if passthrough:
            logger.info(
                f"IP:{IP}访问端点 /{path}➡️特殊路由: 免鉴权访问，自动使用供应商鉴权请求上游",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 特殊路由处理",
            )

        logger.info(
            f"IP:{IP}访问端点 /{path}➡️转发请求➡️方法: {method}"
            f"{('，参数: ' + query_params) if query_params else ''}➡️请求头: {_sanitize_headers_for_log(headers)}➡️",
            IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求",
            请求头=_sanitize_headers_for_log(headers), 请求方法=method, 请求参数=query_params,
        )

        content_length = request.headers.get("content-length")
        has_body = (
            request.headers.get("transfer-encoding") is not None
            or (content_length is not None and content_length != "0")
        )

        if not has_body:
            logger.debug(
                f"IP:{IP}访问端点 /{path}➡️请求体为空",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 请求体为空",
            )
            body_stream = None
        else:
            async def body_iter() -> AsyncIterator[bytes]:
                preview = bytearray()
                total = 0
                async for chunk in request.stream():
                    if not chunk:
                        continue
                    if len(preview) < 200:
                        preview.extend(chunk[: 200 - len(preview)])
                    total += len(chunk)
                    yield chunk
                if total:
                    preview_text = preview.decode("utf-8", "replace")
                    _log_body_preview(
                        logging.DEBUG,
                        f"IP:{IP}访问端点 /{path}➡️请求体: {preview_text}... (总长度: {total} bytes)",
                        IP=IP, trace_id=trace_id, info=f"访问端点 /{path} 请求体",
                        请求体=preview_text, 总长度=total,
                    )
                else:
                    logger.debug(
                        f"IP:{IP}访问端点 /{path}➡️请求体为空",
                        IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 请求体为空",
                    )
            body_stream = body_iter()

        return await _proxy_request(
            method, path, query_params, headers, body_stream,
            allow_retries=not has_body,
            IP=IP, trace_id=trace_id,
            use_provider_authorization=use_provider_authorization,
        )

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        logger.error(
            f"IP:{IP}访问端点 /{path}➡️转发请求失败: {type(e).__name__}: {e}",
            IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求失败: {type(e).__name__}: {e}",
        )
        raise HTTPException(status_code=502, detail={"信息": f"转发请求失败: {type(e).__name__}: {e}", "跟踪ID": trace_id})
    except Exception as e:
        logger.error(
            f"IP:{IP}访问端点 /{path}➡️转发请求失败: {type(e).__name__}: {e}",
            IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求失败: {type(e).__name__}: {e}",
        )
        raise HTTPException(status_code=500, detail={"信息": f"内部错误: {type(e).__name__}: {e}", "跟踪ID": trace_id})


async def _proxy_request(
    method: str,
    path: str,
    query_params: str,
    headers: dict,
    body: AsyncIterator[bytes] | None,
    allow_retries: bool,
    IP: str,
    trace_id: str,
    use_provider_authorization: bool,
):
    last_exc = None
    attempts = 3 if allow_retries else 1
    request_config = config.get_request_config()
    timeout = httpx.Timeout(
        connect=5.0,
        read=request_config["STREAM_TIMEOUT"],
        write=request_config["REQUEST_TIMEOUT"],
        pool=5.0,
    )

    for attempt in range(1, attempts + 1):
        ep = config.get_current_provider_endpoint()

        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if query_params:
            url = f"{url}?{query_params}"

        up_headers = dict(headers)
        if use_provider_authorization:
            logger.info(
                f"IP:{IP}访问端点 /{path}➡️转发请求分配端点: {base_url}，Authorization: 供应商鉴权",
                IP=IP, trace_id=trace_id,
                信息=f"访问端点 /{path} 转发请求分配端点: {base_url}，使用供应商鉴权",
            )
            up_headers["authorization"] = f"Bearer {ep['api_key']}"
        else:
            logger.info(
                f"IP:{IP}访问端点 /{path}➡️转发请求分配端点: {base_url}，Authorization: 不携带",
                IP=IP, trace_id=trace_id,
                信息=f"访问端点 /{path} 转发请求分配端点: {base_url}",
            )
        up_headers["accept-encoding"] = "identity"

        client = await get_client_for(base_url)
        resp_cm = None
        entered = False
        returned = False

        try:
            resp_cm = client.stream(method, url, headers=up_headers, content=body, timeout=timeout)
            resp = await resp_cm.__aenter__()
            entered = True
            logger.info(
                f"IP:{IP}访问端点 /{path}➡️转发请求响应头: {_sanitize_headers_for_log(dict(resp.headers))}➡️响应状态: {resp.status_code}",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求响应",
                响应头=_sanitize_headers_for_log(dict(resp.headers)), 响应状态=resp.status_code,
            )

            async def byte_iter():
                try:
                    first = b""
                    last = b""
                    length = 0
                    async for chunk in resp.aiter_bytes():
                        if not first and chunk:
                            first = chunk[:200]
                        last = (last + chunk)[-200:]
                        length += len(chunk)
                        yield chunk
                    if first or last:
                        _log_body_preview(
                            logging.DEBUG,
                            f"IP:{IP}访问端点 /{path}➡️转发请求响应体: "
                            f"➡️{first.decode('utf-8', 'replace')}......{last.decode('utf-8', 'replace')}⬅️",
                            IP=IP, trace_id=trace_id, info=f"访问端点 /{path} 转发请求响应体",
                            响应体=f"{first.decode('utf-8', 'replace')}......{last.decode('utf-8', 'replace')}",
                            总长度=length,
                        )
                    else:
                        logger.debug(
                            f"IP:{IP}访问端点 /{path}➡️转发请求响应体为空",
                            IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求响应体为空",
                        )
                except (
                    httpx.StreamClosed, httpx.ReadError, httpx.RemoteProtocolError,
                    httpx.ReadTimeout, anyio.EndOfStream, anyio.ClosedResourceError,
                    anyio.BrokenResourceError,
                    ConnectionResetError, BrokenPipeError,
                ) as e:
                    logger.warning(
                        f"IP:{IP}访问端点 /{path}➡️发生错误，流式中断: {type(e).__name__}: {e}",
                        IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 发生错误，流式中断: {type(e).__name__}: {e}",
                    )
                except asyncio.CancelledError:
                    logger.info(
                        f"IP:{IP}访问端点 /{path}➡️客户端已断开连接，结束流式转发",
                        IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 客户端已断开连接",
                    )
                    raise
                finally:
                    try:
                        await resp_cm.__aexit__(None, None, None)
                    except Exception:
                        pass

            returned = True
            response = StreamingResponse(
                byte_iter(),
                status_code=resp.status_code,
            )
            response.raw_headers = _strip_hop_headers(resp.headers)
            return response

        except TRANSIENT_EXC as e:
            if entered and resp_cm is not None and not returned:
                try:
                    await resp_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            logger.warning(
                f"❌IP:{IP}访问端点 /{path}➡️转发请求失败: {type(e).__name__}: {e}",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求失败: {type(e).__name__}: {e}",
            )
            last_exc = e
        except Exception as e:
            if entered and resp_cm is not None and not returned:
                try:
                    await resp_cm.__aexit__(None, None, None)
                except Exception:
                    pass
            logger.warning(
                f"❌IP:{IP}访问端点 /{path}➡️转发请求失败: {type(e).__name__}: {e}",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求失败: {type(e).__name__}: {e}",
            )
            last_exc = e

        if attempt < attempts:
            logger.warning(
                f"❌IP:{IP}访问端点 /{path}➡️转发请求失败，开始重试第 {attempt + 1} 次",
                IP=IP, trace_id=trace_id, 信息=f"访问端点 /{path} 转发请求失败，开始重试第 {attempt + 1} 次",
            )
            await asyncio.sleep(0.8 * (2 ** (attempt - 1)))

    logger.error(
        f"IP:{IP}访问端点 /{path}➡️转发请求失败，上游连接失败: {type(last_exc).__name__}: {last_exc}",
        IP=IP, trace_id=trace_id,
        信息=f"访问端点 /{path} 转发请求失败，上游连接失败: {type(last_exc).__name__}: {last_exc}",
    )
    raise HTTPException(
        status_code=502,
        detail={"信息": f"上游连接失败: {type(last_exc).__name__}: {last_exc}", "跟踪ID": trace_id},
    )
