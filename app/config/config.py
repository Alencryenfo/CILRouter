# -*- coding: utf-8 -*-
"""
CIL Router 配置模块
从固定路径 config.yaml（项目根目录）加载配置
"""

from pathlib import Path
from threading import RLock
from typing import List, Dict, Any
from urllib.parse import quote

import yaml

# 固定配置文件路径：项目根目录下的 config.yaml
# app/config/config.py → app/config/ → app/ → project_root/
CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def _load_yaml() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_providers(raw: list) -> List[Dict[str, List[str]]]:
    providers = []
    for i, p in enumerate(raw or []):
        endpoints = p.get("endpoints", [])
        if not endpoints:
            raise ValueError(f"providers[{i}] 未配置 endpoints")
        base_urls = []
        api_keys = []
        for j, endpoint in enumerate(endpoints):
            base_url = str(endpoint.get("base_url", "")).strip().rstrip("/")
            api_key = str(endpoint.get("api_key", "")).strip()
            if not base_url:
                raise ValueError(f"providers[{i}].endpoints[{j}] 缺少 base_url")
            if not api_key:
                raise ValueError(f"providers[{i}].endpoints[{j}] 缺少 api_key")
            base_urls.append(base_url)
            api_keys.append(api_key)
        if len(base_urls) != len(api_keys):
            raise ValueError(f"providers[{i}] base_url 与 api_key 数量不一致")
        providers.append({"base_urls": base_urls, "api_keys": api_keys})
    if not providers:
        raise ValueError("未配置任何供应商，请在 config.yaml 中添加 providers")
    return providers


def _str_list(value) -> List[str]:
    """将字符串或列表统一转为字符串列表。"""
    if not value:
        return []
    if isinstance(value, str):
        return [k.strip() for k in value.split(",") if k.strip()]
    return [str(k).strip() for k in value if str(k).strip()]


# ---- 运行时状态 ----
CNT: int = -1
CURRENT_PROVIDER_INDEX: int = 0
PROVIDERS: List[Dict[str, List[str]]] = []
_config_lock = RLock()

# ---- Axiom 直接端点（供 axiom.py 直接访问）----
AXIOM_ENDPOINT: str = ""

# ---- 内部配置快照 ----
_cfg: dict = {}


def _apply(cfg: dict) -> None:
    global CNT, CURRENT_PROVIDER_INDEX, PROVIDERS, AXIOM_ENDPOINT
    CNT = -1
    PROVIDERS = _parse_providers(cfg.get("providers", []))
    CURRENT_PROVIDER_INDEX = int(cfg.get("current_provider", 0))
    if not 0 <= CURRENT_PROVIDER_INDEX < len(PROVIDERS):
        raise ValueError(
            f"current_provider 超出范围: {CURRENT_PROVIDER_INDEX}，"
            f"可用范围: 0-{len(PROVIDERS) - 1}"
        )
    AXIOM_ENDPOINT = str(cfg.get("logging", {}).get("axiom", {}).get("endpoint", "")).strip()


# 启动时加载
_cfg = _load_yaml()
_apply(_cfg)


# ---- 服务器 ----

def get_server_config() -> Dict[str, Any]:
    s = _cfg.get("server", {})
    return {
        "HOST": str(s.get("host", "0.0.0.0")),
        "PORT": int(s.get("port", 8000)),
    }


# ---- 日志 ----

def get_log_level() -> str:
    return str(_cfg.get("logging", {}).get("level", "INFO")).upper()


def is_console_log_enabled() -> bool:
    return bool(_cfg.get("logging", {}).get("console", True))


def is_axiom_enabled() -> bool:
    return bool(_cfg.get("logging", {}).get("axiom", {}).get("enabled", False))


def _normalize_axiom_domain(domain: str) -> str:
    domain = domain.strip().rstrip("/")
    if not domain:
        return ""
    if "://" in domain:
        return domain
    return f"https://{domain}"


def get_axiom_endpoint() -> str:
    ax = _cfg.get("logging", {}).get("axiom", {})
    endpoint = str(ax.get("endpoint", "")).strip()
    if endpoint:
        return endpoint.rstrip("/")
    domain = str(ax.get("domain", "")).strip()
    dataset = str(ax.get("dataset", "")).strip()
    if not domain or not dataset:
        return ""
    return f"{_normalize_axiom_domain(domain)}/v1/ingest/{quote(dataset, safe='')}"


