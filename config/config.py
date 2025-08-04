# -*- coding: utf-8 -*-
"""
支持环境变量的配置模块
只支持 PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式
"""

import os
import random
from typing import List, Dict, Any

# 默认供应商配置（支持多URL负载均衡）
DEFAULT_PROVIDERS = [
    {
        "base_urls": ["https://co.yes.vg"],
        "api_keys": [""]  # 在这里填入你的 API Key
    },
    {
        "base_urls": ["https://api.provider2.com"], 
        "api_keys": [""]  # 第二个供应商的 API Key
    }
]

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
            # 解析逗号分隔的URL和API Key列表
            base_urls = [url.strip() for url in base_urls_str.split(',') if url.strip()]
            api_keys = [key.strip() for key in api_keys_str.split(',') if key.strip()]
            
            # 确保URL和Key数量匹配
            if len(base_urls) != len(api_keys):
                print(f"警告：供应商 {index} 的 URL 和 API Key 数量不匹配，跳过")
                index += 1
                continue
            
            providers.append({
                "base_urls": base_urls,
                "api_keys": api_keys
            })
            index += 1
        else:
            break
    
    # 如果环境变量中有配置，使用环境变量；否则使用默认配置
    return providers if providers else DEFAULT_PROVIDERS

# 加载供应商配置
providers: List[Dict[str, List[str]]] = load_providers_from_env()

# 从环境变量获取当前供应商索引
current_provider_index: int = int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))

# 每个供应商内部的URL索引计数器（用于轮询负载均衡）
_provider_url_counters: Dict[int, int] = {}

# 从环境变量获取超时配置
request_timeout: float = float(os.getenv('REQUEST_TIMEOUT', '60'))
stream_timeout: float = float(os.getenv('STREAM_TIMEOUT', '120'))

# 从环境变量获取服务器配置
host: str = os.getenv('HOST', '0.0.0.0')
port: int = int(os.getenv('PORT', '8000'))

# 从环境变量获取鉴权密钥
auth_key: str = os.getenv('AUTH_KEY', '')

# 从环境变量获取限流配置
rate_limit_enabled: bool = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
rate_limit_requests_per_minute: int = int(os.getenv('RATE_LIMIT_RPM', '100'))
rate_limit_burst_size: int = int(os.getenv('RATE_LIMIT_BURST', '10'))
rate_limit_trust_proxy: bool = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'

def get_current_provider_endpoint() -> Dict[str, str]:
    """
    获取当前供应商的一个端点（使用轮询负载均衡）
    返回单个 base_url 和 api_key 的组合
    """
    if not providers or current_provider_index >= len(providers):
        return {"base_url": "", "api_key": ""}
    
    provider = providers[current_provider_index]
    base_urls = provider["base_urls"]
    api_keys = provider["api_keys"]
    
    if not base_urls or not api_keys:
        return {"base_url": "", "api_key": ""}
    
    # 使用轮询方式选择URL
    if current_provider_index not in _provider_url_counters:
        _provider_url_counters[current_provider_index] = 0
    
    url_index = _provider_url_counters[current_provider_index] % len(base_urls)
    _provider_url_counters[current_provider_index] += 1
    
    return {
        "base_url": base_urls[url_index],
        "api_key": api_keys[url_index]
    }

def get_current_provider_random_endpoint() -> Dict[str, str]:
    """
    获取当前供应商的一个端点（使用随机负载均衡）
    返回单个 base_url 和 api_key 的组合
    """
    if not providers or current_provider_index >= len(providers):
        return {"base_url": "", "api_key": ""}
    
    provider = providers[current_provider_index]
    base_urls = provider["base_urls"]
    api_keys = provider["api_keys"]
    
    if not base_urls or not api_keys:
        return {"base_url": "", "api_key": ""}
    
    # 随机选择URL
    url_index = random.randint(0, len(base_urls) - 1)
    
    return {
        "base_url": base_urls[url_index],
        "api_key": api_keys[url_index]
    }

