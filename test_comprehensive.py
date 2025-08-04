# -*- coding: utf-8 -*-
"""
CIL Router 综合功能测试
"""

import asyncio
import sys
import os
sys.path.append('.')

async def test_all_features():
    """全面测试所有功能"""
    print("🚀 开始 CIL Router 综合测试")
    
    # 测试1: 配置模块
    print("\n=== 测试1: 配置模块 ===")
    import config.config as config
    
    print(f"✓ 服务器配置: {config.get_server_config()}")
    print(f"✓ 供应商数量: {config.get_provider_count()}")
    print(f"✓ 当前供应商索引: {config.current_provider_index}")
    print(f"✓ 限流配置: {config.get_rate_limit_config()}")
    
    # 测试供应商切换
    original_index = config.current_provider_index
    if config.set_provider_index(1):
        print("✓ 供应商切换成功")
        config.set_provider_index(original_index)  # 恢复原状态
    else:
        print("❌ 供应商切换失败")
    
    # 测试2: 负载均衡
    print("\n=== 测试2: 负载均衡 ===")
    endpoints = []
    for i in range(5):
        endpoint = config.get_current_provider_endpoint()
        endpoints.append(endpoint["base_url"])
    print(f"✓ 负载均衡测试完成，端点: {set(endpoints)}")
    
    # 测试3: 限流功能
    print("\n=== 测试3: 限流功能 ===")
    from app.middleware.rate_limiter import RateLimiter
    
    limiter = RateLimiter(requests_per_minute=60, burst_size=3)
    
    # 测试突发请求
    allowed_count = 0
    for i in range(5):
        if await limiter.is_allowed("test-ip"):
            allowed_count += 1
    
    print(f"✓ 突发请求测试: 允许 {allowed_count}/5 个请求（期望3个）")
    
    # 测试不同IP
    different_ips = ["192.168.1.1", "192.168.1.2", "10.0.0.1"]
    for ip in different_ips:
        allowed = await limiter.is_allowed(ip)
        print(f"✓ IP {ip}: {'允许' if allowed else '限制'}")
    
    # 测试4: IP地址验证
    print("\n=== 测试4: IP地址验证 ===")
    from app.middleware.rate_limiter import RateLimitMiddleware
    
    middleware = RateLimitMiddleware(None, limiter, True, True)
    
    test_ips = [
        ("192.168.1.1", True),
        ("2001:db8::1", True),
        ("invalid.ip", False),
        ("256.256.256.256", False),
        ("", False)
    ]
    
    for ip, expected in test_ips:
        result = middleware._is_valid_ip(ip)
        status = "✓" if result == expected else "❌"
        print(f"{status} IP验证 '{ip}': {result} (期望: {expected})")
    
    # 测试5: 应用导入和基础功能
    print("\n=== 测试5: 应用基础功能 ===")
    try:
        from app.main import app
        print("✓ 应用导入成功")
        
        # 测试配置模块兼容性
        if hasattr(config, 'get_rate_limit_config'):
            print("✓ 限流配置接口可用")
        
        if hasattr(config, 'get_all_providers_info'):
            print("✓ 供应商信息接口可用")
            
    except Exception as e:
        print(f"❌ 应用导入失败: {e}")
    
    # 测试6: 边界情况
    print("\n=== 测试6: 边界情况 ===")
    
    # 测试无效供应商索引
    invalid_switch = config.set_provider_index(999)
    print(f"✓ 无效供应商索引处理: {not invalid_switch}")
    
    # 测试空配置
    try:
        empty_limiter = RateLimiter(0, 0)
        print("✓ 零配置限流器创建成功")
    except Exception as e:
        print(f"❌ 零配置限流器失败: {e}")
    
    # 测试7: 多端点负载均衡
    print("\n=== 测试7: 多端点负载均衡 ===")
    
    # 临时测试多端点配置
    import os
    old_env = os.environ.copy()
    
    try:
        os.environ['PROVIDER_0_BASE_URL'] = 'https://api1.test,https://api2.test,https://api3.test'
        os.environ['PROVIDER_0_API_KEY'] = 'key1,key2,key3'
        
        # 重新加载配置
        config.reload_config()
        
        # 测试轮询
        endpoints = []
        for i in range(6):
            endpoint = config.get_current_provider_endpoint()
            endpoints.append(endpoint["base_url"])
        
        unique_endpoints = set(endpoints)
        print(f"✓ 多端点轮询测试: 使用了 {len(unique_endpoints)} 个不同端点")
        print(f"  端点列表: {list(unique_endpoints)}")
        
    except Exception as e:
        print(f"❌ 多端点测试失败: {e}")
    finally:
        # 恢复环境变量
        os.environ.clear()
        os.environ.update(old_env)
        config.reload_config()
    
    print("\n🎉 所有测试完成！")

if __name__ == "__main__":
    asyncio.run(test_all_features())