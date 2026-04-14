# -*- coding: utf-8 -*-
"""
共享常量：应用元数据、禁止透传的请求头、逐跳头、可重试的上游异常类型
"""

import httpx

APP_NAME = "CIL Router"
APP_VERSION = "2.0.0"

PROHIBIT_HEADERS = frozenset({
    # 逐跳 / 连接管理
    "authorization",
    "host",
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",

    # 长度 / 期望（交给 httpx 自己计算）
    "content-length",
    "expect",

    # CDN / 代理痕迹
    "cdn-loop",
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-forwarded-server",
    "x-forwarded-port",
    "x-real-ip",
    "true-client-ip",
    "via",
    "forwarded",

    # x-api-key（交给 httpx 自己处理）
    "x-api-key",
})

HOP_HEADERS = frozenset((
    "transfer-encoding", "connection", "keep-alive",
    "proxy-connection", "upgrade", "te", "trailer", "content-encoding",
))

TRANSIENT_EXC = (
    httpx.ConnectError, httpx.ConnectTimeout,
    httpx.ReadTimeout, httpx.ReadError,
    httpx.RemoteProtocolError, httpx.PoolTimeout,
)