def get_current_provider() -> Dict[str, str]:
    """获取当前选择的供应商（向后兼容，使用轮询负载均衡）"""
    return get_current_provider_endpoint()

def set_provider_index(index: int) -> bool:
    """设置当前供应商索引"""
    global current_provider_index
    if 0 <= index < len(providers):
        current_provider_index = index
        return True
    return False

def get_provider_count() -> int:
    """获取供应商总数"""
    return len(providers)

def get_provider_info(index: int) -> Dict[str, Any]:
    """获取指定供应商的详细信息"""
    if not providers or index >= len(providers):
        return {}
    
    provider = providers[index]
    return {
        "index": index,
        "base_urls": provider["base_urls"],
        "api_keys_count": len(provider["api_keys"]),
        "endpoints_count": len(provider["base_urls"])
    }

def get_all_providers_info() -> List[Dict[str, Any]]:
    """获取所有供应商的详细信息"""
    return [get_provider_info(i) for i in range(len(providers))]

def get_request_timeout() -> float:
    """获取普通请求超时时间"""
    return request_timeout

def get_stream_timeout() -> float:
    """获取流式请求超时时间"""
    return stream_timeout

def get_server_config() -> Dict[str, Any]:
    """获取服务器配置"""
    return {
        "host": host,
        "port": port
    }

def get_auth_key() -> str:
    """获取鉴权密钥"""
    return auth_key

def is_auth_enabled() -> bool:
    """检查是否启用了鉴权"""
    return bool(auth_key.strip())

def is_rate_limit_enabled() -> bool:
    """检查是否启用了限流"""
    return rate_limit_enabled

def get_rate_limit_config() -> Dict[str, Any]:
    """获取限流配置"""
    return {
        "enabled": rate_limit_enabled,
        "requests_per_minute": rate_limit_requests_per_minute,
        "burst_size": rate_limit_burst_size,
        "trust_proxy": rate_limit_trust_proxy
    }

def reload_config():
    """重新加载配置（主要用于运行时更新环境变量）"""
    global providers, current_provider_index, request_timeout, stream_timeout, host, port, auth_key, _provider_url_counters
    global rate_limit_enabled, rate_limit_requests_per_minute, rate_limit_burst_size, rate_limit_trust_proxy
    
    providers = load_providers_from_env()
    current_provider_index = int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))
    request_timeout = float(os.getenv('REQUEST_TIMEOUT', '60'))
    stream_timeout = float(os.getenv('STREAM_TIMEOUT', '120'))
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8000'))
    auth_key = os.getenv('AUTH_KEY', '')
    
    # 重新加载限流配置
    rate_limit_enabled = os.getenv('RATE_LIMIT_ENABLED', 'false').lower() == 'true'
    rate_limit_requests_per_minute = int(os.getenv('RATE_LIMIT_RPM', '100'))
    rate_limit_burst_size = int(os.getenv('RATE_LIMIT_BURST', '10'))
    rate_limit_trust_proxy = os.getenv('RATE_LIMIT_TRUST_PROXY', 'true').lower() == 'true'
    
    # 重置URL计数器
    _provider_url_counters.clear()

# 启动时打印配置信息
if __name__ == "__main__":
    print("CIL Router 配置信息:")
    print(f"服务器: {host}:{port}")
    print(f"供应商数量: {len(providers)}")
    print(f"当前供应商索引: {current_provider_index}")
    print(f"请求超时: {request_timeout}s")
    print(f"流式超时: {stream_timeout}s")
    print(f"限流状态: {'启用' if rate_limit_enabled else '禁用'}")
    if rate_limit_enabled:
        print(f"限流配置: {rate_limit_requests_per_minute}次/分钟, 突发容量: {rate_limit_burst_size}")
    
    for i, provider in enumerate(providers):
        base_urls = provider['base_urls']
        api_keys = provider['api_keys']
        print(f"供应商 {i}: {len(base_urls)} 个端点")
        for j, (url, key) in enumerate(zip(base_urls, api_keys)):
            masked_key = key[:8] + "..." if len(key) > 8 else "***"
            print(f"  端点 {j}: {url} (key: {masked_key})")