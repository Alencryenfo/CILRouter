# -*- coding: utf-8 -*-
"""
支持环境变量的配置模块
只支持 PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式
"""

import os
from typing import List, Dict, Any
from urllib.parse import quote

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 兼容未安装开发依赖的场景
    def load_dotenv(*args, **kwargs):
        return False


load_dotenv()


def _parse_csv_env(value: str) -> List[str]:
    """将逗号分隔的环境变量解析为去空白后的列表。"""
    return [item.strip() for item in value.split(',') if item.strip()]


def load_providers_from_env() -> List[Dict[str, List[str]]]:
    """
    从环境变量加载供应商配置
    格式：PROVIDER_N_BASE_URL 和 PROVIDER_N_API_KEY (支持逗号分隔的列表)
    例如：PROVIDER_0_BASE_URL=https://api1.com,https://api2.com
         PROVIDER_0_API_KEY=key1,key2
    """
    providers = []
    index = 0
    while True:
        base_urls_str = os.getenv(f'PROVIDER_{index}_BASE_URL')
        api_keys_str = os.getenv(f'PROVIDER_{index}_API_KEY')
        if base_urls_str is None and api_keys_str is None:
            break
        if not base_urls_str or not api_keys_str:
            raise ValueError(
                f"PROVIDER_{index}_BASE_URL 和 PROVIDER_{index}_API_KEY 必须同时配置，"
                f"当前 BASE_URL={'已设置' if base_urls_str else '未设置'}，"
                f"API_KEY={'已设置' if api_keys_str else '未设置'}"
            )
        if base_urls_str and api_keys_str:
            base_urls = _parse_csv_env(base_urls_str)
            api_keys = _parse_csv_env(api_keys_str)
            if len(base_urls) != len(api_keys):
                raise ValueError(
                    f"PROVIDER_{index}_BASE_URL 和 PROVIDER_{index}_API_KEY 数量不一致: "
                    f"{len(base_urls)} != {len(api_keys)}"
                )
            if not base_urls:
                raise ValueError(f"PROVIDER_{index} 没有可用端点配置")
            providers.append({
                "base_urls": base_urls,
                "api_keys": api_keys
            })
            index += 1
    return providers


def _load_provider_index() -> int:
    raw_index = os.getenv('CURRENT_PROVIDER_INDEX', '0').strip()
    try:
        return int(raw_index)
    except ValueError as exc:
        raise ValueError(f"CURRENT_PROVIDER_INDEX 必须是整数，当前值: {raw_index}") from exc


CNT = -1

# 服务器配置
HOST: str = os.getenv('HOST', '0.0.0.0')
PORT: int = int(os.getenv('PORT', '8000'))

# 日志级别
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
CONSOLE_LOG_ENABLED: bool = os.getenv('CONSOLE_LOG_ENABLED', 'true').lower() == 'true'
AXIOM_ENABLED: bool = os.getenv('AXIOM_ENABLED', 'false').lower() == 'true'
AXIOM_ENDPOINT: str = os.getenv('AXIOM_ENDPOINT', '').strip()
AXIOM_DOMAIN: str = os.getenv('AXIOM_DOMAIN', '').strip()
AXIOM_DATASET: str = os.getenv('AXIOM_DATASET', '').strip()
AXIOM_API_TOKEN: str = os.getenv('AXIOM_API_TOKEN', '').strip()
AXIOM_EVENT_LABELS: str = os.getenv('AXIOM_EVENT_LABELS', '').strip()
AXIOM_TIMESTAMP_FIELD: str = os.getenv('AXIOM_TIMESTAMP_FIELD', '').strip()
AXIOM_TIMESTAMP_FORMAT: str = os.getenv('AXIOM_TIMESTAMP_FORMAT', '').strip()
AXIOM_REQUEST_TIMEOUT: float = float(os.getenv('AXIOM_REQUEST_TIMEOUT', '2'))
AXIOM_RETRY_MAX_ATTEMPTS: int = int(os.getenv('AXIOM_RETRY_MAX_ATTEMPTS', '5'))
AXIOM_RETRY_BASE_DELAY: float = float(os.getenv('AXIOM_RETRY_BASE_DELAY', '1'))
AXIOM_RETRY_MAX_DELAY: float = float(os.getenv('AXIOM_RETRY_MAX_DELAY', '30'))

# 供应商配置
PROVIDERS: List[Dict[str, List[str]]] = load_providers_from_env()
CURRENT_PROVIDER_INDEX: int = _load_provider_index()

# 请求配置
AUTH_KEY: str = os.getenv('AUTH_KEY', '').strip()
AUTH_KEYS: List[str] = _parse_csv_env(AUTH_KEY)
REQUEST_TIMEOUT: float = float(os.getenv('REQUEST_TIMEOUT', '60'))
STREAM_TIMEOUT: float = float(os.getenv('STREAM_TIMEOUT', '120'))

