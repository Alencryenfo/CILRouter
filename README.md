# CIL Router

轻量、透明、面向多供应商切换的 Claude Code / Anthropic 风格 API 转发器。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

[English](README_EN.md) | 简体中文

> 当前文档对应版本 `v2.0.0`。

## 项目定位

CIL Router 适合这类场景：

- 你希望对外暴露一个稳定入口，例如 `http://your-router:8000/v1/messages`
- 你不想把真实上游 `API Key` 分发给每个客户端
- 你需要在多个供应商之间切换，或在同一供应商内轮询多个端点
- 你希望保留流式响应、原始路径和大部分请求体内容

它不是 SDK，也不是完整网关，更像一个专门做“透明转发 + 鉴权替换 + 供应商切换”的极简代理层。

## 核心能力

- 透明转发常见 HTTP 方法：`GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD`、`OPTIONS`、`TRACE`
- 自动把客户端请求转发到当前供应商的对应路径
- 自动注入上游 `Authorization: Bearer <provider_api_key>`
- 支持流式响应透传
- 支持同一供应商下多个端点轮询
- 支持 `POST /select` 手动切换当前供应商
- 支持基于 IP 的令牌桶限流
- 支持 Cloudflare / 反向代理场景下识别真实客户端 IP
- 支持控制台日志和 Axiom 日志上报
- 提供 Docker / Docker Compose 部署方式

## 配置方式

项目当前只使用项目根目录的 `config.yaml`，不再使用旧版 `.env` / `PROVIDER_N_*` 环境变量配置模式。

最小可用配置示例：

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

## 工作方式

假设 `config.yaml` 中当前配置为：

```yaml
current_provider: 0
providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-xxx"
```

当客户端请求：

```text
POST http://localhost:8000/v1/messages
```

路由器会：

1. 校验是否需要访问鉴权 `auth.keys`
2. 清理不应透传的请求头
3. 选择当前供应商的一个端点
4. 将请求转发到 `https://api.anthropic.com/v1/messages`
5. 把上游响应原样流回客户端

关键点：

- 客户端发给路由器的 `Authorization` 不会原样转发到上游
- 上游鉴权头由路由器根据当前供应商的 `api_key` 重新生成

## 快速开始

### 方式一：Docker Compose

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
```

编辑项目根目录下的 `config.yaml`，至少配置一个供应商：

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

启动：

```bash
docker compose up -d --build
```

验证：

```bash
curl http://localhost:8000/
```

说明：

- `docker-compose.yml` 默认把本地 `config.yaml` 挂载到容器内 `/app/config.yaml`
- 这个挂载是只读的，服务启动时读取一次配置
- 修改 `config.yaml` 后需要重启服务才会生效

### 方式二：本地运行

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

如果只想运行服务、不需要测试依赖，也可以使用：

```bash
pip install -r requirements-prod.txt
python -m app.main
```

## `config.yaml` 说明

完整示例：

```yaml
server:
  host: "0.0.0.0"
  port: 8000

auth:
  keys: []
  # keys:
  #   - "your-secret-token-1"
  #   - "your-secret-token-2"

current_provider: 0

providers:
  - endpoints:
      - base_url: "https://api.anthropic.com"
        api_key: "sk-ant-xxx"
  # - endpoints:
  #     - base_url: "https://api.openai.com"
  #       api_key: "sk-openai-xxx"

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

主要字段说明：

- `server.host` / `server.port`：服务监听地址和端口
- `auth.keys`：访问路由器本身所需的 Bearer Token 列表；留空表示不鉴权
- `current_provider`：当前供应商组索引
- `providers[].endpoints[]`：供应商端点和对应 `api_key`
- `request.timeout`：上游写入超时
- `request.stream_timeout`：上游读取超时
- `rate_limit.*`：限流配置
- `logging.*`：控制台日志和 Axiom 上报配置

### `POST /select` 行为

调用 `POST /select` 时：

- 运行中的当前供应商会立即切换
- 切换结果只保留在当前进程内存中
- 服务重启后会重新使用 `config.yaml` 里的 `current_provider`

如果你希望切换结果长期生效，请手动修改 `config.yaml` 后重启服务。

## 关于鉴权

`auth.keys` 保护的是“客户端访问路由器”这一步，不是上游供应商。

启用后，客户端必须带：

```http
Authorization: Bearer <auth.keys 中任意一个 token>
```

然后路由器会在转发时把这个头替换成当前供应商的真实 API Key。

当前实现中，`auth.keys` 只会应用在通用转发接口上，不会拦截：

- `GET /`
- `POST /select`

如果服务暴露到公网，建议在反向代理层额外限制 `/select`。

## API

项目没有启用 FastAPI 的 `/docs` 和 `/openapi.json`，接口约定以 README 和代码实现为准。

### `GET /`

返回当前服务状态、版本、当前供应商索引、全部供应商信息和跟踪 ID。

```bash
curl http://localhost:8000/
```

### `POST /select`

手动切换当前供应商组。请求体不是 JSON，而是一个纯文本整数。

```bash
curl -X POST http://localhost:8000/select -d "1"
```

### `/{path:path}`

除 `/`、`/favicon.ico`、`/select` 之外，其余路径都会进入通用转发逻辑。

```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/messages
curl -X GET "http://localhost:8000/some/path?foo=bar"
```
