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

from starlette.background import BackgroundTask
import anyio

provider_lock = asyncio.Lock()
ALLOWED_HEADERS = {
    "authorization", "content-type", "accept", "user-agent",
    "accept-language", "accept-encoding",
    "anthropic-version", "anthropic-beta", "x-app"
}
RETRY_STATUS_CODES = {500, 502, 503, 504}


rate_limit_config = config.get_rate_limit_config()
RATE_LIMIT_ENABLED = rate_limit_config["RATE_LIMIT_ENABLED"]
rl = RateLimiter(
    rpm=rate_limit_config["RATE_LIMIT_RPM"],
    burst_size=rate_limit_config["RATE_LIMIT_BURST_SIZE"]
) if RATE_LIMIT_ENABLED else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 2) 只在启用时启动/关闭 rl；不要在这里 add_middleware
    try:
        if rl:
            await rl.start()
        yield
    finally:
        if rl:
            await rl.close()

app = FastAPI(title="CILRouter", description="Claude Code透明代理", version="1.0.2",
              docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

app.add_middleware(
    RateLimitMiddleware,
    rate_limiter=rl,                            # 可能为 None；中间件内部需判断 enabled
    enabled=RATE_LIMIT_ENABLED,
    trust_proxy=rate_limit_config["RATE_LIMIT_TRUST_PROXY"]
)
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
                raise HTTPException(status_code=401, detail="缺少鉴权令牌")
            if auth_header[7:] != auth_key:
                raise HTTPException(status_code=401, detail="令牌无效")

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

        print(method, path, query_params, headers, body[:50])
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
    if "text/event-stream" in accept:
        return True

    if not body:
        return False

    try:
        data = json.loads(body)
        return isinstance(data, dict) and data.get("stream") is True
    except Exception:
        return False

def _strip_hop_headers(h: dict, drop_encoding: bool) -> dict:
    out = dict(h)
    # 逐跳/长度类：交给 Starlette 处理
    for k in ("transfer-encoding", "content-length", "connection", "keep-alive",
              "proxy-connection", "upgrade", "te", "trailer"):
        out.pop(k, None)
    if drop_encoding:
        # normal_request 用 resp.content（解压后），避免标错编码
        out.pop("content-encoding", None)
    return out

async def _streaming_request(
    method: str,
    path: str,
    query_params: str,
    headers: dict,
    body: bytes,
):
    """
    稳定的流式代理实现：
    - 加锁读取当前端点
    - 使用 aiter_bytes()（更稳，不直接暴露底层 raw）
    - 在生成器里吞掉上游/下游常见中断异常（不再把 httpx.StreamClosed 冒到 Starlette）
    - 使用 BackgroundTask 统一关闭 httpx.AsyncClient（避免在迭代中关闭 client）
    - 对 5xx 做最多 3 次重试；每次重试前重新加锁取端点
    """
    last_exc = None
    for attempt in range(3):
        # 1) 取端点加锁
        async with provider_lock:
            ep = config.get_current_provider_endpoint()

        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if query_params:
            url = f"{url}?{query_params}"

        # 2) 组装上游请求头
        up_headers = dict(headers)
        up_headers["authorization"] = f"Bearer {ep['api_key']}"
        up_headers.pop("host", None)

        # 3) httpx client —— 显式限制/超时；不让 httpx 自己重试，以免状态错乱
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        limits = httpx.Limits(max_keepalive_connections=100, max_connections=100)
        transport = httpx.AsyncHTTPTransport(retries=0)
        client = httpx.AsyncClient(http2=True, timeout=timeout, limits=limits, transport=transport)

        try:
            # 不要提前关闭 client；交给 BackgroundTask
            resp_cm = client.stream(method, url, headers=up_headers, content=body)
            async with resp_cm as resp:
                ct = (resp.headers.get("content-type") or "").lower()
                is_sse = "text/event-stream" in ct
                if not is_sse:
                    # 上游并非 SSE，直接当普通响应返回，避免流读时序问题
                    body_bytes = await resp.aread()
                    return Response(
                        content=body_bytes,
                        status_code=resp.status_code,
                        headers=_strip_hop_headers(resp.headers, drop_encoding=True),
                    )
                # 4) 遇 5xx 时重试
                if resp.status_code in RETRY_STATUS_CODES and attempt < 2:
                    # 不返回，让 for attempt 重来；client 由 finally/BackgroundTask 兜底
                    await asyncio.sleep(2)
                    continue

                async def byte_iter():
                    try:
                        # 用 aiter_bytes() 比 aiter_raw() 更“温和”，避免错误使用 raw 导致关闭异常
                        async for chunk in resp.aiter_bytes():
                            # 如果下游已经断开，Starlette 会取消发送任务，这里只需要优雅退出即可
                            yield chunk
                    except (httpx.StreamClosed,
                            httpx.ReadError,
                            httpx.RemoteProtocolError,
                            anyio.EndOfStream,
                            anyio.ClosedResourceError,
                            asyncio.CancelledError):
                        # 上游提前关闭、下游断开、连接被取消：都当作正常结束处理，别再向上抛
                        return
                    # 不在这里关闭 client，交给 BackgroundTask，避免与 resp 的上下文冲突

                print(f"[proxy] {method} /{path} ? {query_params} streaming=True")
                print(f"[proxy] upstream {url} -> {resp.status_code}")

                # 用 BackgroundTask 确保流结束后再关 client（无论正常还是异常）
                return StreamingResponse(
                    byte_iter(),
                    status_code=resp.status_code,
                    headers=_strip_hop_headers(resp.headers, drop_encoding=False),
                    background=BackgroundTask(client.aclose),
                )

        except Exception as e:
            last_exc = e
            # 发生连接/协议类异常，关闭 client，尝试重试
            try:
                await client.aclose()
            except Exception:
                pass
            if attempt < 2:
                await asyncio.sleep(2)
            continue

    # 三次尝试失败
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
            timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(http2=True, timeout=timeout) as client:
                resp = await client.request(method, url, headers=up_headers, content=body)

                if resp.status_code in RETRY_STATUS_CODES and attempt < 2:
                    await asyncio.sleep(2)
                    continue  # 直接重试
                print(f"[proxy] {method} /{path} ? {query_params} streaming=False")
                # 在两种请求返回前：
                print(f"[proxy] upstream {url} -> {resp.status_code}")
                # 一次性读取全部内容并返回
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=_strip_hop_headers(resp.headers, drop_encoding=True),
                )
        except Exception as e:
            last_exc = e
            if attempt < 2:
                await asyncio.sleep(2)
            continue

    raise HTTPException(status_code=502, detail=f"上游连接失败：{last_exc}")

if __name__ == "__main__":
    import uvicorn

    server_config = config.get_server_config()
    print(f"🚀 启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}")
    print(f"📡 配置了 {len(config.get_all_providers_info())} 个供应商")
    print(f"🎯 当前使用供应商 {config.CURRENT_PROVIDER_INDEX}")
    uvicorn.run(app, host=server_config['HOST'], port=server_config['PORT'])