def get_axiom_headers() -> Dict[str, str]:
    ax = _cfg.get("logging", {}).get("axiom", {})
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    token = str(ax.get("api_token", "")).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    labels = str(ax.get("event_labels", "")).strip()
    if labels:
        headers["X-Axiom-Event-Labels"] = labels
    return headers


def get_axiom_query_params() -> Dict[str, str]:
    ax = _cfg.get("logging", {}).get("axiom", {})
    params: Dict[str, str] = {}
    ts_field = str(ax.get("timestamp_field", "")).strip()
    ts_format = str(ax.get("timestamp_format", "")).strip()
    if ts_field:
        params["timestamp-field"] = ts_field
    if ts_format:
        params["timestamp-format"] = ts_format
    return params


def get_axiom_timeout() -> float:
    return float(_cfg.get("logging", {}).get("axiom", {}).get("request_timeout", 2.0))


def get_axiom_retry_config() -> Dict[str, Any]:
    retry = _cfg.get("logging", {}).get("axiom", {}).get("retry", {})
    return {
        "max_attempts": int(retry.get("max_attempts", 5)),
        "base_delay": float(retry.get("base_delay", 1.0)),
        "max_delay": float(retry.get("max_delay", 30.0)),
    }


# ---- 请求 ----

def get_request_config() -> Dict[str, Any]:
    r = _cfg.get("request", {})
    keys = _str_list(_cfg.get("auth", {}).get("keys", []))
    return {
        "AUTH_KEYS": keys,
        "REQUEST_TIMEOUT": float(r.get("timeout", 60)),
        "STREAM_TIMEOUT": float(r.get("stream_timeout", 120)),
    }


# ---- 限流 ----

def get_rate_limit_config() -> Dict[str, Any]:
    rl = _cfg.get("rate_limit", {})
    enabled = bool(rl.get("enabled", False))
    rpm = int(rl.get("rpm", 100))
    burst = int(rl.get("burst", 10))
    if enabled and rpm <= 0:
        raise ValueError("rate_limit.enabled=true 时，rate_limit.rpm 必须大于 0")
    if enabled and burst <= 0:
        raise ValueError("rate_limit.enabled=true 时，rate_limit.burst 必须大于 0")
    return {
        "RATE_LIMIT_ENABLED": enabled,
        "RATE_LIMIT_RPM": rpm,
        "RATE_LIMIT_BURST_SIZE": burst,
        "RATE_LIMIT_TRUST_PROXY": bool(rl.get("trust_proxy", True)),
    }


# ---- 供应商 ----

def get_provider_info(index: int) -> Dict[str, Any]:
    with _config_lock:
        if not 0 <= index < len(PROVIDERS):
            raise IndexError(f"供应商索引超出范围: {index}")
        provider = PROVIDERS[index]
        return {
            "供应商索引": index,
            "供应商端点数目": len(provider["api_keys"]),
            "供应商端点": list(provider["base_urls"]),
        }


def get_all_providers_info() -> List[Dict[str, Any]]:
    with _config_lock:
        return [
            {
                "供应商索引": index,
                "供应商端点数目": len(provider["api_keys"]),
                "供应商端点": list(provider["base_urls"]),
            }
            for index, provider in enumerate(PROVIDERS)
        ]


def get_current_provider_index() -> int:
    with _config_lock:
        return CURRENT_PROVIDER_INDEX


def get_current_provider_endpoint() -> Dict[str, str]:
    with _config_lock:
        if not PROVIDERS:
            raise RuntimeError("未配置任何供应商")
        if not 0 <= CURRENT_PROVIDER_INDEX < len(PROVIDERS):
            raise RuntimeError(
                f"CURRENT_PROVIDER_INDEX 超出范围: {CURRENT_PROVIDER_INDEX}，"
                f"可用范围: 0-{len(PROVIDERS) - 1}"
            )
        provider = PROVIDERS[CURRENT_PROVIDER_INDEX]
        base_urls = provider["base_urls"]
        api_keys = provider["api_keys"]
        global CNT
        CNT = (CNT + 1) % len(base_urls)
        return {"base_url": base_urls[CNT], "api_key": api_keys[CNT]}


def set_provider_index(index: int) -> bool:
    global CURRENT_PROVIDER_INDEX, CNT
    with _config_lock:
        if 0 <= index < len(PROVIDERS):
            _cfg["current_provider"] = index
            CURRENT_PROVIDER_INDEX = index
            CNT = -1
            return True
        return False


def reload_config() -> None:
    """重新从 config.yaml 加载配置。"""
    global _cfg
    with _config_lock:
        _cfg = _load_yaml()
        _apply(_cfg)
