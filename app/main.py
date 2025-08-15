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


provider_lock = asyncio.Lock()
PROHIBIT_HEADERS = {
    # 逐跳 / 连接管理
    "authorization","Authorization",
    "host","Host",
    "connection","Connection",
    "keep-alive","Keep-Alive",
    "proxy-connection","Proxy-Connection",
    "transfer-encoding","Transfer-Encoding",
    "te","TE",
    "trailer","Trailer",
    "upgrade","Upgrade",

    # 长度 / 期望（交给 httpx 自己计算）
    "content-length","Content-Length",
    "expect","Expect",

    # CDN / 代理痕迹（固定名）
    "cdn-loop","CDN-Loop",
    "x-forwarded-for","X-Forwarded-For",
    "x-forwarded-proto","X-Forwarded-Proto",
    "x-forwarded-host","X-Forwarded-Host",
    "x-forwarded-server","X-Forwarded-Server",
    "x-forwarded-port","X-Forwarded-Port",
    "x-real-ip","X-Real-IP",
    "true-client-ip","True-Client-IP",
    "via","Via",
    "forwarded","Forwarded",
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

        # 请求头处理
        headers = dict(request.headers)
        for k in PROHIBIT_HEADERS:
            headers.pop(k, None)
        for k in list(headers.keys()):
            kl = k.lower()
            if kl.startswith(("cf-", "cf-access-")):
                headers.pop(k, None)


        body = await request.body() if method in ["POST", "PUT", "PATCH"] else b""

        print(method, path, query_params, headers, body[:50])
        return await _proxy_request(method, path, query_params, headers, body)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")

def _strip_hop_headers(h: dict) -> dict:
    return {k: v for k, v in h.items() if k.lower() not in HOP_HEADERS}
async def sse_passthrough(resp, ping_every: int = 25):
    """
    将上游 SSE 字节流逐字节回放；在上游静默超过 ping_every 秒时，注入合法心跳帧(: ping\\n\\n)。
    """
    q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1)

    async def reader():
        try:
            async for chunk in resp.aiter_bytes():
                # 若队列里已有旧数据就覆盖（避免堆积）
                if q.full():
                    try: q.get_nowait()
                    except asyncio.QueueEmpty: pass
                await q.put(chunk)
        finally:
            # 用 None 标记结束
            try: await q.put(None)
            except Exception: pass

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=ping_every)
            except asyncio.TimeoutError:
                # 上游静默：发一个 SSE 注释作为心跳
                yield b": ping\n\n"
                continue

            if item is None:
                break  # 上游结束
            yield item
    finally:
        reader_task.cancel()

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

            is_sse = "text/event-stream" in (resp.headers.get("content-type", "")).lower()

            async def byte_iter():
                try:
                    if is_sse:
                        async for chunk in sse_passthrough(resp, ping_every=25):
                            yield chunk
                    else:
                        async for chunk in resp.aiter_bytes():
                            yield chunk
                except (httpx.StreamClosed, httpx.ReadError,
                        httpx.RemoteProtocolError, anyio.EndOfStream,
                        anyio.ClosedResourceError, asyncio.CancelledError):
                    return
                finally:
                    try:
                        await resp_cm.__aexit__(None, None, None)
                    finally:
                        await client.aclose()

            handed_off = True  # 已把关闭责任交给生成器
            print(resp.status_code, resp.headers)
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
    uvicorn.run(app, host=server_config['HOST'], port=server_config['PORT'],http="h11", timeout_keep_alive=120,access_log=False)
