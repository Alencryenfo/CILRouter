# CIL Router

A lightweight, transparent Claude Code / Anthropic-style API forwarder built around provider switching.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

English | [简体中文](README.md)

> Make sure your usage, deployment model, and local regulatory requirements are your own responsibility.

## What It Is For

CIL Router is useful when:

- You want to expose a stable entrypoint such as `http://your-router:8000/v1/messages`
- You do not want to distribute the real upstream `API Key` to every client
- You need to switch between multiple providers, or rotate across multiple endpoints inside one provider
- You want to preserve streaming responses, request paths, and most request payloads

This project is not an SDK and not a full management gateway. It is a small proxy layer focused on transparent forwarding, auth replacement, and provider switching.

## Core Capabilities

- Transparent forwarding for common HTTP methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `TRACE`
- Automatic forwarding to the matching path on the current provider
- Automatic upstream `Authorization: Bearer <provider_api_key>` injection
- Streaming response passthrough
- Round-robin selection across multiple endpoints inside one provider group
- Manual provider-group switching through `POST /select`
- IP-based token-bucket rate limiting
- Real client IP detection behind Cloudflare or reverse proxies
- Console logging and optional Axiom log delivery
- Docker and Docker Compose deployment support

## How It Works

Assume this configuration:

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-xxx
CURRENT_PROVIDER_INDEX=0
```

When a client sends:

```text
POST http://localhost:8000/v1/messages
```

the router will:

1. Check whether router-level auth via `AUTH_KEY` is required
2. Remove headers that should not be forwarded
3. Select one endpoint from the current provider group
4. Forward the request to:

```text
https://api.anthropic.com/v1/messages
```

5. Stream the upstream response back to the client

Two important details:

- The client's original `Authorization` header is not forwarded upstream as-is
- The upstream auth header is always regenerated from `PROVIDER_N_API_KEY`

## Quick Start

### Option 1: Docker Compose

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
cp .env.example .env
```

Edit `.env` and set at least one provider:

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key
CURRENT_PROVIDER_INDEX=0
```

Start:

```bash
docker compose up -d --build
```

Verify:

```bash
curl http://localhost:8000/
```

### Option 2: Local Run

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

If you only want to run the service locally and do not need test dependencies, you can use:

```bash
pip install -r requirements-prod.txt
```

## Configuration

### Minimum Working Configuration

These three values are enough to boot the service:

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key
CURRENT_PROVIDER_INDEX=0
```

### Provider Model

Provider configuration always uses this pattern:

- `PROVIDER_0_BASE_URL` / `PROVIDER_0_API_KEY`
- `PROVIDER_1_BASE_URL` / `PROVIDER_1_API_KEY`
- `PROVIDER_2_BASE_URL` / `PROVIDER_2_API_KEY`

Rules:

- Indexes must start at `0` and be continuous with no gaps
- Each `PROVIDER_N_BASE_URL` must have a matching `PROVIDER_N_API_KEY`
- Multiple URLs and keys may be comma-separated for round-robin selection inside one provider group
- The number of URLs and keys must match exactly inside the same provider group

Example:

```env
PROVIDER_0_BASE_URL=https://api.provider-a.com,https://api2.provider-a.com
PROVIDER_0_API_KEY=key-a-1,key-a-2

PROVIDER_1_BASE_URL=https://api.provider-b.com
PROVIDER_1_API_KEY=key-b-1

CURRENT_PROVIDER_INDEX=0
```

This means:

- `PROVIDER_0` is one provider group with 2 rotatable endpoints
- `PROVIDER_1` is another provider group with 1 endpoint
- the service starts on `PROVIDER_0`

### Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listening port |
| `CURRENT_PROVIDER_INDEX` | `0` | Current provider-group index |
| `REQUEST_TIMEOUT` | `60` | Upstream write timeout in seconds |
| `STREAM_TIMEOUT` | `120` | Upstream read timeout in seconds |
| `AUTH_KEY` | empty | Enables router-level access auth |
| `RATE_LIMIT_ENABLED` | `false` | Enables rate limiting |
| `RATE_LIMIT_RPM` | `100` | Requests allowed per minute |
| `RATE_LIMIT_BURST` | `10` | Token-bucket burst capacity |
| `RATE_LIMIT_TRUST_PROXY` | `true` | Trust proxy headers for real client IP |
| `LOG_LEVEL` | `INFO` | Console log level |
| `CONSOLE_LOG_ENABLED` | `true` | Enables console logging |
| `AXIOM_ENABLED` | `false` | Enables Axiom log delivery |
| `AXIOM_ENDPOINT` | empty | Full explicit Axiom ingest URL |
| `AXIOM_DOMAIN` | empty | Axiom domain, used with `AXIOM_DATASET` |
| `AXIOM_DATASET` | empty | Axiom dataset |
| `AXIOM_API_TOKEN` | empty | Axiom Bearer token |
| `AXIOM_EVENT_LABELS` | empty | Labels attached to each event, must be a JSON object string |
| `AXIOM_TIMESTAMP_FIELD` | empty | Axiom timestamp field name |
| `AXIOM_TIMESTAMP_FORMAT` | empty | Axiom timestamp format |
| `AXIOM_REQUEST_TIMEOUT` | `2` | Axiom request timeout |
| `AXIOM_RETRY_MAX_ATTEMPTS` | `5` | Max Axiom retry attempts |
| `AXIOM_RETRY_BASE_DELAY` | `1` | Base retry backoff in seconds |
| `AXIOM_RETRY_MAX_DELAY` | `30` | Max retry backoff in seconds |

### About `AUTH_KEY`

`AUTH_KEY` protects access to the router itself, not the upstream provider.
It supports either a single token or multiple comma-separated tokens.

In the current implementation, `AUTH_KEY` is only enforced on the generic forwarding route. It does not protect:

- `GET /`
- `POST /select`

When enabled, clients must send:

```http
Authorization: Bearer <any token from AUTH_KEY>
```

The router then replaces that header with the real provider API key before forwarding upstream.

In practice:

- clients do not need to know the real upstream key
- the client `Authorization` header is never passed upstream unchanged
- you can leave `AUTH_KEY` unset for trusted internal use
- if you want multiple valid tokens, separate them with commas, for example `AUTH_KEY=token-a,token-b`
- if you expose this service publicly, you should restrict `/select` at the reverse-proxy layer

## API

FastAPI docs are intentionally disabled. Use this README and the code as the contract.

### `GET /`

Returns service status, the current provider index, all configured provider info, and the request trace ID.

Example:

```bash
curl http://localhost:8000/
```

### `POST /select`

Switches the current provider group manually. The request body is not JSON. It must be a plain integer string.

Example:

```bash
curl -X POST http://localhost:8000/select -d "1"
```

On success, the service returns the new provider-group information.

Notes:

- this switches the provider group, not an individual endpoint inside the group
- the change only affects the running process
- after a restart, the service falls back to `CURRENT_PROVIDER_INDEX` from the environment

### `/{path:path}`

Everything except `/`, `/favicon.ico`, and `/select` goes through the generic forwarding logic.

Examples:

```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/messages
curl -X GET "http://localhost:8000/some/path?foo=bar"
```

Those paths are appended to the selected provider `base_url`.

## Usage Examples

### Basic Status Check

```bash
curl http://localhost:8000/
```

### Access with `AUTH_KEY` Enabled

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer your-router-auth-key"
```

### Forward a Claude-Style Request

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-router-auth-key" \
  -d '{
    "model": "your-upstream-model",
    "max_tokens": 256,
    "messages": [
      {"role": "user", "content": "Say hello"}
    ]
  }'
```

### Streaming Request

```bash
curl http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-router-auth-key" \
  -d '{
    "model": "your-upstream-model",
    "max_tokens": 256,
    "stream": true,
    "messages": [
      {"role": "user", "content": "Write a short poem"}
    ]
  }'
```

## Proxy Behavior Details

### 1. Group Switching, Endpoint Rotation

