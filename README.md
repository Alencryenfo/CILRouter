# CIL Router

轻量、透明、面向多供应商切换的 Claude Code / Anthropic 风格 API 转发器。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

[English](README_EN.md) | 简体中文

> 使用本项目时，请自行确认用途、部署方式和所在地法规合规性。

## 项目定位

CIL Router 解决的是这类场景：

- 你希望对外暴露一个稳定入口，例如 `http://your-router:8000/v1/messages`
- 你不想把真实上游 `API Key` 分发给每个客户端
- 你需要在多个供应商之间切换，或在同一供应商的多个端点之间轮询
- 你希望保留流式响应、原始请求路径和绝大多数请求体内容

这个项目不是 SDK，也不是带管理后台的网关。它更像一个专门做“请求透传 + 鉴权替换 + 供应商切换”的极简代理层。

## 核心能力

- 透明转发所有常见 HTTP 方法：`GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD`、`OPTIONS`、`TRACE`
- 自动把客户端请求转发到当前供应商的对应路径
- 自动注入上游 `Authorization: Bearer <provider_api_key>`
- 支持流式响应透传
- 支持同一供应商下多个端点轮询
- 支持通过 `POST /select` 手动切换当前供应商
- 支持基于 IP 的令牌桶限流
- 支持 Cloudflare / 反向代理场景下识别真实客户端 IP
- 支持控制台日志和 Axiom 日志上报
- 提供 Docker / Docker Compose 部署方式

## 工作方式

假设当前配置为：

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-xxx
CURRENT_PROVIDER_INDEX=0
```

当客户端请求：

```text
POST http://localhost:8000/v1/messages
```

路由器会：

1. 校验是否需要访问鉴权 `AUTH_KEY`
2. 清理不应透传的请求头
3. 选择当前供应商的一个端点
4. 将请求转发到：

```text
https://api.anthropic.com/v1/messages
```

5. 把上游响应原样流回客户端

关键点有两个：

- 客户端发给路由器的 `Authorization` 不会原样转发到上游
- 上游鉴权头始终由路由器根据 `PROVIDER_N_API_KEY` 重新生成

## 快速开始

### 方式一：Docker Compose

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
cp .env.example .env
```

编辑 `.env`，至少设置一组供应商：

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key
CURRENT_PROVIDER_INDEX=0
```

启动：

```bash
docker compose up -d --build
```

验证：

```bash
curl http://localhost:8000/
```

### 方式二：本地运行

```bash
git clone https://github.com/Alencryenfo/CILRouter.git
cd CILRouter
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

如果你只是本地运行服务、不需要测试依赖，也可以改用：

```bash
pip install -r requirements-prod.txt
```

## 配置说明

### 最小可用配置

最少只需要这三项：

```env
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key
CURRENT_PROVIDER_INDEX=0
```

### 供应商配置模型

配置格式固定为：

- `PROVIDER_0_BASE_URL` / `PROVIDER_0_API_KEY`
- `PROVIDER_1_BASE_URL` / `PROVIDER_1_API_KEY`
- `PROVIDER_2_BASE_URL` / `PROVIDER_2_API_KEY`

规则如下：

- 索引必须从 `0` 开始连续递增，不能跳号
- 每个 `PROVIDER_N_BASE_URL` 和 `PROVIDER_N_API_KEY` 必须同时存在
- 可以用逗号分隔多个端点和多个 Key，用于同一供应商内部轮询
- 同一个供应商下，URL 数量和 Key 数量必须严格一致

例如：

```env
PROVIDER_0_BASE_URL=https://api.provider-a.com,https://api2.provider-a.com
PROVIDER_0_API_KEY=key-a-1,key-a-2

PROVIDER_1_BASE_URL=https://api.provider-b.com
PROVIDER_1_API_KEY=key-b-1

CURRENT_PROVIDER_INDEX=0
```

上面表示：

- `PROVIDER_0` 是一个供应商组，组内有 2 个可轮询端点
- `PROVIDER_1` 是另一个供应商组，只有 1 个端点
- 当前默认使用 `PROVIDER_0`

