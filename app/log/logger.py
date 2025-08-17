# -*- coding: utf-8 -*-
"""
CIL Router 日志配置模块
提供统一的日志管理功能
"""

import logging
import sys
import re

def setup_logger(
    log_level: str,
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
        '[%(levelname)s][%(asctime)sZ|%(pathname)s:%(lineno)d]%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)
    return logger

_default_logger = None

def get_logger() -> logging.Logger:
    """
    获取默认日志器，如果未设置则使用默认配置

    Returns:
        日志器实例
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger("INFO")
    return _default_logger

def oneline(b: bytes) -> str:
    s = b.decode("utf-8", errors="replace")
    # 1) 把换行符/回车转为可见的 \n \r
    s = s.replace("\r", r"\r").replace("\n", r"\n")
    # 2) 可选：再把其它不可见空白压扁（保留空格）
    s = re.sub(r"[ \t\f\v]+", " ", s)
    return s

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