# -*- coding: utf-8 -*-
"""
CIL Router - 应用入口，只负责装配。
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import config
from app.constants import APP_VERSION
from app.http_client.http_pool import close_all_clients, ensure_http2_support
from app.log.logger import get_logger
from app.middleware.rate_limiter import RateLimitMiddleware, RateLimiter
from app.routes import router

logger = get_logger()
CONFIG_RELOAD_INTERVAL_SECONDS = 1.0

rate_limit_config = config.get_rate_limit_config()
RATE_LIMIT_ENABLED = rate_limit_config["RATE_LIMIT_ENABLED"]
rl = RateLimiter(
    rpm=rate_limit_config["RATE_LIMIT_RPM"],
    burst_size=rate_limit_config["RATE_LIMIT_BURST_SIZE"],
) if RATE_LIMIT_ENABLED else None


async def _config_reload_loop():
    while True:
        await asyncio.sleep(CONFIG_RELOAD_INTERVAL_SECONDS)
        try:
            if config.reload_config_if_changed():
                logger.info("♻️ 检测到 config.yaml 变更，已完成热重载", 信息="config.yaml 已热重载")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"❌ config.yaml 热重载失败: {type(e).__name__}: {e}",
                信息=f"config.yaml 热重载失败: {type(e).__name__}: {e}",
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    config_reload_task = asyncio.create_task(_config_reload_loop())
    try:
        ensure_http2_support()
        if rl:
            await rl.start()
        yield
    finally:
        config_reload_task.cancel()
        try:
            await config_reload_task
        except asyncio.CancelledError:
            pass
        if rl:
            await rl.close()
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
