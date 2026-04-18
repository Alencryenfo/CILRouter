import importlib

import pytest
import httpx
from fastapi.responses import Response
from fastapi.testclient import TestClient


@pytest.fixture
def main_module(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8000
auth:
  keys:
    - "local-auth"
current_provider: 0
providers:
  - endpoints:
      - base_url: "https://provider.example"
        api_key: "provider-key"
request:
  timeout: 60
  stream_timeout: 120
rate_limit:
  enabled: false
logging:
  level: "INFO"
  console: false
  axiom:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    from app.config import config
    import app.routes.proxy as proxy_module

    monkeypatch.setattr(config, "CONFIG_PATH", config_file)
    config.reload_config()
    importlib.reload(proxy_module)

    import app.main as main

    main = importlib.reload(main)
    yield main


def test_models_request_without_authorization_uses_upstream_auth(main_module, monkeypatch):
    captured = {}

    async def fake_proxy_request(*args, **kwargs):
        captured.update(kwargs)
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get("/v1/models")

    assert response.status_code == 204
    assert captured["use_provider_authorization"] is True


def test_models_request_with_valid_authorization_keeps_default_upstream_auth(main_module, monkeypatch):
    captured = {}

    async def fake_proxy_request(*args, **kwargs):
        captured.update(kwargs)
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get("/v1/models", headers={"Authorization": "Bearer local-auth"})

    assert response.status_code == 204
    assert captured["use_provider_authorization"] is True


def test_models_request_with_invalid_authorization_is_allowed(main_module, monkeypatch):
    captured = {}

    async def fake_proxy_request(*args, **kwargs):
        captured.update(kwargs)
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get("/v1/models", headers={"Authorization": "Bearer wrong-auth"})

    assert response.status_code == 204
    assert captured["use_provider_authorization"] is True


def test_non_models_request_without_authorization_is_rejected(main_module, monkeypatch):
    called = False

    async def fake_proxy_request(*args, **kwargs):
        nonlocal called
        called = True
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get("/v1/messages")

    assert response.status_code == 401
    assert response.json()["detail"]["信息"] == "缺少鉴权令牌"
    assert called is False


def test_models_request_with_bad_authorization_scheme_is_allowed(main_module, monkeypatch):
    captured = {}

    async def fake_proxy_request(*args, **kwargs):
        captured.update(kwargs)
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get("/v1/models", headers={"Authorization": "Token local-auth"})

    assert response.status_code == 204
    assert captured["use_provider_authorization"] is True


def test_set_provider_index_syncs_back_to_config_file(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8000
current_provider: 0
providers:
  - endpoints:
      - base_url: "https://provider-a.example"
        api_key: "provider-a-key"
  - endpoints:
      - base_url: "https://provider-b.example"
        api_key: "provider-b-key"
""".strip(),
        encoding="utf-8",
    )

    from app.config import config

    monkeypatch.setattr(config, "CONFIG_PATH", config_file)
    config.reload_config()

    assert config.set_provider_index(1) is True
    assert config.CURRENT_PROVIDER_INDEX == 1
    assert "current_provider: 1" not in config_file.read_text(encoding="utf-8")

def test_reload_config_applies_external_updates(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 8000
current_provider: 0
providers:
  - endpoints:
      - base_url: "https://provider-a.example"
        api_key: "provider-a-key"
  - endpoints:
      - base_url: "https://provider-b.example"
        api_key: "provider-b-key"
logging:
  level: "INFO"
  console: false
  axiom:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    from app.config import config

    monkeypatch.setattr(config, "CONFIG_PATH", config_file)
    config.reload_config()

    config_file.write_text(
        """
server:
  host: "127.0.0.1"
  port: 9000
current_provider: 1
providers:
  - endpoints:
      - base_url: "https://provider-a.example"
        api_key: "provider-a-key"
  - endpoints:
      - base_url: "https://provider-b.example"
        api_key: "provider-b-key"
logging:
  level: "DEBUG"
  console: false
  axiom:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    config.reload_config()
    assert config.CURRENT_PROVIDER_INDEX == 1
    assert config.get_server_config()["PORT"] == 9000
    assert config.get_log_level() == "DEBUG"


def test_proxy_strips_prohibited_headers_case_insensitively(main_module, monkeypatch):
    captured = {}

    async def fake_proxy_request(*args, **kwargs):
        captured["headers"] = args[3]
        return Response(status_code=204)

    import app.routes.proxy as proxy_module

    monkeypatch.setattr(proxy_module, "_proxy_request", fake_proxy_request)

    with TestClient(main_module.app) as client:
        response = client.get(
            "/v1/models",
            headers={
                "Authorization": "Bearer local-auth",
                "Host": "example.com",
                "X-Forwarded-For": "1.2.3.4",
                "X-Api-Key": "secret",
            },
        )

    assert response.status_code == 204
    assert "Authorization" not in captured["headers"]
    assert "Host" not in captured["headers"]
    assert "X-Forwarded-For" not in captured["headers"]
    assert "X-Api-Key" not in captured["headers"]


def test_http_pool_requires_h2_dependency(monkeypatch):
    import app.http_client.http_pool as http_pool

    monkeypatch.setattr(http_pool.importlib.util, "find_spec", lambda name: None)

    with pytest.raises(RuntimeError, match="缺少 h2 依赖"):
        http_pool.ensure_http2_support()


def test_proxy_preserves_duplicate_response_headers():
    from app.routes.proxy import _strip_hop_headers

    headers = httpx.Headers(
        [
            (b"set-cookie", b"a=1"),
            (b"set-cookie", b"b=2"),
            (b"content-type", b"text/plain"),
            (b"connection", b"close"),
        ]
    )

    assert _strip_hop_headers(headers) == [
        (b"set-cookie", b"a=1"),
        (b"set-cookie", b"b=2"),
        (b"content-type", b"text/plain"),
    ]


@pytest.mark.asyncio
async def test_close_rate_limit_middleware_closes_current_runtime_limiter():
    import app.middleware.rate_limiter as rate_limiter_module

    class FakeLimiter:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    middleware = rate_limiter_module.RateLimitMiddleware(
        app=lambda scope, receive, send: None,
        rate_limiter=None,
        enabled=False,
        trust_proxy=True,
    )
    limiter = FakeLimiter()
    middleware.rate_limiter = limiter

    await rate_limiter_module.close_rate_limit_middleware()

    assert limiter.closed is True
