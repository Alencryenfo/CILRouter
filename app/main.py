# -*- coding: utf-8 -*-
"""
CIL Router - 极简版 Claude API 转发器
支持所有HTTP方法，完全透明转发，智能处理API Key和流式请求
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import sys
import os
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import config
from app.middleware.rate_limiter import RateLimiter, RateLimitMiddleware
from app.log import setup_logger
import anyio
import asyncio

logger = setup_logger(
    log_level="INFO",
)

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
               "proxy-connection","upgrade","te","trailer", "content-encoding")
TRANSIENT_EXC = (
    httpx.ConnectError, httpx.ConnectTimeout,
    httpx.ReadTimeout, httpx.ReadError,
    httpx.RemoteProtocolError, httpx.PoolTimeout,
)
rate_limit_config = config.get_rate_limit_config()
RATE_LIMIT_ENABLED = rate_limit_config["RATE_LIMIT_ENABLED"]
rl = RateLimiter(
    rpm=rate_limit_config["RATE_LIMIT_RPM"],
    burst_size=rate_limit_config["RATE_LIMIT_BURST_SIZE"]
) if RATE_LIMIT_ENABLED else None

@asynccontextmanager
async def lifespan(_: FastAPI):
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

def get_request_ip(request: Request) -> str:
    """获取客户端IP地址，复用中间件逻辑"""
    trust_proxy = rate_limit_config["RATE_LIMIT_TRUST_PROXY"]
    # 如果不信任代理，直接使用连接IP
    if not trust_proxy:
        if request.client and hasattr(request.client, 'host') and request.client.host:
            return request.client.host
        return "unknown-client"
    # 信任代理的情况下，按优先级获取真实IP
    # 1. CF-Connecting-IP: Cloudflare 提供的原始客户端IP（最可靠）
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    # 2. CF-IPCountry 存在时，说明经过了 Cloudflare，但没有 CF-Connecting-IP
    if request.headers.get("CF-IPCountry"):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            return first_ip
    # 3. X-Real-IP: nginx 等反向代理设置的真实IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    # 4. X-Forwarded-For: 标准代理头部（取第一个IP）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        return first_ip
    # 5. 最后使用连接IP
    if request.client and hasattr(request.client, 'host') and request.client.host:
        return request.client.host
    logger.warning("无法获取客户端IP，需要检查可能的攻击")
    return "unknown-client"

@app.get("/")
async def root(request: Request):
    """根路径，返回当前状态"""
    logger.info(f"IP:{get_request_ip(request)}访问端点 /")
    return {
        "应用名称": "CIL Router",
        "当前版本": "1.0.2",
        "当前供应商": config.CURRENT_PROVIDER_INDEX,
        "全部供应商信息": config.get_all_providers_info(),
    }


@app.post("/select")
async def select_provider(request: Request):
    """
    选择供应商接口
    POST 一个数字表示要使用的供应商索引
    """
    IP = get_request_ip(request)
    try:
        logger.info(f"IP:{IP}访问端点 /select")
        body = await request.body()
        index = int(body.decode().strip())
        if config.set_provider_index(index):
            logger.info(f"IP:{IP}访问端点 /select➡️成功，切换到供应商 {index}")
            return {
                "success": True,
                "message": f"已切换到供应商 {index}",
                "供应商信息": config.get_provider_info(index)
            }
        else:
            logger.warning(f"IP:{IP}访问端点 /select➡️失败，索引 {index} 无效")
            raise HTTPException(
                status_code=400,
                detail=f"无效的供应商索引 {index}"
            )
    except ValueError:
        logger.error(f"IP:{IP}访问端点 /select➡️发生错误: 请求体不是一个数字")
        raise HTTPException(status_code=400, detail="请求体不是一个数字")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IP:{IP}访问端点 /select➡️发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
async def forward_request(path: str, request: Request):
    """
    通用转发接口
    支持所有HTTP方法，完全透明转发
    智能处理API Key：如果请求中有Authorization头部则替换，没有则添加
    支持流式响应
    """
    IP = get_request_ip(request)
    logger.info(f"IP:{IP}访问端点 /{path}")
    try:
        # 鉴权检查
        auth_key = (config.get_request_config()["AUTH_KEY"]).strip()
        if auth_key:
            auth_header = (request.headers.get('authorization', '')).strip()
            if not auth_header.lower().startswith('bearer '):
                logger.warning(f"IP:{IP}访问端点 /{path}➡️鉴权失败: 缺少Bearer令牌")
                raise HTTPException(status_code=401, detail="缺少鉴权令牌")
            if auth_header[7:] != auth_key:
                logger.warning(f"IP:{IP}访问端点 /{path}➡️鉴权失败: 令牌无效")
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

        logger.info(
            f"IP:{IP}访问端点 /{path}➡️转发请求➡️"
            f"方法: {method}"
            f"{('，参数: ' + str(query_params)) if query_params else ''}➡️"
            f"请求头: {headers}➡️"
            f"请求体: {(body[:100] if body else '')}... (总长度: {len(body) if body else 0} bytes)"
        )

        return await _proxy_request(method, path, query_params, headers, body,IP)

    except httpx.HTTPError as e:
        logger.error(f"IP:{IP}访问端点 /{path}➡️转发请求失败: {str(e)}")
        raise HTTPException(status_code=502, detail=f"转发请求失败: {str(e)}")

    except Exception as e:
        logger.error(f"IP:{IP}访问端点 /{path}➡️转发请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部错误: {str(e)}")

def _strip_hop_headers(h: dict) -> dict:
    return {k: v for k, v in h.items() if k.lower() not in HOP_HEADERS}

async def _proxy_request(method: str, path: str, query_params: str, headers: dict, body: bytes,IP:str):
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
        up_headers["accept-encoding"] = "identity"

        timeout   = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        limits    = httpx.Limits(max_keepalive_connections=100, max_connections=100, keepalive_expiry=30.0)
        transport = httpx.AsyncHTTPTransport(http2=False, retries=0)
        client    = httpx.AsyncClient(timeout=timeout, limits=limits, transport=transport)

        handed_off = False  # 关键：标记是否已把关闭责任交给生成器
        try:
            resp_cm = client.stream(method, url, headers=up_headers, content=body)
            resp = await resp_cm.__aenter__()

            async def byte_iter():
                try:
                    firstres = b''
                    lstres = b''
                    async for chunk in resp.aiter_bytes():
                        firstres += chunk
                        if len(firstres)>200:
                            firstres = firstres[:200]
                        lstres += chunk
                        if len(lstres) > 200:
                            lstres = lstres[-200:]
                        yield chunk
                    if firstres or lstres:
                        logger.info(
                            f"IP:{IP}访问端点 /{path}➡️转发请求响应体: "
                            f"➡️{firstres.decode('utf-8', errors='replace')}......"
                            f"{lstres.decode('utf-8', errors='replace')}⬅️"
                        )
                    else:
                        logger.warning(f"IP:{IP}访问端点 /{path}➡️转发请求响应体为空")

                except (httpx.StreamClosed, httpx.ReadError,
                        httpx.RemoteProtocolError, anyio.EndOfStream,
                        anyio.ClosedResourceError, asyncio.CancelledError):
                    logger.warning(f"IP:{IP}访问端点 /{path}➡️转发请求响应流异常，可能是连接中断或超时")
                    return
                finally:
                    try:
                        await resp_cm.__aexit__(None, None, None)
                    finally:
                        await client.aclose()

            handed_off = True  # 已把关闭责任交给生成器
            logger.info(f"IP:{IP}访问端点 /{path}➡️转发请求响应头: {dict(resp.headers)}➡️响应状态: {resp.status_code}")
            return StreamingResponse(
                byte_iter(),
                status_code=resp.status_code,
                headers=_strip_hop_headers(resp.headers),
            )

        except TRANSIENT_EXC as e:
            logger.warning(f"IP:{IP}访问端点 /{path}➡️转发请求失败: {str(e)}")
            last_exc = e
        except Exception as e:
            logger.warning(f"IP:{IP}访问端点 /{path}➡️转发请求失败: {str(e)}")
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
    logger.error(f"IP:{IP}访问端点 /{path}➡️转发请求失败: {str(last_exc)}")
    raise HTTPException(status_code=502, detail=f"上游连接失败：{last_exc}")

if __name__ == "__main__":
    import uvicorn
    server_config = config.get_server_config()
    import logging
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).disabled = True
    # 启动前日志
    logger.info(f"🚀 启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}")
    logger.info(f"📡 配置了 {len(config.get_all_providers_info())} 个供应商")
    logger.info(f"🎯 当前使用供应商 {config.CURRENT_PROVIDER_INDEX}")
    
    uvicorn.run(app, host=server_config['HOST'], port=server_config['PORT'],http="h11", timeout_keep_alive=120,access_log=False)
