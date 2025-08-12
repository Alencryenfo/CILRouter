#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高级鲁棒性测试
测试各种数据类型、配置变更、IP阻止等功能
"""

import sys
import os
import json
import time
import threading
import tempfile
import shutil
import asyncio
from pathlib import Path
from unittest.mock import patch

sys.path.append('.')

def test_data_types_encoding():
    """测试各种数据类型和编码情况"""
    print('=== 数据类型和编码测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 创建临时测试目录
    test_dir = tempfile.mkdtemp()
    try:
        logger = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
        
        print('\n--- 测试复杂数据类型 ---')
        complex_data = {
            'integer': 123456789,
            'float': 3.141592653589793,
            'negative': -999,
            'zero': 0,
            'boolean_true': True,
            'boolean_false': False,
            'none_value': None,
            'empty_string': '',
            'empty_list': [],
            'empty_dict': {},
            'nested_dict': {
                'level1': {
                    'level2': {
                        'level3': 'deep_value'
                    }
                }
            },
            'mixed_list': [1, 'string', True, None, {'key': 'value'}],
            'unicode_test': '测试中文🔥💻🎉',
            'special_chars': '\n\t\r\\"\'\x00\x01\x02',
            'large_number': 99999999999999999999999999,
            'scientific': 1.23e-10,
        }
        
        try:
            logger.debug('复杂数据类型测试', complex_data)
            print('复杂数据类型处理成功')
        except Exception as e:
            print(f'复杂数据类型处理异常: {e}')
        
        print('\n--- 测试不可序列化对象 ---')
        try:
            # 测试不能JSON序列化的对象
            import datetime
            import threading
            
            non_serializable = {
                'datetime': datetime.datetime.now(),
                'thread': threading.Thread(),
                'function': print,
                'class': str,
                'file': open(__file__, 'r'),
            }
            
            logger.debug('不可序列化对象测试', non_serializable)
            print('不可序列化对象处理成功')
            
            # 记得关闭文件
            non_serializable['file'].close()
            
        except Exception as e:
            print(f'不可序列化对象处理异常: {e}')
            try:
                non_serializable['file'].close()
            except:
                pass
        
        print('\n--- 测试巨大数据 ---')
        try:
            huge_data = {
                'huge_string': 'x' * 1000000,  # 1MB字符串
                'huge_list': list(range(10000)),  # 1万个元素的列表
                'huge_dict': {f'key_{i}': f'value_{i}' for i in range(1000)}  # 1000个键值对
            }
            
            logger.debug('巨大数据测试', huge_data)
            print('巨大数据处理成功')
        except Exception as e:
            print(f'巨大数据处理异常: {e}')
        
        print('\n--- 测试不同编码 ---')
        try:
            # 测试不同编码的字符串
            encoding_tests = [
                '普通中文',
                '日本語テスト',
                'Тест на русском',
                'العربية اختبار',
                '🌟✨🎊🎈🎉💫⭐',
                '\u200b\u200c\u200d',  # 零宽字符
                '\ufeff',  # BOM
                '\\x41\\x42\\x43',  # 转义字符
            ]
            
            for i, text in enumerate(encoding_tests):
                logger.debug(f'编码测试{i}', {'text': text, 'bytes': text.encode('utf-8', errors='replace')})
            
            print('不同编码处理成功')
        except Exception as e:
            print(f'不同编码处理异常: {e}')
        
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    print('\n数据类型和编码测试完成')


def test_config_reload():
    """测试配置重载和动态变更"""
    print('\n=== 配置重载测试 ===')
    
    # 测试日志等级动态变更
    print('\n--- 测试日志等级动态变更 ---')
    
    test_dir = tempfile.mkdtemp()
    try:
        from app.utils.logger import CILRouterLogger
        
        # 创建不同等级的logger
        logger_debug = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
        logger_info = CILRouterLogger(log_level='INFO', log_dir=test_dir)
        logger_warning = CILRouterLogger(log_level='WARNING', log_dir=test_dir)
        logger_error = CILRouterLogger(log_level='ERROR', log_dir=test_dir)
        logger_none = CILRouterLogger(log_level='NONE', log_dir=test_dir)
        
        # 测试各等级是否正确启用/禁用
        test_cases = [
            (logger_debug, 'DEBUG', True),
            (logger_info, 'INFO', True),
            (logger_warning, 'WARNING', True),
            (logger_error, 'ERROR', True),
            (logger_none, 'NONE', False),
        ]
        
        for logger, level, should_be_enabled in test_cases:
            actual_enabled = logger.is_enabled()
            status = '✅' if actual_enabled == should_be_enabled else '❌'
            print(f'{status} {level}等级logger启用状态: {actual_enabled} (期望: {should_be_enabled})')
    
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    print('\n配置重载测试完成')


def test_ip_blocking_robustness():
    """测试IP阻止功能的鲁棒性"""
    print('\n=== IP阻止功能鲁棒性测试 ===')
    
    # 创建临时IP阻止文件
    temp_ip_file = tempfile.mktemp(suffix='.json')
    temp_dir = tempfile.mkdtemp()
    
    try:
        from app.middleware.rate_limiter import RateLimitMiddleware, RateLimiter
        from fastapi import Request
        from unittest.mock import MagicMock
        
        print('\n--- 测试IP阻止文件格式 ---')
        
        # 测试1: 正常的IP列表
        normal_ips = ["192.168.1.100", "10.0.0.50", "127.0.0.1"]
        with open(temp_ip_file, 'w') as f:
            json.dump(normal_ips, f)
        
        middleware = RateLimitMiddleware(
            app=None, 
            rate_limiter=RateLimiter(),
            enabled=False,
            ip_block_enabled=True,
            blocked_ips_file=temp_ip_file
        )
        
        # 测试正常IP阻止
        for ip in normal_ips:
            is_blocked = middleware._is_ip_blocked(ip)
            print(f'IP {ip} 阻止状态: {is_blocked}')
        
        # 测试未阻止的IP
        test_ip = "8.8.8.8"
        is_blocked = middleware._is_ip_blocked(test_ip)
        print(f'未阻止IP {test_ip} 状态: {is_blocked}')
        
        print('\n--- 测试异常IP格式 ---')
        
        # 测试2: 包含无效IP的列表
        invalid_ips = ["192.168.1.100", "invalid-ip", "", None, 12345, True]
        with open(temp_ip_file, 'w') as f:
            json.dump(invalid_ips, f)
        
        # 重新加载
        middleware._load_blocked_ips()
        
        # 测试有效IP
        is_blocked = middleware._is_ip_blocked("192.168.1.100")
        print(f'有效IP阻止状态: {is_blocked}')
        
        print('\n--- 测试文件异常情况 ---')
        
        # 测试3: 损坏的JSON文件
        with open(temp_ip_file, 'w') as f:
            f.write('{"invalid": json}')
        
        try:
            middleware._load_blocked_ips()
            print('损坏JSON文件处理成功')
        except Exception as e:
            print(f'损坏JSON文件处理异常: {e}')
        
        # 测试4: 不存在的文件
        os.remove(temp_ip_file)
        try:
            middleware._load_blocked_ips()
            print('不存在文件处理成功')
        except Exception as e:
            print(f'不存在文件处理异常: {e}')
        
        print('\n--- 测试IPv6支持 ---')
        
        # 测试IPv6地址
        ipv6_ips = [
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "::1",  # localhost
            "fe80::1%lo0",  # 链路本地地址
            "::ffff:192.0.2.1"  # IPv4映射地址
        ]
        
        # 重新创建文件
        with open(temp_ip_file, 'w') as f:
            json.dump(ipv6_ips, f)
        
        middleware = RateLimitMiddleware(
            app=None,
            rate_limiter=RateLimiter(),
            enabled=False, 
            ip_block_enabled=True,
            blocked_ips_file=temp_ip_file
        )
        
        for ip in ipv6_ips:
            is_blocked = middleware._is_ip_blocked(ip)
            print(f'IPv6 {ip} 阻止状态: {is_blocked}')
        
        print('\n--- 测试热重载 ---')
        
        # 测试文件修改时的热重载
        initial_ips = ["192.168.1.1"]
        with open(temp_ip_file, 'w') as f:
            json.dump(initial_ips, f)
        
        middleware = RateLimitMiddleware(
            app=None,
            rate_limiter=RateLimiter(),
            enabled=False,
            ip_block_enabled=True, 
            blocked_ips_file=temp_ip_file
        )
        
        # 初始检查
        is_blocked = middleware._is_ip_blocked("192.168.1.1")
        print(f'初始IP阻止状态: {is_blocked}')
        
        # 模拟文件修改（修改时间戳）
        time.sleep(0.1)
        updated_ips = ["192.168.1.2"]
        with open(temp_ip_file, 'w') as f:
            json.dump(updated_ips, f)
        
        # 强制检查文件修改
        middleware._last_file_check = 0  # 重置检查时间
        
        # 新的检查
        is_blocked_old = middleware._is_ip_blocked("192.168.1.1") 
        is_blocked_new = middleware._is_ip_blocked("192.168.1.2")
        print(f'更新后 - 旧IP阻止状态: {is_blocked_old}, 新IP阻止状态: {is_blocked_new}')
        
    except Exception as e:
        print(f'IP阻止功能测试异常: {e}')
        
    finally:
        # 清理
        if os.path.exists(temp_ip_file):
            os.remove(temp_ip_file)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    print('\nIP阻止功能鲁棒性测试完成')


def test_exception_handling():
    """测试异常处理和恢复机制"""
    print('\n=== 异常处理和恢复机制测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    test_dir = tempfile.mkdtemp()
    try:
        logger = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
        
        print('\n--- 测试日志记录异常恢复 ---')
        
        # 模拟磁盘满的情况
        with patch('builtins.open', side_effect=OSError("磁盘空间不足")):
            try:
                logger.debug('磁盘满测试', {'data': 'test'})
                print('磁盘满情况处理成功')
            except Exception as e:
                print(f'磁盘满异常: {e}')
        
        # 测试恢复后是否正常工作
        try:
            logger.debug('恢复测试', {'status': 'ok'})
            print('异常恢复成功')
        except Exception as e:
            print(f'异常恢复失败: {e}')
        
        print('\n--- 测试内存不足情况 ---')
        
        # 模拟内存不足
        original_json_dumps = json.dumps
        def memory_error_dumps(*args, **kwargs):
            raise MemoryError("内存不足")
        
        with patch('json.dumps', side_effect=memory_error_dumps):
            try:
                logger.debug('内存不足测试', {'large_data': 'x' * 1000})
                print('内存不足情况处理成功')
            except Exception as e:
                print(f'内存不足异常: {e}')
        
        print('\n--- 测试竞争条件 ---')
        
        # 测试文件轮转时的竞争条件
        def concurrent_logging():
            try:
                for i in range(100):
                    logger.debug(f'并发测试 {i}', {'thread': threading.current_thread().name})
                    time.sleep(0.001)
            except Exception as e:
                print(f'并发日志异常: {e}')
        
        threads = []
        for i in range(5):
            thread = threading.Thread(target=concurrent_logging, name=f'Thread-{i}')
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        print('并发竞争条件测试完成')
        
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    
    print('\n异常处理和恢复机制测试完成')


if __name__ == '__main__':
    test_data_types_encoding()
    test_config_reload() 
    test_ip_blocking_robustness()
    test_exception_handling()
    print('\n🎉 所有高级鲁棒性测试完成！')