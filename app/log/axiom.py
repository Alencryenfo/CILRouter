import httpx
import sys
import os
from app.config import config

ENABLE = config.is_axiom_enabled()

def _caller_info(stacklevel) -> dict:
    """
    返回调用方信息。stacklevel=1 指 axiom_log 的直接调用者；
    若你外面再包一层函数/装饰器，把 stacklevel 调高（例如 2/3）。
    """
    # 用 _getframe 比 inspect.stack() 轻很多
    f = sys._getframe(stacklevel)  # 0:_context_info 1:axiom_log 2:你的调用点
    return {
        # 代码位置信息
        "模块名": f.f_globals.get("__name__", ""),
        "文件路径": f.f_code.co_filename,
        "文件名": os.path.basename(f.f_code.co_filename),
        "行号": f.f_lineno,
        "函数名": f.f_code.co_name,
        "类名": (
            f.f_locals["self"].__class__.__name__ if "self" in f.f_locals else
            (f.f_locals["cls"].__name__ if f.f_locals.get("cls") and isinstance(f.f_locals["cls"], type) else None)
        ),
    }


def axiom_log(level: str, **fields) -> None:
    """
    用法: axiom_log("DEBUG", message="dddd", ddd=45)
    会发送 JSON 数组: [{"timestamp": "...", "level": "DEBUG", "message": "dddd", "ddd": 45}]
    """
    if ENABLE is False:
        return
    event = {
        "level": level,
        **fields,  # 你的任意键值对都直接并入
        "位置信息":_caller_info(2),
    }
    try:
        with httpx.Client() as client:
            # 发送 JSON 数组（多数接收端更通用；需要 NDJSON 的话可自行调整）
            r = client.post("http://cloudbase-vectorhk-aovphq:4864/logs", json=[event])
            r.raise_for_status()
    except httpx.RequestError as e:
        print(f"Axiom上报出现错误: {e}")
    except httpx.HTTPStatusError as e:
        print(f"Axiom上报出现错误: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"Axiom上报出现错误: {e}")
