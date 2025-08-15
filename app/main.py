# -*- coding: utf-8 -*-
"""
CIL Router - 极简版 Claude API 转发器
支持所有HTTP方法，完全透明转发，智能处理API Key和流式请求
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import  StreamingResponse
import httpx
import sys
import os
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config.config as config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
import anyio
import asyncio

from starlette.background import BackgroundTask


provider_lock = asyncio.Lock()
ALLOWED_HEADERS = {
    "authorization", "content-type", "accept", "user-agent",
    "accept-language", "accept-encoding",
    "anthropic-version", "anthropic-beta", "x-app"
}

HOP_HEADERS = ("transfer-encoding","content-length","connection","keep-alive",
               "proxy-connection","upgrade","te","trailer")

TRANSIENT_EXC = (
    httpx.ConnectError, httpx.ConnectTimeout,
    httpx.ReadTimeout, httpx.ReadError,
    httpx.RemoteProtocolError, httpx.PoolTimeout,
)

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
        headers = dict(request.headers)

        # 仅删除这些不应转发/必须由我们接管的头；其余一律保留
        for k in (
                "authorization", "Authorization",  # 来路鉴权，交给上游 Key
                "host", "Host",  # Host 由 httpx/HTTP2 的 :authority 处理
                "connection", "Connection",
                "keep-alive", "Keep-Alive",
                "proxy-connection", "Proxy-Connection",
                "transfer-encoding", "Transfer-Encoding",
                "te", "TE",
                "trailer", "Trailer",
                "upgrade", "Upgrade",
        ):
            headers.pop(k, None)
        # 请求体
        body = await request.body() if method in ["POST", "PUT", "PATCH"] else b""

        print(method, path, query_params, headers, body[:50])
        return await _proxy_request(method, path, query_params, headers, body)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")

def _strip_hop_headers(h: dict) -> dict:
    return {k: v for k, v in h.items() if k.lower() not in HOP_HEADERS}

async def _proxy_request(method: str, path: str, query_params: str, headers: dict, body: bytes):
    last_exc = None
    attempts = 3

    for attempt in range(1, attempts + 1):
        async with provider_lock:
            ep = config.get_current_provider_endpoint()

        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if query_params:
            url = f"{url}?{query_params}"

        up_headers = dict(headers)
        up_headers["authorization"] = f"Bearer {ep['api_key']}"

        timeout   = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        limits    = httpx.Limits(max_keepalive_connections=100, max_connections=100, keepalive_expiry=30.0)
        transport = httpx.AsyncHTTPTransport(http2=False, retries=0)
        client    = httpx.AsyncClient(timeout=timeout, limits=limits, transport=transport)

        handed_off = False  # 关键：标记是否已把关闭责任交给生成器
        try:
            resp_cm = client.stream(method, url, headers=up_headers, content=body)
            resp = await resp_cm.__aenter__()

            async def byte_iter():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                except (httpx.StreamClosed, httpx.ReadError,
                        httpx.RemoteProtocolError, anyio.EndOfStream,
                        anyio.ClosedResourceError, asyncio.CancelledError):
                    return
                finally:
                    # 生成器结束时再统一收尾
                    try:
                        await resp_cm.__aexit__(None, None, None)
                    finally:
                        await client.aclose()

            handed_off = True  # 已把关闭责任交给生成器
            return StreamingResponse(
                byte_iter(),
                status_code=resp.status_code,
                headers=_strip_hop_headers(resp.headers),
            )

        except TRANSIENT_EXC as e:
            last_exc = e
        except Exception as e:
            last_exc = e
        finally:
            # 只有在“没有交付流”的情况下，才由这里关闭资源
            if not handed_off:
                try:
                    await client.aclose()
                except Exception:
                    pass

        if attempt < attempts:
            await asyncio.sleep(0.8 * (2 ** (attempt - 1)))

    raise HTTPException(status_code=502, detail=f"上游连接失败：{last_exc}")

if __name__ == "__main__":
    import uvicorn

    server_config = config.get_server_config()
    print(f"🚀 启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}")
    print(f"📡 配置了 {len(config.get_all_providers_info())} 个供应商")
    print(f"🎯 当前使用供应商 {config.CURRENT_PROVIDER_INDEX}")
    uvicorn.run(app, host=server_config['HOST'], port=server_config['PORT'])
