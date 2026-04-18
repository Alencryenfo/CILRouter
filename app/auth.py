# -*- coding: utf-8 -*-
"""
鉴权模块：判断来访令牌是否合法，以及是否向上游注入鉴权头。
"""

from typing import Literal

from fastapi import HTTPException
from app.log.logger import get_logger

logger = get_logger()
AuthHeaderName = Literal["authorization", "x-api-key"]
AUTHORIZATION_HEADER: AuthHeaderName = "authorization"
X_API_KEY_HEADER: AuthHeaderName = "x-api-key"


def is_passthrough_models_request(path: str) -> bool:
    """识别允许免鉴权访问的 /v1/models 请求。"""
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


def format_auth_header_name(header_name: AuthHeaderName) -> str:
    if header_name == X_API_KEY_HEADER:
        return "X-API-Key"
    return "Authorization"


def _validate_authorization(
    path: str,
    incoming_authorization: str,
    auth_keys: list[str],
    IP: str,
    trace_id: str,
) -> None:
    if not incoming_authorization.lower().startswith("bearer "):
        _reject(path, IP, trace_id, "Bearer格式错误", "鉴权格式错误，应为 Bearer <token>")

    if incoming_authorization[7:].strip() not in auth_keys:
        _reject(path, IP, trace_id, "令牌无效", "令牌无效")


def _validate_x_api_key(
    path: str,
    incoming_x_api_key: str,
    auth_keys: list[str],
    IP: str,
    trace_id: str,
) -> None:
    if incoming_x_api_key not in auth_keys:
        _reject(path, IP, trace_id, "X-API-Key无效", "X-API-Key无效")


def resolve_upstream_auth_header(
    path: str,
    incoming_authorization: str,
    incoming_x_api_key: str,
    auth_keys: list[str],
    IP: str,
    trace_id: str,
) -> AuthHeaderName:
    """
    决定使用哪种上游鉴权头，并在需要时校验来访请求。

    规则：
    - Authorization 与 X-API-Key 同时存在时，优先使用 Authorization。
    - /v1/models：客户端无需携带令牌；若来访请求携带鉴权头，则沿用该头类型请求上游。
    - 其他接口且无 auth_keys 配置：不校验；若来访请求携带鉴权头，则沿用该头类型请求上游。
    - 其他接口：必须携带合法 Authorization 或 X-API-Key，通过后只注入对应类型的上游鉴权头。
    """
    if incoming_authorization:
        chosen_header = AUTHORIZATION_HEADER
    elif incoming_x_api_key:
        chosen_header = X_API_KEY_HEADER
    else:
        chosen_header = AUTHORIZATION_HEADER

    if is_passthrough_models_request(path):
        return chosen_header

    if not auth_keys:
        return chosen_header

    if incoming_authorization:
        _validate_authorization(path, incoming_authorization, auth_keys, IP, trace_id)
        return AUTHORIZATION_HEADER

    if incoming_x_api_key:
        _validate_x_api_key(path, incoming_x_api_key, auth_keys, IP, trace_id)
        return X_API_KEY_HEADER

    _reject(
        path,
        IP,
        trace_id,
        "缺少鉴权令牌",
        "缺少鉴权令牌，应提供 Authorization 或 X-API-Key",
    )
    return AUTHORIZATION_HEADER
