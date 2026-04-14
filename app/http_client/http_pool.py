# -*- coding: utf-8 -*-
# app/http_pool.py
import importlib.util
import httpx
from asyncio import Lock
from typing import Dict

from app.config import config
from app.log import get_logger

_client_pool: Dict[str, httpx.AsyncClient] = {}
_client_lock = Lock()

logger = get_logger()


def ensure_http2_support() -> None:
    """显式校验 h2 依赖，避免服务带着隐性降级启动。"""
    if importlib.util.find_spec("h2") is None:
        raise RuntimeError("缺少 h2 依赖，请重新安装 requirements.txt 或 requirements-prod.txt")

async def get_client_for(base_url: str) -> httpx.AsyncClient:
    async with _client_lock:
        cli = _client_pool.get(base_url)
        if cli is not None:
            return cli
        ensure_http2_support()

        request_config = config.get_request_config()
        timeout = httpx.Timeout(
            connect=5.0,
            read=None,
            write=request_config["REQUEST_TIMEOUT"],
            pool=5.0,
        )
        limits = httpx.Limits(
            max_connections=60,
            max_keepalive_connections=60,
            keepalive_expiry=30.0,
        )
        transport = httpx.AsyncHTTPTransport(
            http2=True,
            retries=0,
        )

        cli = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            transport=transport,
        )
        _client_pool[base_url] = cli
        return cli


async def close_all_clients() -> None:
    logger.info("✅ ♻️ 正在关闭所有 HTTP 客户端连接池")
    async with _client_lock:
        for cli in _client_pool.values():
            await cli.aclose()
        _client_pool.clear()
