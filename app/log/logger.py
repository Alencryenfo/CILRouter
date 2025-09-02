# -*- coding: utf-8 -*-
"""
极简 JSON 日志模块：仅导出函数 debug/info/warning/error。
用法：
  - debug(字段A="...") → {"_time":"...","level":"DEBUG","字段A":"..."}
  - info(path="/", method="GET")
"""

import sys
import json
from datetime import datetime, timezone
from app.config import config

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
_LEVEL_THRESHOLD = _LEVELS.get(str(config.get_log_level()).upper(), 20)

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


def _log(level_field: str, *args, **kwargs) -> None:
    if _LEVELS.get(str(level_field).upper(), 0) < _LEVEL_THRESHOLD:
        return
    data = {"_time": _now_iso(), "level": level_field}
    for a in args:
        if isinstance(a, dict):
            data.update(a)
    data.update(kwargs)
    _emit(data)

def debug(*args, **kwargs) -> None:
    _log("DEBUG", *args, **kwargs)


def info(*args, **kwargs) -> None:
    _log("INFO", *args, **kwargs)


def warning(*args, **kwargs) -> None:
    _log("WARNING", *args, **kwargs)


def error(*args, **kwargs) -> None:
    _log("ERROR", *args, **kwargs)
