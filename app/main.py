# -*- coding: utf-8 -*-
"""
CIL Router - 应用入口，只负责装配。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import config
from app.constants import APP_VERSION
from app.http_client.http_pool import close_all_clients, ensure_http2_support
from app.log.logger import get_logger
from app.middleware.rate_limiter import RateLimitMiddleware, RateLimiter, close_rate_limit_middleware
from app.routes import router

logger = get_logger()

rate_limit_config = config.get_rate_limit_config()
RATE_LIMIT_ENABLED = rate_limit_config["RATE_LIMIT_ENABLED"]
rl = RateLimiter(
    rpm=rate_limit_config["RATE_LIMIT_RPM"],
    burst_size=rate_limit_config["RATE_LIMIT_BURST_SIZE"],
) if RATE_LIMIT_ENABLED else None


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        ensure_http2_support()
        if rl:
            await rl.start()
        yield
    finally:
        await close_rate_limit_middleware()
        await close_all_clients()


app = FastAPI(
    title="CILRouter",
    description="Claude Code透明代理",
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    RateLimitMiddleware,
    rate_limiter=rl or RateLimiter(rpm=0, burst_size=0),
    enabled=RATE_LIMIT_ENABLED,
    trust_proxy=rate_limit_config["RATE_LIMIT_TRUST_PROXY"],
)

app.include_router(router)


if __name__ == "__main__":
    import logging
    import uvicorn

    server_config = config.get_server_config()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).disabled = True

    logger.info(
        f"✅ 启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}",
        信息=f"启动 CIL Router 在 {server_config['HOST']}:{server_config['PORT']}",
    )
    logger.info(
        f"✅ 配置了 {len(config.get_all_providers_info())} 个供应商",
        信息=f"配置了 {len(config.get_all_providers_info())} 个供应商",
    )
    logger.info(
        f"✅ 当前使用供应商 {config.get_current_provider_index()}",
        信息=f"当前使用供应商 {config.get_current_provider_index()}",
    )

    uvicorn.run(
        app,
        host=server_config["HOST"],
        port=server_config["PORT"],
        http="h11",
        timeout_keep_alive=120,
        access_log=False,
    )
