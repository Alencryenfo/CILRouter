# CIL Router

A lightweight, transparent Claude Code / Anthropic-style API forwarder built around provider switching.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

English | [简体中文](README.md)

> This document targets version `v2.0.0`.

## What It Is For

CIL Router is useful when:

- You want to expose a stable entrypoint such as `http://your-router:8000/v1/messages`
- You do not want to distribute the real upstream `API Key` to every client
- You need to switch between multiple providers, or rotate across multiple endpoints within one provider
- You want to preserve streaming responses, original paths, and most request payloads

It is not an SDK and not a full gateway. It is a small proxy layer focused on transparent forwarding, auth replacement, and provider switching.

## Core Capabilities

- Transparent forwarding for common HTTP methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `TRACE`
- Automatic forwarding to the matching path on the current provider
- Automatic upstream `Authorization: Bearer <provider_api_key>` injection
- Streaming response passthrough
- Round-robin selection across multiple endpoints inside one provider group
- Manual provider-group switching via `POST /select`
- `config.yaml` hot reload
- `POST /select` persists the new provider index back into `config.yaml`
- IP-based token-bucket rate limiting
- Real client IP detection behind Cloudflare or reverse proxies
- Console logging and optional Axiom log delivery
- Docker and Docker Compose deployment support

## Configuration Model

The project now uses only the root-level `config.yaml`. The old `.env` / `PROVIDER_N_*` environment-variable model is no longer the active configuration mechanism.

Minimum working configuration:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

current_provider: 0

providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-your-key"
```

## How It Works

Assume `config.yaml` contains:

```yaml
current_provider: 0
providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-xxx"
```

When a client sends:

```text
POST http://localhost:8000/v1/messages
```

the router will:

1. Check whether router-level auth via `auth.keys` is required
2. Remove headers that should not be forwarded
3. Select one endpoint from the current provider group
4. Forward the request to `https://api.anthropic.com/v1/messages`
5. Stream the upstream response back to the client

Important details:

- The client `Authorization` header is not forwarded upstream as-is
- Upstream auth is regenerated from the current provider `api_key`

## Quick Start

### Option 1: Docker Compose

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
```

Edit the root `config.yaml` and configure at least one provider:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

current_provider: 0

providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-your-key"
```

Start:

```bash
docker compose up -d --build
```

Verify:

```bash
curl http://localhost:8000/
```

Notes:

- `docker-compose.yml` mounts your local `config.yaml` into `/app/config.yaml`
- `docker-compose.yml` runs as `user: "${UID:-1000}:${GID:-1000}"` by default to better match host file permissions
- The mount must stay writable because `POST /select` writes the new `current_provider` back to the file
- Editing `config.yaml` on the host triggers automatic in-process hot reload

### Option 2: Local Run

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

If you only want the service runtime dependencies:

```bash
pip install -r requirements-prod.txt
python -m app.main
```

## `config.yaml` Reference

Full example:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

auth:
  keys: []

current_provider: 0

providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-xxx"

request:
  timeout: 60
  stream_timeout: 120

rate_limit:
  enabled: false
  rpm: 100
  burst: 10
  trust_proxy: true

logging:
  level: INFO
  console: true
  axiom:
    enabled: false
    endpoint: ""
    domain: ""
    dataset: ""
    api_token: ""
    event_labels: ""
    timestamp_field: ""
    timestamp_format: ""
    request_timeout: 2.0
    retry:
      max_attempts: 5
      base_delay: 1.0
      max_delay: 30.0
```

Main fields:

- `server.host` / `server.port`: bind address and port
- `auth.keys`: Bearer tokens accepted by the router; empty means no router-level auth
- `current_provider`: active provider-group index
- `providers[].endpoints[]`: upstream endpoints and their `api_key`
- `request.timeout`: upstream write timeout
- `request.stream_timeout`: upstream read timeout
- `rate_limit.*`: rate-limit settings
- `logging.*`: console and Axiom logging settings

### Hot Reload Behavior

After startup, the service continuously watches `config.yaml`:

- Manual edits to `config.yaml` are reloaded automatically
- `current_provider`, logging level, auth, timeouts, and rate limiting all follow the updated config
- If the file becomes invalid, the service keeps the last valid in-memory config and logs the reload error

### `POST /select` Persistence

When you call `POST /select`:

- The running provider group switches immediately
- `current_provider` in `config.yaml` is updated at the same time
- The new provider index survives restarts

That is why the Docker Compose bind mount must remain writable.

## Authentication

`auth.keys` protects access to the router itself, not the upstream provider.

When enabled, clients must send:

```http
Authorization: Bearer <any token from auth.keys>
```

The router then replaces that header with the real provider API key before forwarding upstream.

In the current implementation, `auth.keys` is only enforced on the generic forwarding route. It does not protect:

- `GET /`
- `POST /select`

If you expose the service publicly, restrict `/select` at the reverse-proxy layer.

## API

FastAPI docs are intentionally disabled. Use this README and the code as the contract.

### `GET /`

Returns service status, version, current provider index, all configured provider info, and the request trace ID.

```bash
curl http://localhost:8000/
```

### `POST /select`

Switch the current provider group manually. The request body is not JSON. It must be a plain integer string.

```bash
curl -X POST http://localhost:8000/select -d "1"
```

### `/{path:path}`

Everything except `/`, `/favicon.ico`, and `/select` goes through the generic forwarding logic.

```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/messages
curl -X GET "http://localhost:8000/some/path?foo=bar"
```