### 环境变量清单

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务监听端口 |
| `CURRENT_PROVIDER_INDEX` | `0` | 当前供应商组索引 |
| `REQUEST_TIMEOUT` | `60` | 上游写入超时，单位秒 |
| `STREAM_TIMEOUT` | `120` | 上游读取超时，单位秒 |
| `AUTH_KEY` | 空 | 为路由器本身开启访问鉴权 |
| `RATE_LIMIT_ENABLED` | `false` | 是否启用限流 |
| `RATE_LIMIT_RPM` | `100` | 每分钟允许请求数 |
| `RATE_LIMIT_BURST` | `10` | 令牌桶突发容量 |
| `RATE_LIMIT_TRUST_PROXY` | `true` | 是否信任代理头部获取真实 IP |
| `LOG_LEVEL` | `INFO` | 控制台日志级别 |
| `CONSOLE_LOG_ENABLED` | `true` | 是否输出控制台日志 |
| `AXIOM_ENABLED` | `false` | 是否启用 Axiom 日志上报 |
| `AXIOM_ENDPOINT` | 空 | 显式指定完整 Axiom ingest URL |
| `AXIOM_DOMAIN` | 空 | Axiom 域名，和 `AXIOM_DATASET` 组合使用 |
| `AXIOM_DATASET` | 空 | Axiom dataset |
| `AXIOM_API_TOKEN` | 空 | Axiom Bearer Token |
| `AXIOM_EVENT_LABELS` | 空 | 统一附加到事件的 labels，值必须是 JSON 对象字符串 |
| `AXIOM_TIMESTAMP_FIELD` | 空 | Axiom 时间字段名 |
| `AXIOM_TIMESTAMP_FORMAT` | 空 | Axiom 时间字段格式 |
| `AXIOM_REQUEST_TIMEOUT` | `2` | Axiom 上报超时 |
| `AXIOM_RETRY_MAX_ATTEMPTS` | `5` | Axiom 最大重试次数 |
| `AXIOM_RETRY_BASE_DELAY` | `1` | Axiom 重试基础退避秒数 |
| `AXIOM_RETRY_MAX_DELAY` | `30` | Axiom 最大退避秒数 |

### 关于 `AUTH_KEY`

`AUTH_KEY` 保护的是“客户端访问路由器”这一步，不是上游供应商。

当前实现中，`AUTH_KEY` 只会应用在通用转发接口上，不会拦截：

- `GET /`
- `POST /select`

启用后，客户端必须带：

```http
Authorization: Bearer <AUTH_KEY>
```

然后路由器会在转发时把这个头替换成当前供应商的真实 API Key。

也就是说：

- 客户端不需要知道供应商真实 Key
- 客户端传给路由器的 `Authorization` 不会原样透传到上游
- 如果你希望零鉴权内网使用，可以不设置 `AUTH_KEY`
- 如果你把服务暴露到公网，建议在反向代理层额外限制 `/select`

## API

项目没有启用 FastAPI 的 `/docs` 和 `/openapi.json`，接口约定以这里和代码实现为准。

### `GET /`

返回当前服务状态、当前供应商索引、全部供应商信息和本次请求的跟踪 ID。

示例：

```bash
curl http://localhost:8000/
```

### `POST /select`

手动切换当前供应商组。请求体不是 JSON，而是一个纯文本整数。

示例：

```bash
curl -X POST http://localhost:8000/select -d "1"
```

成功后会返回切换结果和新供应商信息。

注意：

- 这里切换的是“供应商组”，不是组内单个端点
- 切换结果只影响当前运行进程
- 服务重启后，仍会回到环境变量 `CURRENT_PROVIDER_INDEX` 指定的值

### `/{path:path}`

除 `/`、`/favicon.ico`、`/select` 之外，其余路径都会进入通用转发逻辑。

例如：

```bash
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/messages
curl -X GET "http://localhost:8000/some/path?foo=bar"
```

这些路径会被拼接到当前供应商 `base_url` 后面转发。

## 使用示例

### 基础状态检查

```bash
curl http://localhost:8000/
```

