"""
RequestPrep 中间件：最简实现
- 可选鉴权（与 config.AUTH_KEY 对比）
- 净化来访请求头，存入 request.state.sanitized_headers
"""

import hmac

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import config
from app.log.logger import debug, info, warning


PROHIBIT_HEADERS = {
    # 逐跳 / 连接管理
    "authorization", "Authorization",
    "host", "Host",
    "connection", "Connection",
    "keep-alive", "Keep-Alive",
    "proxy-connection", "Proxy-Connection",
    "transfer-encoding", "Transfer-Encoding",
    "te", "TE",
    "trailer", "Trailer",
    "upgrade", "Upgrade",

    # 长度 / 期望（交给 httpx 自己计算）
    "content-length", "Content-Length",
    "expect", "Expect",

    # CDN / 代理痕迹（固定名）
    "cdn-loop", "CDN-Loop",
    "x-forwarded-for", "X-Forwarded-For",
    "x-forwarded-proto", "X-Forwarded-Proto",
    "x-forwarded-host", "X-Forwarded-Host",
    "x-forwarded-server", "X-Forwarded-Server",
    "x-forwarded-port", "X-Forwarded-Port",
    "x-real-ip", "X-Real-IP",
    "true-client-ip", "True-Client-IP",
    "via", "Via",
    "forwarded", "Forwarded",

    # x-api-key 相关（交给 httpx 自己处理）
    "x-api-key", "X-Api-Key",
}


class RequestPrepMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        auth_skip_paths: set[str] | None = None,
        auth_skip_prefixes: tuple[str, ...] = (),
    ):
        super().__init__(app)
        # 默认：只有在配置了 AUTH_KEY 时才启用鉴权
        self.enforce_auth = bool(config.get_request_config()["AUTH_KEY"])
        self.auth_skip_paths = auth_skip_paths or set()
        self.auth_skip_prefixes = auth_skip_prefixes or tuple()

    def _sanitize_headers(self, request: Request) -> dict:
        headers = dict(request.headers)
        # 清理禁止头
        for k in PROHIBIT_HEADERS:
            headers.pop(k, None)
        # 清理 cf-* 等代理痕迹
        for k in list(headers.keys()):
            if k.lower().startswith(("cf-", "cf-access-")):
                headers.pop(k, None)
        # 明确不压缩，交给转发层控制
        headers["accept-encoding"] = "identity"
        return headers

    def _auth_ok(self, request: Request) -> bool:
        if not self.enforce_auth:
            return True
        auth = request.headers.get("authorization") or ""
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer":
            return False
        return hmac.compare_digest(token.strip(), config.AUTH_KEY)

    async def dispatch(self, request: Request, call_next):
        # 鉴权（如启用）；命中白名单则跳过鉴权
        path = request.url.path
        skip_auth = (self.auth_skip_paths and path in self.auth_skip_paths) or any(
            path.startswith(p) for p in self.auth_skip_prefixes
        )
        if self.enforce_auth:
            if skip_auth:
                debug(event="auth_skipped", path=path)
            else:
                if not self._auth_ok(request):
                    warning(event="auth_failed", path=path)
                    return JSONResponse({"detail": "鉴权错误"}, status_code=401)
                else:
                    debug(event="auth_ok", path=path)

        # 净化头，供路由使用
        request.state.headers = self._sanitize_headers(request)
        debug(event="headers_sanitized", path=path)

        return await call_next(request)