# 限流配置
RATE_LIMIT_ENABLED: bool = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
RATE_LIMIT_RPM: int = int(os.getenv('RATE_LIMIT_RPM', '100'))
RATE_LIMIT_BURST_SIZE: int = int(os.getenv('RATE_LIMIT_BURST', '10'))
RATE_LIMIT_TRUST_PROXY: bool = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'


def get_server_config() -> Dict[str, Any]:
    """获取服务器配置"""
    return {
        "HOST": HOST,
        "PORT": PORT
    }

def get_log_level() -> str:
    """获取日志级别"""
    return LOG_LEVEL

def is_console_log_enabled() -> bool:
    return CONSOLE_LOG_ENABLED == True

def is_axiom_enabled() -> bool:
    return AXIOM_ENABLED == True

def _normalize_axiom_domain(domain: str) -> str:
    domain = domain.strip().rstrip('/')
    if not domain:
        return ''
    if '://' in domain:
        return domain
    return f'https://{domain}'

def get_axiom_endpoint() -> str:
    """获取 Axiom ingest 端点。"""
    if AXIOM_ENDPOINT:
        return AXIOM_ENDPOINT.rstrip('/')
    if not AXIOM_DOMAIN or not AXIOM_DATASET:
        return ''
    return f"{_normalize_axiom_domain(AXIOM_DOMAIN)}/v1/ingest/{quote(AXIOM_DATASET, safe='')}"

def get_axiom_headers() -> Dict[str, str]:
    """获取 Axiom ingest 请求头。"""
    headers = {
        'Content-Type': 'application/json',
    }
    if AXIOM_API_TOKEN:
        headers['Authorization'] = f'Bearer {AXIOM_API_TOKEN}'
    if AXIOM_EVENT_LABELS:
        headers['X-Axiom-Event-Labels'] = AXIOM_EVENT_LABELS
    return headers

def get_axiom_query_params() -> Dict[str, str]:
    """获取 Axiom ingest 查询参数。"""
    params = {}
    if AXIOM_TIMESTAMP_FIELD:
        params['timestamp-field'] = AXIOM_TIMESTAMP_FIELD
    if AXIOM_TIMESTAMP_FORMAT:
        params['timestamp-format'] = AXIOM_TIMESTAMP_FORMAT
    return params

def get_axiom_timeout() -> float:
    """获取 Axiom ingest 请求超时。"""
    return AXIOM_REQUEST_TIMEOUT

def get_axiom_retry_config() -> Dict[str, Any]:
    """获取 Axiom 重试配置。"""
    return {
        "max_attempts": AXIOM_RETRY_MAX_ATTEMPTS,
        "base_delay": AXIOM_RETRY_BASE_DELAY,
        "max_delay": AXIOM_RETRY_MAX_DELAY,
    }

def get_provider_info(index: int) -> Dict[str, Any]:
    """获取指定供应商的详细信息"""
    provider = PROVIDERS[index]
    return {
        "供应商索引": index,
        "供应商端点数目": len(provider["api_keys"]),
        "供应商端点": provider["base_urls"],
    }


def get_all_providers_info() -> List[Dict[str, Any]]:
    """获取所有供应商的详细信息"""
    return [get_provider_info(i) for i in range(len(PROVIDERS))]


def get_current_provider_endpoint() -> Dict[str, str]:
    """
    获取当前供应商的一个端点
    返回单个 base_url 和 api_key 的组合
    """
    if not PROVIDERS:
        raise RuntimeError("未配置任何供应商，请先设置 PROVIDER_N_BASE_URL 和 PROVIDER_N_API_KEY")
    if not 0 <= CURRENT_PROVIDER_INDEX < len(PROVIDERS):
        raise RuntimeError(
            f"CURRENT_PROVIDER_INDEX 超出范围: {CURRENT_PROVIDER_INDEX}，可用范围: 0-{len(PROVIDERS) - 1}"
        )

    provider = PROVIDERS[CURRENT_PROVIDER_INDEX]
    base_urls = provider["base_urls"]
    api_keys = provider["api_keys"]
    global CNT
    CNT = (CNT + 1) % len(base_urls)
    return {
        "base_url": base_urls[CNT],
        "api_key": api_keys[CNT]
    }


def get_request_config() -> Dict[str, Any]:
    """获取请求配置"""
    return {
        "AUTH_KEY": AUTH_KEY,
        "AUTH_KEYS": AUTH_KEYS,
        "REQUEST_TIMEOUT": REQUEST_TIMEOUT,
        "STREAM_TIMEOUT": STREAM_TIMEOUT
    }


def get_rate_limit_config() -> Dict[str, Any]:
    """获取限流配置"""
    return {
        "RATE_LIMIT_ENABLED": RATE_LIMIT_ENABLED,
        "RATE_LIMIT_RPM": RATE_LIMIT_RPM,
        "RATE_LIMIT_BURST_SIZE": RATE_LIMIT_BURST_SIZE,
        "RATE_LIMIT_TRUST_PROXY": RATE_LIMIT_TRUST_PROXY
    }


