# -*- coding: utf-8 -*-
"""
鉴权模块：判断来访令牌是否合法，以及是否向上游注入 Authorization。
"""

from fastapi import HTTPException
from app.log.logger import get_logger

logger = get_logger()


def is_passthrough_models_request(path: str) -> bool:
    """识别允许缺失令牌直通的 /v1/models 请求。"""
    return path.strip("/") == "v1/models"


def _reject(path: str, IP: str, trace_id: str, reason: str, detail: str) -> None:
    """记录鉴权失败日志并抛出 401。"""
    logger.warning(
        f"❌IP:{IP}访问端点 /{path}➡️鉴权失败: {reason}",
        IP=IP,
        trace_id=trace_id,
        信息=f"访问端点 /{path} 鉴权失败: {reason}",
    )
    raise HTTPException(status_code=401, detail={"信息": detail, "跟踪ID": trace_id})


def should_use_provider_authorization(
    path: str,
    incoming_authorization: str,
    auth_keys: list[str],
    IP: str,
    trace_id: str,
) -> bool:
    """
    决定是否为上游补充供应商 Authorization。

    规则：
    - 无 auth_keys 配置：不校验，直通（/v1/models 缺 token 时不带上游 Authorization）。
    - 普通接口：必须携带合法 Bearer 令牌，通过后注入上游 Authorization。
    - /v1/models 缺 token：允许直通，但不带上游 Authorization。
    - /v1/models 有 token：仍需通过本地校验，通过后沿用默认上游鉴权。
    """
    passthrough = is_passthrough_models_request(path)

    if not auth_keys:
        return not (passthrough and not incoming_authorization)

    if not incoming_authorization:
        if passthrough:
            return False
        _reject(path, IP, trace_id, "缺少Bearer令牌", "缺少鉴权令牌")

    if not incoming_authorization.lower().startswith("bearer "):
        _reject(path, IP, trace_id, "Bearer格式错误", "鉴权格式错误，应为 Bearer <token>")

    if incoming_authorization[7:].strip() not in auth_keys:
        _reject(path, IP, trace_id, "令牌无效", "令牌无效")

    return True
