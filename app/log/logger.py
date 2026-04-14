# -*- coding: utf-8 -*-
"""
统一日志出口。
"""

import logging
import secrets
import sys
from typing import Any

from app.config import config
from .axiom import axiom_log

LOGGER_NAME = "CILRouter"
TRACE_ID_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class RouterLogger:
    """统一日志出口，同时支持控制台和 Axiom。"""

    _LOGGING_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _sync_level(self) -> None:
        self._logger.setLevel(getattr(logging, config.get_log_level().upper(), logging.INFO))

    def _ensure_console_handler(self) -> None:
        if self._logger.handlers:
            return
        formatter = logging.Formatter(
            '[%(levelname)s][%(asctime)sZ|%(pathname)s:%(lineno)d]%(message)s',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

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


def setup_logger() -> RouterLogger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = False
    return RouterLogger(logger)


_default_logger: RouterLogger | None = None


def get_logger() -> RouterLogger:
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logger()
    return _default_logger


def get_trace_id() -> str:
    return "".join(secrets.choice(TRACE_ID_ALPHABET) for _ in range(20))
