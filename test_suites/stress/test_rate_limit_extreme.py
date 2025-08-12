#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流功能极端情况测试
测试令牌桶算法在各种极端条件下的表现
"""

import sys
import os
import asyncio
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import tempfile
import shutil

sys.path.append('.')

async def test_rate_limiter_extreme_cases():
    """测试限流器的极端情况"""
    print('=== 限流器极端情况测试 ===')
    
    from app.middleware.rate_limiter import RateLimiter
    
    print('\n--- 测试极端配置参数 ---')
    
    # 测试1: 极小的限流配置
    try:
        limiter_tiny = RateLimiter(requests_per_minute=1, burst_size=1)
        
        # 快速连续请求
        results = []
        for i in range(5):
            allowed = await limiter_tiny.is_allowed("test_ip")
            results.append(allowed)
            print(f'请求 {i+1}: {"✅允许" if allowed else "❌拒绝"}')
        
        allowed_count = sum(results)
        print(f'极小配置下5次请求中允许了: {allowed_count}次')
        
    except Exception as e:
        print(f'极小配置测试异常: {e}')
    
    print('\n--- 测试极大的限流配置 ---')
    
    # 测试2: 极大的限流配置
    try:
        limiter_huge = RateLimiter(requests_per_minute=1000000, burst_size=10000)
        
        # 大量快速请求
        results = []
        start_time = time.time()
        for i in range(1000):
            allowed = await limiter_huge.is_allowed("test_ip_huge")
            results.append(allowed)
        
        elapsed = time.time() - start_time
        allowed_count = sum(results)
        print(f'极大配置下1000次请求中允许了: {allowed_count}次, 耗时: {elapsed:.3f}秒')
        
    except Exception as e:
        print(f'极大配置测试异常: {e}')
    
    print('\n--- 测试零配置 ---')
    
    # 测试3: 零配置（理论上不允许任何请求）
    try:
        limiter_zero = RateLimiter(requests_per_minute=0, burst_size=0)
        
        results = []
        for i in range(3):
            allowed = await limiter_zero.is_allowed("test_ip_zero")
            results.append(allowed)
            print(f'零配置请求 {i+1}: {"✅允许" if allowed else "❌拒绝"}')
        
        allowed_count = sum(results)
        print(f'零配置下3次请求中允许了: {allowed_count}次')
        
    except Exception as e:
        print(f'零配置测试异常: {e}')
    
    print('\n--- 测试时间跳跃 ---')
    
    # 测试4: 时间跳跃（模拟系统时间调整）
    try:
        limiter_time = RateLimiter(requests_per_minute=60, burst_size=5)
        
        # 正常请求
        allowed1 = await limiter_time.is_allowed("time_test")
        print(f'正常请求: {"✅允许" if allowed1 else "❌拒绝"}')
        
        # 获取bucket状态
        status = await limiter_time.get_bucket_status("time_test")
        if status:
            print(f'Bucket状态: tokens={status["tokens"]}, last_refill={status["last_refill"]}')
        
        # 模拟时间向前跳跃（通过等待模拟）
        await asyncio.sleep(0.1)
        
        allowed2 = await limiter_time.is_allowed("time_test")
        print(f'时间跳跃后请求: {"✅允许" if allowed2 else "❌拒绝"}')
        
    except Exception as e:
        print(f'时间跳跃测试异常: {e}')
    
    print('\n--- 测试大量不同IP ---')
    
    # 测试5: 大量不同IP（测试内存使用）
    try:
        limiter_multi = RateLimiter(requests_per_minute=100, burst_size=10)
        
        # 创建1000个不同的IP
        ip_count = 1000
        allowed_total = 0
        
        start_time = time.time()
        for i in range(ip_count):
            ip = f"192.168.{i // 256}.{i % 256}"
            allowed = await limiter_multi.is_allowed(ip)
            if allowed:
                allowed_total += 1
        
        elapsed = time.time() - start_time
        print(f'大量IP测试: {ip_count}个IP, {allowed_total}个被允许, 耗时: {elapsed:.3f}秒')
        
        # 检查bucket数量
        status = await limiter_multi.get_all_buckets_status()
        print(f'创建的bucket数量: {status["total_buckets"]}')
        
    except Exception as e:
        print(f'大量IP测试异常: {e}')
    
    print('\n限流器极端情况测试完成')


async def test_concurrent_rate_limiting():
    """测试并发限流"""
    print('\n=== 并发限流测试 ===')
    
    from app.middleware.rate_limiter import RateLimiter
    
    # 创建中等限流配置
    limiter = RateLimiter(requests_per_minute=120, burst_size=20)  # 每分钟120个请求，突发20个
    
    print('\n--- 单IP并发测试 ---')
    
    async def single_ip_worker(worker_id, request_count):
        """单个工作线程"""
        allowed_count = 0
        for i in range(request_count):
            allowed = await limiter.is_allowed("concurrent_test_ip")
            if allowed:
                allowed_count += 1
            await asyncio.sleep(0.01)  # 10ms间隔
        return worker_id, allowed_count
    
    # 启动10个并发worker，每个发送20个请求
    tasks = []
    for i in range(10):
        task = asyncio.create_task(single_ip_worker(i, 20))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    total_allowed = sum(result[1] for result in results)
    print(f'10个并发worker，每个20请求 = 200个请求')
    print(f'实际允许的请求数: {total_allowed}')
    print(f'拒绝率: {((200 - total_allowed) / 200) * 100:.1f}%')
    
    # 获取最终bucket状态
    status = await limiter.get_bucket_status("concurrent_test_ip")
    if status:
        print(f'最终bucket状态: tokens={status["tokens"]:.2f}')
    
    print('\n--- 多IP并发测试 ---')
    
    async def multi_ip_worker(worker_id, request_count):
        """多IP工作线程"""
        allowed_count = 0
        for i in range(request_count):
            ip = f"192.168.1.{(worker_id * request_count + i) % 254 + 1}"
            allowed = await limiter.is_allowed(ip)
            if allowed:
                allowed_count += 1
            await asyncio.sleep(0.005)  # 5ms间隔
        return worker_id, allowed_count
    
    # 启动5个并发worker，每个用不同IP发送40个请求
    tasks = []
    for i in range(5):
        task = asyncio.create_task(multi_ip_worker(i, 40))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    total_allowed = sum(result[1] for result in results)
    print(f'5个并发worker，每个40请求(不同IP) = 200个请求')
    print(f'实际允许的请求数: {total_allowed}')
    print(f'允许率: {(total_allowed / 200) * 100:.1f}%')
    
    # 查看总体bucket状态
    all_status = await limiter.get_all_buckets_status()
    print(f'总bucket数量: {all_status["total_buckets"]}')
    
    print('\n并发限流测试完成')


def test_middleware_edge_cases():
    """测试中间件的边界情况"""
    print('\n=== 中间件边界情况测试 ===')
    
    from app.middleware.rate_limiter import RateLimitMiddleware, RateLimiter
    from fastapi import Request
    from starlette.datastructures import Headers, URL, QueryParams
    from unittest.mock import MagicMock
    
    print('\n--- 测试各种IP获取情况 ---')
    
    limiter = RateLimiter(requests_per_minute=60, burst_size=5)
    
    # 测试用例: 各种HTTP头部组合
    test_cases = [
        {
            'name': 'Cloudflare标准',
            'headers': {
                'CF-Connecting-IP': '1.2.3.4',
                'CF-IPCountry': 'US',
                'X-Forwarded-For': '5.6.7.8, 9.10.11.12'
            },
            'expected_ip': '1.2.3.4'
        },
        {
            'name': 'Cloudflare无CF-Connecting-IP',
            'headers': {
                'CF-IPCountry': 'US',
                'X-Forwarded-For': '5.6.7.8, 9.10.11.12'
            },
            'expected_ip': '5.6.7.8'
        },
        {
            'name': '只有X-Real-IP',
            'headers': {
                'X-Real-IP': '8.8.8.8',
                'X-Forwarded-For': '1.1.1.1, 2.2.2.2'
            },
            'expected_ip': '8.8.8.8'
        },
        {
            'name': '只有X-Forwarded-For',
            'headers': {
                'X-Forwarded-For': '7.7.7.7, 8.8.8.8, 9.9.9.9'
            },
            'expected_ip': '7.7.7.7'
        },
        {
            'name': '无代理头部',
            'headers': {},
            'expected_ip': '127.0.0.1'  # 会使用client.host
        },
        {
            'name': '无效IP地址',
            'headers': {
                'X-Forwarded-For': 'invalid-ip, not-an-ip'
            },
            'expected_ip': '127.0.0.1'  # 会回退到client.host
        }
    ]
    
    for case in test_cases:
        middleware = RateLimitMiddleware(
            app=None,
            rate_limiter=limiter,
            enabled=True,
            trust_proxy=True
        )
        
        # 创建模拟请求
        mock_request = MagicMock()
        mock_request.headers = Headers(case['headers'])
        mock_request.client = MagicMock()
        mock_request.client.host = '127.0.0.1'
        
        actual_ip = middleware._get_client_ip(mock_request)
        status = '✅' if actual_ip == case['expected_ip'] else '❌'
        print(f"{status} {case['name']}: 获取到IP {actual_ip} (期望: {case['expected_ip']})")
    
    print('\n--- 测试trust_proxy=False情况 ---')
    
    middleware_no_proxy = RateLimitMiddleware(
        app=None,
        rate_limiter=limiter,
        enabled=True,
        trust_proxy=False
    )
    
    mock_request = MagicMock()
    mock_request.headers = Headers({
        'CF-Connecting-IP': '1.2.3.4',
        'X-Forwarded-For': '5.6.7.8'
    })
    mock_request.client = MagicMock()
    mock_request.client.host = '192.168.1.100'
    
    actual_ip = middleware_no_proxy._get_client_ip(mock_request)
    expected_ip = '192.168.1.100'
    status = '✅' if actual_ip == expected_ip else '❌'
    print(f"{status} 不信任代理: 获取到IP {actual_ip} (期望: {expected_ip})")
    
    print('\n--- 测试IPv6地址验证 ---')
    
    ipv6_test_cases = [
        ('2001:0db8:85a3:0000:0000:8a2e:0370:7334', True),
        ('::1', True),
        ('fe80::1%lo0', True),  # 可能因为%符号导致验证失败，但我们测试看看
        ('192.168.1.1', True),
        ('invalid-ipv6', False),
        ('', False),
        (':::', False)
    ]
    
    for ip, should_be_valid in ipv6_test_cases:
        is_valid = middleware._is_valid_ip(ip)
        status = '✅' if is_valid == should_be_valid else '❌'
        print(f"{status} IP验证 '{ip}': {is_valid} (期望: {should_be_valid})")
    
    print('\n中间件边界情况测试完成')


async def main():
    """主测试函数"""
    await test_rate_limiter_extreme_cases()
    await test_concurrent_rate_limiting()
    test_middleware_edge_cases()
    
    print('\n🎉 所有限流极端情况测试完成！')


if __name__ == '__main__':
    asyncio.run(main())