The selection model has two layers:

- Layer 1: `CURRENT_PROVIDER_INDEX` or `POST /select` chooses the active provider group
- Layer 2: inside that provider group, endpoints are selected round-robin

That means:

- `PROVIDER_0`, `PROVIDER_1`, `PROVIDER_2` are separate provider groups
- each provider group may contain multiple URL + key pairs
- load distribution only happens inside the current group

### 2. Retry Behavior

In the current implementation:

- requests without a body may be retried up to 3 times on transient network errors
- requests with a body are attempted once by default

This is done to avoid replaying a consumed streaming body or large payload.

### 3. Header Handling

Before forwarding, the router removes headers such as:

- connection-management headers like `Connection` and `Transfer-Encoding`
- proxy-trace headers like `X-Forwarded-For` and `CF-*`
- the original client `Authorization`
- the original client `X-Api-Key`

It then injects a new upstream `Authorization` header.

### 4. Client IP Resolution

When `RATE_LIMIT_TRUST_PROXY=true`, the rate-limiting middleware prefers:

1. `CF-Connecting-IP`
2. `X-Forwarded-For`
3. `X-Real-IP`
4. the socket peer IP

If you run behind Cloudflare, Nginx, Traefik, or another trusted reverse proxy, keeping the default `true` is usually correct.

If the service is exposed directly without a trusted proxy, use:

```env
RATE_LIMIT_TRUST_PROXY=false
```

### 5. Logging

Console logging is enabled by default. Axiom logging is optional.

To enable Axiom, you usually have two choices:

- set a full `AXIOM_ENDPOINT`
- or set both `AXIOM_DOMAIN` and `AXIOM_DATASET`

If you use the official ingest endpoint, you also need:

```env
AXIOM_API_TOKEN=your-token
```

## Deployment

### Docker

```bash
docker build -t cilrouter .

docker run -d \
  --name cilrouter \
  --restart unless-stopped \
  --env-file .env \
  -p 8000:8000 \
  cilrouter
```

View logs:

```bash
docker logs -f cilrouter
```

### Docker Compose

The repository includes [docker-compose.yml](docker-compose.yml).

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f cilrouter
```

### Reverse Proxy Recommendations

If you plan to expose the service publicly, place it behind a reverse proxy such as:

- Cloudflare
- Nginx
- Traefik
- Caddy

You should also strongly consider:

- enabling `AUTH_KEY`
- setting `RATE_LIMIT_ENABLED=true`
- serving over HTTPS
- adding basic access controls or IP allowlists

## Troubleshooting

### Service Exits on Startup

Check the environment first:

- is at least one `PROVIDER_0_BASE_URL` / `PROVIDER_0_API_KEY` pair configured
- is `CURRENT_PROVIDER_INDEX` within range
- if you configured multiple endpoints, do the URL and key counts match

### Request Returns `401`

Common causes:

- `AUTH_KEY` is set, but the client did not send `Authorization: Bearer <AUTH_KEY>`
- the Bearer token sent by the client does not match `AUTH_KEY`

### Request Returns `429`

Rate limiting is active. Check:

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_RPM`
- `RATE_LIMIT_BURST`
- `RATE_LIMIT_TRUST_PROXY`

If you are behind a proxy but real client IPs are not being resolved correctly, multiple users may end up sharing the same bucket.

### Request Returns `502`

This usually means the router received the request but failed to connect to the upstream. Check:

- whether `PROVIDER_N_BASE_URL` is reachable
- whether the upstream service is available
- whether the corresponding API key is valid
- whether the host or container network can reach the upstream

### No `/docs`

That is expected. FastAPI Swagger and OpenAPI endpoints are explicitly disabled.

## Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
python -m app.main
```

Project layout:

```text
app/
├── config/         # Environment loading and runtime config
├── http_client/    # Upstream httpx client pool
├── log/            # Console logging and Axiom delivery
├── middleware/     # Rate-limiting middleware
└── main.py         # FastAPI entrypoint and proxy logic
```

## License

This project is released under the [MIT License](LICENSE).
