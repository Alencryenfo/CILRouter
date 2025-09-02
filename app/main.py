"""
最简洁的转发版主程序：
- 仅保留根路由和通用转发
- 复用 httpx 连接池，按当前供应商转发
- 移除限流与复杂日志采样
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import config
from app.http_client.http_pool import get_client_for, close_all_clients
from app.middleware.anti_abuse import RateLimiter, AntiAbuseMiddleware
from app.middleware.request_prep import RequestPrepMiddleware


# 响应侧需要移除的头（与旧版相同）
HOP_HEADERS = (
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-connection",
    "upgrade",
    "te",
    "trailer",
    "content-encoding",
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_all_clients()

app = FastAPI(title="CILRouter", description="极简透明转发", version="1.1.0",
              docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# 公共放行路径/前缀（最小化：仅首页与图标）
PUBLIC_EXACT = {"/", "/favicon.ico"}
PUBLIC_PREFIX = {}
"""
- 公共精确路径 PUBLIC_EXACT: 精确匹配放行。只在路径完全等于集合中的某一项时放行。例：
    - "/" 仅放行根路径；
    - "/favicon.ico" 不放行 "/favicon.ico/" 或 "/favicon.ico?v=1" 的路径部分（查询串不参与匹配）。
    - "/favicon.ico" 不放行 "/favicon.ico/" 或 "/favicon.ico?v=1" 的路径部分（查询串不参与匹配）。
- 
公共前缀 PUBLIC_PREFIX: 前缀匹配放行。只要请求路径以其中任一前缀开头即放行。例：
    - ("/metrics",) 放行 "/metrics"、"/metrics/"、"/metrics/a/b"，但不放行 "/metric"。
    - 注意不要用 "/" 作为前缀，否则等于放行全部路径。
- 
适用场景
    - 用 PUBLIC_EXACT 放行固定路径，如 "/"、"/health"、"/favicon.ico"。
    - 用 PUBLIC_PREFIX 放行一组接口，如 "/docs"、"/static/"、"/metrics" 整段。
- 
组合逻辑
    - 命中任一即可放行：先检查是否在 PUBLIC_EXACT，再检查是否 startswith 任一 PUBLIC_PREFIX。
"""
# 反滥用配置
rate_limit_config = config.get_rate_limit_config()
app.add_middleware(
    AntiAbuseMiddleware,
    rate_limiter=RateLimiter(
        rpm=rate_limit_config["RATE_LIMIT_RPM"],
        burst_size=rate_limit_config["RATE_LIMIT_BURST"]
    ),
    enabled=rate_limit_config["RATE_LIMIT_ENABLED"],
    trust_proxy=rate_limit_config["RATE_LIMIT_TRUST_PROXY"],
    allow_paths={},
    allow_prefixes={},
)

# 鉴权与头清理（仅跳过鉴权，仍做头净化）
app.add_middleware(
    RequestPrepMiddleware,
    auth_skip_paths=PUBLIC_EXACT,
    auth_skip_prefixes=PUBLIC_PREFIX,
)


def _strip_hop_headers(h: dict) -> dict:
    return {k: v for k, v in h.items() if k.lower() not in HOP_HEADERS}


@app.get("/")
async def root():
    return {
        "name": "CIL Router",
        "version": "1.1.0",
        "providers": len(config.get_all_providers_info()),
        "current_provider": config.CURRENT_PROVIDER_INDEX,
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse({"detail": "未设置"},status_code=204)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
async def forward(path: str, request: Request):
    method = request.method.upper()

    try:
        # 获得请求端点
        ep = config.get_current_provider_endpoint()
        base_url = ep["base_url"].rstrip("/")
        url = f"{base_url}/{path.lstrip('/')}"
        if request.url.query:
            url = f"{url}?{request.url.query}"

        # 透传请求体（流式）
        async def body_iter() -> AsyncIterator[bytes]:
            async for chunk in request.stream():
                if chunk:
                    yield chunk

        client = await get_client_for(base_url)
        cm = client.stream(method, url, headers=request.state.headers, content=body_iter())
        resp = await cm.__aenter__()

        async def resp_bytes() -> AsyncIterator[bytes]:
            try:
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass

        # 返回流式响应，移除逐跳头
        return StreamingResponse(
            resp_bytes(),
            status_code=resp.status_code,
            headers=_strip_hop_headers(dict(resp.headers)),
        )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {type(e).__name__}: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部错误: {type(e).__name__}: {e}")


if __name__ == "__main__":
    import uvicorn
    # 禁用访问日志并降低日志级别，避免控制台输出
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_level="critical",
    )