def reload_config():
    """重新加载配置（主要用于运行时更新环境变量）"""
    global CNT,PROVIDERS, CURRENT_PROVIDER_INDEX, REQUEST_TIMEOUT, STREAM_TIMEOUT, HOST, PORT, AUTH_KEY, AUTH_KEYS, RATE_LIMIT_ENABLED, \
        RATE_LIMIT_RPM, RATE_LIMIT_BURST_SIZE, RATE_LIMIT_TRUST_PROXY,LOG_LEVEL, CONSOLE_LOG_ENABLED, AXIOM_ENABLED, AXIOM_ENDPOINT, \
        AXIOM_DOMAIN, AXIOM_DATASET, AXIOM_API_TOKEN, AXIOM_EVENT_LABELS, AXIOM_TIMESTAMP_FIELD, AXIOM_TIMESTAMP_FORMAT, \
        AXIOM_REQUEST_TIMEOUT, AXIOM_RETRY_MAX_ATTEMPTS, AXIOM_RETRY_BASE_DELAY, AXIOM_RETRY_MAX_DELAY

    CNT = -1

    # 服务器配置
    HOST= os.getenv('HOST', '0.0.0.0')
    PORT= int(os.getenv('PORT', '8000'))

    # 日志级别
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    CONSOLE_LOG_ENABLED = os.getenv('CONSOLE_LOG_ENABLED', 'true').lower() == 'true'
    AXIOM_ENABLED = os.getenv('AXIOM_ENABLED', 'false').lower() == 'true'
    AXIOM_ENDPOINT = os.getenv('AXIOM_ENDPOINT', '').strip()
    AXIOM_DOMAIN = os.getenv('AXIOM_DOMAIN', '').strip()
    AXIOM_DATASET = os.getenv('AXIOM_DATASET', '').strip()
    AXIOM_API_TOKEN = os.getenv('AXIOM_API_TOKEN', '').strip()
    AXIOM_EVENT_LABELS = os.getenv('AXIOM_EVENT_LABELS', '').strip()
    AXIOM_TIMESTAMP_FIELD = os.getenv('AXIOM_TIMESTAMP_FIELD', '').strip()
    AXIOM_TIMESTAMP_FORMAT = os.getenv('AXIOM_TIMESTAMP_FORMAT', '').strip()
    AXIOM_REQUEST_TIMEOUT = float(os.getenv('AXIOM_REQUEST_TIMEOUT', '2'))
    AXIOM_RETRY_MAX_ATTEMPTS = int(os.getenv('AXIOM_RETRY_MAX_ATTEMPTS', '5'))
    AXIOM_RETRY_BASE_DELAY = float(os.getenv('AXIOM_RETRY_BASE_DELAY', '1'))
    AXIOM_RETRY_MAX_DELAY = float(os.getenv('AXIOM_RETRY_MAX_DELAY', '30'))

    # 供应商配置
    PROVIDERS = load_providers_from_env()
    CURRENT_PROVIDER_INDEX = _load_provider_index()

    # 请求配置
    AUTH_KEY = os.getenv('AUTH_KEY', '').strip()
    AUTH_KEYS = _parse_csv_env(AUTH_KEY)
    REQUEST_TIMEOUT= float(os.getenv('REQUEST_TIMEOUT', '60'))
    STREAM_TIMEOUT = float(os.getenv('STREAM_TIMEOUT', '120'))

    # 限流配置
    RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
    RATE_LIMIT_RPM = int(os.getenv('RATE_LIMIT_RPM', '100'))
    RATE_LIMIT_BURST_SIZE= int(os.getenv('RATE_LIMIT_BURST', '10'))
    RATE_LIMIT_TRUST_PROXY = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'


def set_provider_index(index: int) -> bool:
    """设置当前供应商索引"""
    global CURRENT_PROVIDER_INDEX, CNT
    if 0 <= index < len(PROVIDERS):
        CURRENT_PROVIDER_INDEX = index
        CNT = -1
        os.environ['CURRENT_PROVIDER_INDEX'] = str(index)
        return True
    return False


# # 启动时打印配置信息
# if __name__ == "__main__":
#     print("CIL Router 配置信息:")
#     print(f"服务器: {HOST}:{PORT}")
#     print(f"供应商数量: {len(PROVIDERS)}")
#     print(f"当前供应商索引: {CURRENT_PROVIDER_INDEX}")
#     print(f"请求超时: {REQUEST_TIMEOUT}s")
#     print(f"流式超时: {STREAM_TIMEOUT}s")
#     print(f"限流状态: {'启用' if RATE_LIMIT_ENABLED else '禁用'}")
#     if RATE_LIMIT_ENABLED:
#         print(f"限流配置: {RATE_LIMIT_RPM}次/分钟, 突发容量: {RATE_LIMIT_BURST_SIZE}")
#
#     for i, provider in enumerate(PROVIDERS):
#         base_urls = provider['base_urls']
#         api_keys = provider['api_keys']
#         print(f"供应商 {i}: {len(base_urls)} 个端点")
#         for j, (url, key) in enumerate(zip(base_urls, api_keys)):
#             masked_key = key[:8] + "..." if len(key) > 8 else "***"
#             print(f"  端点 {j}: {url} (key: {masked_key})")
