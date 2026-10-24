import gzip
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
    assert captured["upstream_auth_header"] == "authorization"


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
    assert captured["upstream_auth_header"] == "authorization"


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
    assert captured["upstream_auth_header"] == "authorization"


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
    assert response.json()["detail"]["信息"] == "缺少鉴权令牌，应提供 Authorization 或 X-API-Key"
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
    assert captured["upstream_auth_header"] == "authorization"


def test_set_provider_index_does_not_modify_config_file(tmp_path, monkeypatch):
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

    original = config_file.read_bytes()
    assert config.set_provider_index(1) is True
    assert config.CURRENT_PROVIDER_INDEX == 1
    assert config_file.read_bytes() == original


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
    names = {name.lower() for name in captured["headers"]}
    assert not names.intersection({"authorization", "host", "x-forwarded-for", "x-api-key"})


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


@pytest.mark.parametrize(
    "incoming, expected_status, upstream_header",
    [
        ({"Authorization": "Bearer local-auth"}, 200, "authorization"),
        ({"X-API-Key": "local-auth"}, 200, "x-api-key"),
        ({"X-API-Key": "wrong-auth"}, 401, None),
        ({"Authorization": "Token local-auth"}, 401, None),
        ({"Authorization": "Bearer wrong-auth", "X-API-Key": "local-auth"}, 401, None),
        ({"Authorization": "Bearer local-auth", "X-API-Key": "wrong-auth"}, 200, "authorization"),
    ],
)
def test_message_auth_replaces_client_credentials(main_module, monkeypatch, incoming, expected_status, upstream_header):
    import app.routes.proxy as proxy_module

    captured = []

    async def handle(request):
        captured.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handle))

    async def get_client(base_url):
        return upstream

    monkeypatch.setattr(proxy_module, "get_client_for", get_client)
    with TestClient(main_module.app) as client:
        try:
            response = client.post("/v1/messages", headers=incoming, json={"stream": True})
        finally:
            client.portal.call(upstream.aclose)

    assert response.status_code == expected_status
    if upstream_header is None:
        assert captured == []
    else:
        assert response.content == b"ok"
        assert len(captured) == 1
        headers = captured[0].headers
        expected = "Bearer provider-key" if upstream_header == "authorization" else "provider-key"
        assert headers[upstream_header] == expected
        other_header = "x-api-key" if upstream_header == "authorization" else "authorization"
        assert other_header not in headers
        assert b'"stream":true' in captured[0].content


@pytest.mark.asyncio
@pytest.mark.parametrize("compressed", [False, True])
async def test_proxy_preserves_wire_body_and_representation_headers(main_module, monkeypatch, compressed):
    import app.routes.proxy as proxy_module

    payload = b"data: hello\n\n" * 40
    wire_body = gzip.compress(payload) if compressed else payload
    headers = [("content-length", str(len(wire_body))), ("content-type", "text/event-stream"),
               ("set-cookie", "a=1"), ("set-cookie", "b=2")]
    if compressed:
        headers.append(("content-encoding", "gzip"))

    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield wire_body[:10]
            yield wire_body[10:]

        async def aclose(self):
            self.closed = True

    stream = Stream()

    async def handle(request):
        return httpx.Response(200, headers=headers, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as upstream:
        async def get_client(base_url):
            return upstream

        monkeypatch.setattr(proxy_module, "get_client_for", get_client)
        response = await proxy_module._proxy_request(
            "GET", "v1/models", "", {}, None, False, "test", "test", "authorization"
        )
        body = b"".join([chunk async for chunk in response.body_iterator])

    assert body == wire_body
    assert int(response.headers["content-length"]) == len(body)
    assert response.headers.get("content-encoding") == ("gzip" if compressed else None)
    assert response.headers.getlist("set-cookie") == ["a=1", "b=2"]
    assert stream.closed
