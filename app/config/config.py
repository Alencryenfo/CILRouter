# -*- coding: utf-8 -*-
"""
支持环境变量的配置模块
只支持 PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式
"""

import os
from threading import Lock
from typing import List, Dict, Any

CNT = 0
_RR_LOCK = Lock()

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
        if base_urls_str and api_keys_str:
            base_urls = [url.strip() for url in base_urls_str.split(',') if url.strip()]
            api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            providers.append({
                "base_urls": base_urls,
                "api_keys": api_keys
            })
            index += 1
        else:
            break
    return providers

# 日志级别
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()

# 供应商配置
PROVIDERS: List[Dict[str, List[str]]] = load_providers_from_env()
CURRENT_PROVIDER_INDEX: int = 0

# 请求配置
AUTH_KEY: str = os.getenv('AUTH_KEY', '').strip()

# 限流配置
RATE_LIMIT_ENABLED: bool = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
RATE_LIMIT_RPM: int = int(os.getenv('RATE_LIMIT_RPM', '30'))
RATE_LIMIT_BURST: int = int(os.getenv('RATE_LIMIT_BURST', '10'))
RATE_LIMIT_TRUST_PROXY: bool = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'


def get_log_level() -> str:
    """获取日志级别"""
    return LOG_LEVEL

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
    provider = PROVIDERS[CURRENT_PROVIDER_INDEX]
    base_urls = provider["base_urls"]
    api_keys = provider["api_keys"]
    n = min(len(base_urls), len(api_keys))
    if n == 0:
        raise RuntimeError("No provider endpoints configured")
    global CNT
    with _RR_LOCK:
        CNT = (CNT + 1) % n  # 原子更新以避免并发竞争
        idx = CNT
    return {
        "base_url": base_urls[idx],
        "api_key": api_keys[idx]
    }


def get_request_config() -> Dict[str, Any]:
    """获取请求配置"""
    return {
        "AUTH_KEY": AUTH_KEY
    }


def get_rate_limit_config() -> Dict[str, Any]:
    """获取限流配置"""
    return {
        "RATE_LIMIT_ENABLED": RATE_LIMIT_ENABLED,
        "RATE_LIMIT_RPM": RATE_LIMIT_RPM,
        "RATE_LIMIT_BURST": RATE_LIMIT_BURST,
        "RATE_LIMIT_TRUST_PROXY": RATE_LIMIT_TRUST_PROXY
    }

def set_provider_index(index: int) -> bool:
    """设置当前供应商索引"""
    global CURRENT_PROVIDER_INDEX
    if 0 <= index < len(PROVIDERS):
        CURRENT_PROVIDER_INDEX = index
        os.environ['CURRENT_PROVIDER_INDEX'] = str(index)
        return True
    return False
