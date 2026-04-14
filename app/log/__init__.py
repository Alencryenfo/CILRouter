# -*- coding: utf-8 -*-
"""
日志模块初始化
"""

from .logger import get_logger, get_trace_id, setup_logger
from .axiom import axiom_log

__all__ = ["setup_logger", "get_logger", "get_trace_id", "axiom_log"]
