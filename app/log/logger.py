# -*- coding: utf-8 -*-
"""
CIL Router 日志配置模块
提供统一的日志管理功能
"""

import logging
import sys

def setup_logger(
    log_level: str = "INFO",
) -> logging.Logger:
    """
    设置日志配置
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        配置好的日志器
    """
    
    # 创建日志器
    logger = logging.getLogger("CILRouter")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # 清除已有的处理器，避免重复
    logger.handlers.clear()
    
    # 创建格式化器
    console_formatter = logging.Formatter(
        '[%(asctime)sZ|%(levelname)s|%(pathname)s:%(lineno)d]%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)
    return logger

_default_logger = None


def get_logger() -> logging.Logger:
    """获取默认日志器"""
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger()
    return _default_logger


# 便捷的日志函数
def debug(msg, *args, **kwargs):
    """记录DEBUG级别日志"""
    get_logger().debug(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    """记录INFO级别日志"""
    get_logger().info(msg, *args, **kwargs)


def warning(msg, *args, **kwargs):
    """记录WARNING级别日志"""
    get_logger().warning(msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    """记录ERROR级别日志"""
    get_logger().error(msg, *args, **kwargs)