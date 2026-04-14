import httpx
import atexit
import os
import queue
import sys
import threading
from typing import Any

from app.config import config

_AXIOM_QUEUE: "queue.Queue[dict[str, Any] | None]" = queue.Queue(maxsize=1000)
_AXIOM_WORKER = None
_AXIOM_WORKER_LOCK = threading.Lock()
_AXIOM_SHUTTING_DOWN = False


def _report_axiom_failure(message: str) -> None:
    if config.is_console_log_enabled():
        print(message)


def _enqueue_axiom_item(item: dict[str, Any]) -> None:
    if _AXIOM_SHUTTING_DOWN:
        return
    _ensure_axiom_worker()
    _AXIOM_QUEUE.put_nowait(item)


def _backoff_delay(retry_count: int) -> float:
    retry_config = config.get_axiom_retry_config()
    base_delay = max(float(retry_config["base_delay"]), 0.0)
    max_delay = max(float(retry_config["max_delay"]), base_delay)
    if retry_count <= 0:
        return 0.0
    return min(base_delay * (2 ** (retry_count - 1)), max_delay)


def _schedule_retry(item: dict[str, Any], reason: str) -> None:
    retry_config = config.get_axiom_retry_config()
    retry_count = int(item.get("retry_count", 0)) + 1
    max_attempts = max(int(retry_config["max_attempts"]), 0)

    if retry_count > max_attempts:
        _report_axiom_failure(
            f"Axiom上报失败且重试耗尽，日志已丢弃: {reason}"
        )
        return

    retry_item = dict(item)
    retry_item["retry_count"] = retry_count
    delay = _backoff_delay(retry_count)

    def _requeue() -> None:
        try:
            _enqueue_axiom_item(retry_item)
        except queue.Full:
            _report_axiom_failure("Axiom日志队列已满，重试日志已丢弃")
        except Exception as e:
            _report_axiom_failure(f"Axiom重试入队失败: {e}")

    timer = threading.Timer(delay, _requeue)
    timer.name = f"axiom-log-retry-{retry_count}"
    timer.daemon = True
    timer.start()
    _report_axiom_failure(
        f"Axiom上报失败，将在 {delay:.1f}s 后进行第 {retry_count} 次重试: {reason}"
    )


def _axiom_worker() -> None:
    with httpx.Client() as client:
        while True:
            item = _AXIOM_QUEUE.get()
            try:
                if item is None:
                    return
                endpoint = item["endpoint"]
                headers = item["headers"]
                params = item["params"]
                timeout = item["timeout"]
                event = item["event"]
                response = client.post(
                    endpoint,
                    json=[event],
                    headers=headers,
                    params=params,
                    timeout=timeout,
                )
                response.raise_for_status()
            except httpx.RequestError as e:
                if item is not None:
                    _schedule_retry(item, str(e))
            except httpx.HTTPStatusError as e:
                if item is not None:
                    _schedule_retry(item, f"{e.response.status_code} - {e.response.text}")
            except Exception as e:
                if item is not None:
                    _schedule_retry(item, str(e))
            finally:
                _AXIOM_QUEUE.task_done()


def _ensure_axiom_worker() -> None:
    global _AXIOM_WORKER
    with _AXIOM_WORKER_LOCK:
        if _AXIOM_WORKER is not None and _AXIOM_WORKER.is_alive():
            return
        _AXIOM_WORKER = threading.Thread(
            target=_axiom_worker,
            name="axiom-log-worker",
            daemon=True,
        )
        _AXIOM_WORKER.start()


def _shutdown_axiom_worker() -> None:
    global _AXIOM_SHUTTING_DOWN
    _AXIOM_SHUTTING_DOWN = True
    worker = _AXIOM_WORKER
    if worker is None or not worker.is_alive():
        return
    try:
        _AXIOM_QUEUE.put_nowait(None)
    except queue.Full:
        pass


atexit.register(_shutdown_axiom_worker)

def _caller_info(stacklevel: int) -> dict[str, Any]:
    f = sys._getframe(stacklevel)
    return {
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


def axiom_log(level: str, stacklevel: int = 2, **fields) -> None:
    if not config.is_axiom_enabled():
        return
    endpoint = config.get_axiom_endpoint()
    headers = config.get_axiom_headers()
    params = config.get_axiom_query_params()
    timeout = config.get_axiom_timeout()

    if not endpoint:
        _report_axiom_failure(
            "Axiom日志未配置端点，请设置 AXIOM_ENDPOINT，或同时设置 AXIOM_DOMAIN 与 AXIOM_DATASET"
        )
        return
    if "Authorization" not in headers:
        _report_axiom_failure(
            "Axiom日志未配置 AXIOM_API_TOKEN，本条日志已跳过"
        )
        return

    event = {
        "level": level,
        **fields,
        "位置信息": _caller_info(stacklevel),
    }
    try:
        _enqueue_axiom_item({
            "endpoint": endpoint,
            "headers": headers,
            "params": params,
            "timeout": timeout,
            "event": event,
            "retry_count": 0,
        })
    except queue.Full:
        _report_axiom_failure("Axiom日志队列已满，本条日志已丢弃")
    except Exception as e:
        _report_axiom_failure(f"Axiom上报出现错误: {e}")
