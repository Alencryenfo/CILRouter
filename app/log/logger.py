# -*- coding: utf-8 -*-
"""
CIL Router 日志配置模块
提供统一的日志管理功能
"""

import logging
import sys
import secrets
from typing import Any

from app.config import config
from .axiom import axiom_log


class RouterLogger:
    """统一日志出口，同时支持控制台和 Axiom。"""

    _LOGGING_KWARGS = {"exc_info", "stack_info", "stacklevel", "extra"}

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _sync_level(self) -> None:
        self._logger.setLevel(getattr(logging, config.get_log_level().upper(), logging.INFO))

    def _ensure_console_handler(self) -> None:
        if self._logger.handlers:
            return
        console_formatter = logging.Formatter(
            '[%(levelname)s][%(asctime)sZ|%(pathname)s:%(lineno)d]%(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        self._logger.addHandler(console_handler)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)

    def _render_message(self, msg: Any, args: tuple[Any, ...]) -> str:
        if not args:
            return str(msg)
        try:
            return str(msg) % args
        except Exception:
            return f"{msg} {' '.join(str(arg) for arg in args)}"

    def _log(self, level: int, msg: Any, *args, **kwargs) -> None:
        self._sync_level()
        logging_kwargs = {
            key: kwargs.pop(key)
            for key in list(kwargs.keys())
            if key in self._LOGGING_KWARGS
        }
        console_stacklevel = logging_kwargs.pop("stacklevel", 3)
        enabled_for_level = self._logger.isEnabledFor(level)

        if not enabled_for_level:
            return

        if config.is_console_log_enabled():
            self._ensure_console_handler()
            self._logger.log(
                level,
                msg,
                *args,
                stacklevel=console_stacklevel,
                **logging_kwargs,
            )

        if config.is_axiom_enabled():
            event = dict(kwargs)
            if "信息" not in event and "message" not in event:
                event["message"] = self._render_message(msg, args)
            axiom_log(
                logging.getLevelName(level),
                stacklevel=4,
                **event,
            )

    def debug(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: Any, *args, **kwargs) -> None:
        kwargs.setdefault("exc_info", True)
        self._log(logging.ERROR, msg, *args, **kwargs)

def setup_logger(
    log_level: str,
) -> RouterLogger:
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
    logger.propagate = False
    
    return RouterLogger(logger)

_default_logger = None

def get_logger() -> RouterLogger:
    """
    获取默认日志器，如果未设置则使用默认配置

    Returns:
        日志器实例
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger(config.get_log_level())
    return _default_logger

def get_trace_id()-> str:
    ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return ''.join(secrets.choice(ALPHABET) for _ in range(20))

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