### 开启 `AUTH_KEY` 后访问

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer your-router-auth-key"
```

### 透传 Claude 风格请求

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

### 流式请求

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

## 代理行为细节

### 1. 组间切换，组内轮询

当前项目的选择逻辑是两层的：

- 第一层：`CURRENT_PROVIDER_INDEX` 或 `POST /select` 决定当前使用哪个供应商组
- 第二层：在该供应商组内，多个端点按轮询方式选择

这意味着：

- `PROVIDER_0`、`PROVIDER_1`、`PROVIDER_2` 代表不同供应商组
- 每个供应商组内部可以有多个 URL + Key 对
- 负载均衡只发生在“当前组内部”

### 2. 重试策略

当前实现中：

- 没有请求体的请求会在瞬时网络错误时最多尝试 3 次
- 有请求体的请求默认只尝试 1 次

这样做是为了避免流式请求体或大请求体被重复消费。

### 3. 请求头处理

路由器会在转发前移除这类头：

- 连接管理相关头，例如 `Connection`、`Transfer-Encoding`
- 代理痕迹相关头，例如 `X-Forwarded-For`、`CF-*`
- 客户端原始 `Authorization`
- 客户端原始 `X-Api-Key`

随后再由路由器注入新的上游 `Authorization`。

### 4. 客户端 IP 获取

当 `RATE_LIMIT_TRUST_PROXY=true` 时，限流中间件会优先尝试：

1. `CF-Connecting-IP`
2. `X-Forwarded-For`
3. `X-Real-IP`
4. 连接来源 IP

如果你部署在 Cloudflare、Nginx、Traefik 或其他反向代理后面，通常建议保留默认值 `true`。

如果服务直接暴露在公网，没有可信代理，建议改成：

```env
RATE_LIMIT_TRUST_PROXY=false
```

### 5. 日志

控制台日志默认开启。Axiom 日志是可选项。

如果要启用 Axiom，通常有两种方式：

- 直接设置完整 `AXIOM_ENDPOINT`
- 或同时设置 `AXIOM_DOMAIN` + `AXIOM_DATASET`

如果你走官方 ingest 端点，还需要提供：

```env
AXIOM_API_TOKEN=your-token
```

## 部署方式

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

查看日志：

```bash
docker logs -f cilrouter
```

### Docker Compose

仓库自带 [docker-compose.yml](docker-compose.yml)。

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f cilrouter
```

### 反向代理建议

如果你打算对公网提供服务，建议放在反向代理后面：

- Cloudflare
- Nginx
- Traefik
- Caddy

同时建议开启：

- `AUTH_KEY`
- `RATE_LIMIT_ENABLED=true`
- HTTPS
- 基础访问控制或 IP 白名单

## 故障排查

### 服务启动即退出

优先检查环境变量是否完整：

- 是否至少配置了一组 `PROVIDER_0_BASE_URL` / `PROVIDER_0_API_KEY`
- `CURRENT_PROVIDER_INDEX` 是否在有效范围内
- 多端点配置时，URL 数量和 Key 数量是否一致

### 请求返回 `401`

常见原因：

- 你设置了 `AUTH_KEY`，但客户端没带 `Authorization: Bearer <AUTH_KEY>`
- 客户端传入的 Bearer Token 不等于 `AUTH_KEY`

### 请求返回 `429`

说明限流生效了。检查：

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_RPM`
- `RATE_LIMIT_BURST`
- `RATE_LIMIT_TRUST_PROXY`

如果你在代理后面部署，但没有正确获取真实 IP，多个客户端可能会共用同一个限流桶。

### 请求返回 `502`

这通常表示路由器能收到请求，但连接上游失败。检查：

- `PROVIDER_N_BASE_URL` 是否可访问
- 上游服务是否可用
- 对应 API Key 是否有效
- 容器或主机网络是否允许访问上游

### 没有 `/docs`

这是预期行为。项目显式关闭了 FastAPI 的 Swagger / OpenAPI 页面。

## 开发

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
python -m app.main
```

项目结构：

```text
app/
├── config/         # 环境变量加载与运行时配置
├── http_client/    # 上游 httpx 连接池
├── log/            # 控制台日志与 Axiom 上报
├── middleware/     # 限流中间件
└── main.py         # FastAPI 入口与核心转发逻辑
```

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
