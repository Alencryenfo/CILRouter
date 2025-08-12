#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志模块鲁棒性测试
全面测试极端情况和边界条件
"""

import sys
import os
import json
import time
import threading
import tempfile
import shutil
from pathlib import Path

sys.path.append('.')

def test_logger_edge_cases():
    """测试日志模块的边界情况"""
    print('=== 日志模块边界情况测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 测试1: 无效的日志等级
    print('\n--- 测试无效日志等级 ---')
    logger = CILRouterLogger(log_level='INVALID', log_dir='app/data/log')
    print(f'无效等级logger启用状态: {logger.is_enabled()}')
    
    # 测试2: 空字符串和None参数
    print('\n--- 测试空字符串参数 ---')
    try:
        logger = CILRouterLogger(log_level='', log_dir='')
        print(f'空字符串参数logger创建成功: {logger.is_enabled()}')
    except Exception as e:
        print(f'空字符串参数异常: {e}')
    
    # 测试3: 极长的日志消息
    print('\n--- 测试极长日志消息 ---')
    logger = CILRouterLogger(log_level='DEBUG', log_dir='app/data/log')
    long_message = 'x' * 10000  # 10KB消息
    long_data = {'huge_field': 'y' * 50000}  # 50KB数据
    
    try:
        logger.debug(long_message, long_data)
        print('极长日志消息处理成功')
    except Exception as e:
        print(f'极长日志消息异常: {e}')
    
    # 测试4: None和空值处理
    print('\n--- 测试None和空值 ---')
    try:
        logger.debug(None)
        logger.debug('', {})
        logger.debug('test', None)
        print('None和空值处理成功')
    except Exception as e:
        print(f'None和空值处理异常: {e}')
    
    # 测试5: 特殊字符和Unicode
    print('\n--- 测试特殊字符 ---')
    try:
        special_chars = '测试🚀\n\t\r\\"\\\'NULL\\0'
        unicode_data = {'emoji': '🎉🔥💻', 'chinese': '中文测试', 'escape': '\\n\\t'}
        logger.debug(special_chars, unicode_data)
        print('特殊字符处理成功')
    except Exception as e:
        print(f'特殊字符处理异常: {e}')
    
    print('\n边界情况测试完成')

def test_filesystem_exceptions():
    """测试文件系统异常"""
    print('\n=== 文件系统异常测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 测试1: 不存在的目录
    print('\n--- 测试不存在的目录 ---')
    try:
        logger = CILRouterLogger(log_level='DEBUG', log_dir='/nonexistent/path/logs')
        logger.debug('测试消息')
        print('不存在目录处理成功')
    except Exception as e:
        print(f'不存在目录异常: {e}')
    
    # 测试2: 只读目录（模拟权限问题）
    print('\n--- 测试目录权限 ---')
    temp_dir = tempfile.mkdtemp()
    try:
        # 创建只读目录
        readonly_dir = os.path.join(temp_dir, 'readonly')
        os.makedirs(readonly_dir)
        os.chmod(readonly_dir, 0o444)  # 只读权限
        
        logger = CILRouterLogger(log_level='DEBUG', log_dir=readonly_dir)
        logger.debug('权限测试')
        print('只读目录处理成功')
        
    except Exception as e:
        print(f'只读目录异常: {e}')
    finally:
        # 恢复权限并清理
        if os.path.exists(readonly_dir):
            os.chmod(readonly_dir, 0o755)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 测试3: 磁盘空间满（模拟）
    print('\n--- 测试写入失败 ---')
    # 这个测试比较难模拟，我们测试文件句柄异常
    try:
        logger = CILRouterLogger(log_level='DEBUG', log_dir='app/data/log')
        # 尝试写入大量数据
        for i in range(100):
            logger.debug(f'批量写入测试 {i}', {'data': 'x' * 1000})
        print('批量写入测试成功')
    except Exception as e:
        print(f'批量写入异常: {e}')

def test_large_data_volume():
    """测试大数据量处理"""
    print('\n=== 大数据量测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 创建临时测试目录
    test_dir = tempfile.mkdtemp()
    try:
        logger = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
        
        print('\n--- 测试大量快速写入 ---')
        start_time = time.time()
        
        # 快速写入1000条日志
        for i in range(1000):
            logger.debug(f'快速写入测试 {i}', {
                'index': i,
                'data': f'测试数据_{i}_' + 'x' * 100,
                'timestamp': time.time()
            })
            
            if i % 100 == 0:
                print(f'已写入 {i} 条日志')
        
        elapsed = time.time() - start_time
        print(f'写入1000条日志耗时: {elapsed:.2f}秒')
        
        # 检查文件大小
        log_files = list(Path(test_dir).glob('*.log*'))
        total_size = sum(f.stat().st_size for f in log_files)
        print(f'生成的日志文件数: {len(log_files)}')
        print(f'总文件大小: {total_size / 1024 / 1024:.2f} MB')
        
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

def test_concurrent_access():
    """测试并发访问"""
    print('\n=== 并发访问测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 创建临时测试目录
    test_dir = tempfile.mkdtemp()
    logger = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
    
    results = []
    exceptions = []
    
    def worker_thread(thread_id, count):
        """工作线程函数"""
        try:
            for i in range(count):
                logger.debug(f'线程{thread_id}消息{i}', {
                    'thread_id': thread_id,
                    'message_id': i,
                    'data': f'thread_{thread_id}_msg_{i}'
                })
            results.append(f'线程{thread_id}完成')
        except Exception as e:
            exceptions.append(f'线程{thread_id}异常: {e}')
    
    print('\n--- 启动10个并发线程 ---')
    threads = []
    for i in range(10):
        thread = threading.Thread(target=worker_thread, args=(i, 50))
        threads.append(thread)
        thread.start()
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    print(f'并发测试结果: {len(results)}个线程成功, {len(exceptions)}个异常')
    if exceptions:
        for exc in exceptions[:3]:  # 只显示前3个异常
            print(f'异常详情: {exc}')
    
    # 检查日志文件完整性
    try:
        log_files = list(Path(test_dir).glob('*.log*'))
        total_lines = 0
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8') as f:
                total_lines += sum(1 for _ in f)
        
        print(f'总日志行数: {total_lines}')
        print(f'期望行数: 500 (10线程 × 50消息)')
        
    except Exception as e:
        print(f'日志文件检查异常: {e}')
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

def test_log_rotation_edge_cases():
    """测试日志轮转的极端情况"""
    print('\n=== 日志轮转极端情况测试 ===')
    
    from app.utils.logger import CILRouterLogger
    
    # 创建临时测试目录
    test_dir = tempfile.mkdtemp()
    
    try:
        # 创建小轮转大小的logger (1KB轮转测试)
        logger = CILRouterLogger(log_level='DEBUG', log_dir=test_dir)
        # 修改轮转大小为1KB进行测试
        if logger.logger:
            for handler in logger.logger.handlers:
                if hasattr(handler, 'maxBytes'):
                    handler.maxBytes = 1024  # 1KB
        
        print('\n--- 测试快速轮转 ---')
        
        # 写入足够的数据触发多次轮转
        for i in range(20):
            large_data = {'data': 'x' * 200, 'index': i}  # 每条约300字节
            logger.debug(f'轮转测试消息 {i}', large_data)
        
        # 检查生成的文件数量
        log_files = list(Path(test_dir).glob('*.log*'))
        print(f'生成的日志文件数量: {len(log_files)}')
        
        for log_file in sorted(log_files):
            size = log_file.stat().st_size
            print(f'文件: {log_file.name}, 大小: {size} bytes')
    
    except Exception as e:
        print(f'日志轮转测试异常: {e}')
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == '__main__':
    test_logger_edge_cases()
    test_filesystem_exceptions()
    test_large_data_volume()
    test_concurrent_access()
    test_log_rotation_edge_cases()
    print('\n🎉 所有鲁棒性测试完成！')