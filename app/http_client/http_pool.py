# -*- coding: utf-8 -*-
# app/http_pool.py
import httpx
from typing import Dict
from asyncio import Lock

from app.log import setup_logger
from app.config import config
# 说明：
# - 为每个 base_url 复用一个 AsyncClient，避免高并发下频繁建连/握手。
# - 提供 get_client_for() 获取（或懒创建）客户端。
# - 提供 close_all_clients() 在应用关闭时统一释放资源。

_client_pool: Dict[str, httpx.AsyncClient] = {}
_client_lock = Lock()

logger = setup_logger(
    log_level=config.get_log_level(),
)

async def get_client_for(base_url: str) -> httpx.AsyncClient:
    """
    按 base_url 获取一个可复用的 AsyncClient。
    不存在则懒创建并放入池中；存在则直接返回。
    """
    async with _client_lock:
        cli = _client_pool.get(base_url)
        if cli is not None:
            return cli

        # —— 最简但稳妥的默认参数（可按需微调）——
        timeout = httpx.Timeout(
            connect=5.0,   # 连接超时：短一些便于快速失败+重试
            read=None,     # 读取超时：适配大多数流式/长响应
            write=20.0,     # 写入超时
            pool=5.0,      # 连接池获取超时：避免无限等待
        )
        limits = httpx.Limits(
            max_connections=60,          # 池内最大并发连接数（所有host总和）
            max_keepalive_connections=60,# 可复用的长连数量
            keepalive_expiry=30.0,        # 空闲长连保活时长
        )
        transport = httpx.AsyncHTTPTransport(
            http2=True,   # 若上游支持，开启HTTP/2可显著提升并发复用
            retries=0     # 重试由上层业务控制（更可控）
        )

        cli = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            transport=transport
            # 注：不在这里传 base_url，避免路径拼接出错；上层拼URL更直观
        )
        _client_pool[base_url] = cli
        return cli

async def close_all_clients() -> None:
    """
    在应用关闭时调用，确保所有 AsyncClient 被正确关闭，释放连接与句柄。
    """
    logger.info("✅ ♻️ 正在关闭所有 HTTP 客户端连接池")
    async with _client_lock:
        for cli in _client_pool.values():
            await cli.aclose()
        _client_pool.clear()
