# -*- coding: utf-8 -*-
"""
支持环境变量的配置模块
只支持 PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式
"""

import os
from typing import List, Dict, Any

# 默认供应商配置
DEFAULT_PROVIDERS = [
    {
        "base_url": "https://co.yes.vg",
        "api_key": "cr_11ff9f3a5aa317b8bd90d0053e2d0caeec53fc3a05c037ed2b14155e6a8da73d"  # 在这里填入你的 API Key
    },
    {
        "base_url": "https://api.provider2.com", 
        "api_key": ""  # 第二个供应商的 API Key
    }
]

def load_providers_from_env() -> List[Dict[str, str]]:
    """
    从环境变量加载供应商配置
    格式：PROVIDER_N_BASE_URL 和 PROVIDER_N_API_KEY
    """
    providers = []
    index = 0
    
    while True:
        base_url = os.getenv(f'PROVIDER_{index}_BASE_URL')
        api_key = os.getenv(f'PROVIDER_{index}_API_KEY')
        
        if base_url and api_key:
            providers.append({
                "base_url": base_url.strip(),
                "api_key": api_key.strip()
            })
            index += 1
        else:
            break
    
    # 如果环境变量中有配置，使用环境变量；否则使用默认配置
    return providers if providers else DEFAULT_PROVIDERS

# 加载供应商配置
providers: List[Dict[str, str]] = load_providers_from_env()

# 从环境变量获取当前供应商索引
current_provider_index: int = int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))

# 从环境变量获取超时配置
request_timeout: float = float(os.getenv('REQUEST_TIMEOUT', '60'))
stream_timeout: float = float(os.getenv('STREAM_TIMEOUT', '120'))

# 从环境变量获取服务器配置
host: str = os.getenv('HOST', '0.0.0.0')
port: int = int(os.getenv('PORT', '8000'))

# 从环境变量获取鉴权密钥
auth_key: str = os.getenv('AUTH_KEY', '')

def get_current_provider() -> Dict[str, str]:
    """获取当前选择的供应商"""
    if not providers or current_provider_index >= len(providers):
        return {"base_url": "", "api_key": ""}
    return providers[current_provider_index]

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

def reload_config():
    """重新加载配置（主要用于运行时更新环境变量）"""
    global providers, current_provider_index, request_timeout, stream_timeout, host, port, auth_key
    
    providers = load_providers_from_env()
    current_provider_index = int(os.getenv('CURRENT_PROVIDER_INDEX', '0'))
    request_timeout = float(os.getenv('REQUEST_TIMEOUT', '60'))
    stream_timeout = float(os.getenv('STREAM_TIMEOUT', '120'))
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8000'))
    auth_key = os.getenv('AUTH_KEY', '')

# 启动时打印配置信息
if __name__ == "__main__":
    print("CIL Router 配置信息:")
    print(f"服务器: {host}:{port}")
    print(f"供应商数量: {len(providers)}")
    print(f"当前供应商索引: {current_provider_index}")
    print(f"请求超时: {request_timeout}s")
    print(f"流式超时: {stream_timeout}s")
    
    for i, provider in enumerate(providers):
        masked_key = provider['api_key'][:8] + "..." if len(provider['api_key']) > 8 else "***"
        print(f"供应商 {i}: {provider['base_url']} (key: {masked_key})")