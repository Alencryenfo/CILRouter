# -*- coding: utf-8 -*-
"""
支持环境变量的配置模块
只支持 PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式
"""

import os
from typing import List, Dict, Any

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

CNT = 0

# 服务器配置
HOST: str = os.getenv('HOST', '0.0.0.0')
PORT: int = int(os.getenv('PORT', '8000'))

# 日志级别
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')

# 供应商配置
PROVIDERS: List[Dict[str, List[str]]] = load_providers_from_env()
CURRENT_PROVIDER_INDEX: int = 0

# 请求配置
AUTH_KEY: str = os.getenv('AUTH_KEY', '').strip()
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
    global CNT
    CNT += 1
    CNT = CNT % len(base_urls)  # 确保轮询
    return {
        "base_url": base_urls[CNT],
        "api_key": api_keys[CNT]
    }


def get_request_config() -> Dict[str, Any]:
    """获取请求配置"""
    return {
        "AUTH_KEY": AUTH_KEY,
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
    global CNT,PROVIDERS, CURRENT_PROVIDER_INDEX, REQUEST_TIMEOUT, STREAM_TIMEOUT, HOST, PORT, AUTH_KEY, RATE_LIMIT_ENABLED, \
        RATE_LIMIT_RPM, RATE_LIMIT_BURST_SIZE, RATE_LIMIT_TRUST_PROXY,OG_LEVEL

    CNT = 0

    # 服务器配置
    HOST= os.getenv('HOST', '0.0.0.0')
    PORT= int(os.getenv('PORT', '8000'))

    # 日志级别
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # 供应商配置
    PROVIDERS = load_providers_from_env()
    CURRENT_PROVIDER_INDEX= int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))

    # 请求配置
    AUTH_KEY = os.getenv('AUTH_KEY', '').strip()
    REQUEST_TIMEOUT= float(os.getenv('REQUEST_TIMEOUT', '60'))
    STREAM_TIMEOUT = float(os.getenv('STREAM_TIMEOUT', '120'))

    # 限流配置
    RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
    RATE_LIMIT_RPM = int(os.getenv('RATE_LIMIT_RPM', '100'))
    RATE_LIMIT_BURST_SIZE= int(os.getenv('RATE_LIMIT_BURST', '10'))
    RATE_LIMIT_TRUST_PROXY = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'


def set_provider_index(index: int) -> bool:
    """设置当前供应商索引"""
    global CURRENT_PROVIDER_INDEX
    if 0 <= index < len(PROVIDERS):
        CURRENT_PROVIDER_INDEX = index
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
