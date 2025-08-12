# CIL Router - 极简版 Claude Code API 转发器

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-framework-green.svg)

**极简的 Claude Code API 转发器，专为替换 API Key 和透明转发设计**

[功能特性](#功能特性) • [快速开始](#快速开始) • [部署方式](#部署方式) • [API 文档](#api-文档) • [配置说明](#配置说明)

[English](README_EN.md) | 简体中文

</div>

> 警告：使用本项目必须符合当地相关法规，其一切使用后果由用户自行承担
> 
> 本项目为个人使用构建开源~~水平菜菜~~，且大量AI编码,使用后果自负，欢迎PR增加功能

---

## 📋 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [部署方式](#部署方式)
  - [本地部署](#本地部署)
  - [Docker 部署](#docker-部署)
  - [Docker Compose 部署](#docker-compose-部署推荐)
- [配置说明](#配置说明)
  - [环境变量配置](#环境变量配置)
  - [代码配置](#代码配置)
- [API 文档](#api-文档)
  - [基础接口](#基础接口)
  - [转发接口](#转发接口)
  - [使用示例](#使用示例)
- [高级功能](#高级功能)
  - [流式请求支持](#流式请求支持)
  - [鉴权功能](#鉴权功能)
  - [健康检查](#健康检查)
- [故障排除](#故障排除)
- [开发指南](#开发指南)
- [许可证](#许可证)

---

## 🚀 功能特性

### 核心功能
- 🌐 **全HTTP方法支持** - 支持所有HTTP方法（GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, TRACE）
- 🎯 **完全透明转发** - 完整转发所有请求内容（URL参数、请求头、请求体）
- 🔑 **智能API Key处理** - 自动检测并替换Authorization头部，没有则添加
- 🌊 **流式请求支持** - 自动检测并正确处理流式响应（如Claude的stream模式）
- 🔄 **手动切换供应商** - 通过 `/select` 接口实时切换API供应商
- ⚖️ **负载均衡** - 同供应商内多个端点自动轮询负载均衡
- 🔁 **失败重试** - 端点失败时自动重试其他端点
- 🛡️ **智能限流** - 基于令牌桶算法的IP限流，支持突发流量
- 🌏 **Cloudflare支持** - 完整的CDN代理支持，准确获取真实客户端IP
- 🚀 **零配置启动** - 只需配置供应商的 `base_url` 和 `api_key`
- 📦 **轻量级设计** - 只有 3 个核心依赖包，代码极简

### 技术特点
- ⚡ **高性能** - 基于FastAPI和httpx，支持异步并发
- 🐳 **容器化就绪** - 完整的Docker支持和健康检查
- 🔧 **灵活配置** - 支持环境变量和代码两种配置方式
- 🛡️ **安全可靠** - 可选的API密钥鉴权功能
- 📊 **监控友好** - 内置状态接口和健康检查

---

## ⚡ 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter

# 2. 配置环境变量
cp .env.example .env
vim .env  # 编辑配置文件

# 3. 启动服务
docker-compose up -d

# 4. 测试服务
curl http://localhost:8000/
```

### 方式二：本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置供应商（二选一）
# 方式A：环境变量配置
cp .env.example .env
vim .env

# 方式B：代码配置
vim config/config.py

# 3. 启动服务
python app/main.py
```

---

## 🚀 部署方式

### 本地部署

#### 环境要求
- Python 3.10+
- pip 包管理器

#### 步骤详解

1. **克隆项目**
```bash
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter
```

2. **创建虚拟环境（推荐）**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **配置供应商信息**

**方式A：环境变量配置（推荐）**
```bash
cp .env.example .env
```

编辑 `.env` 文件：
```bash
# 供应商配置
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

PROVIDER_1_BASE_URL=https://api.provider2.com
PROVIDER_1_API_KEY=your-key-2

# 服务器配置
HOST=0.0.0.0
PORT=8000
CURRENT_PROVIDER_INDEX=0
```

**方式B：代码配置**
编辑 `config/config.py`：
```python
DEFAULT_PROVIDERS = [
    {
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-your-key-1"
    },
    {
        "base_url": "https://api.provider2.com", 
        "api_key": "your-key-2"
    }
]
```

5. **启动服务**
```bash
python app/main.py
```

6. **验证安装**
```bash
curl http://localhost:8000/
```

### Docker 部署

#### 单容器部署

```bash
# 1. 构建镜像
docker build -t cilrouter .

# 2. 运行容器
docker run -d \
  -p 8000:8000 \
  -e PROVIDER_0_BASE_URL="https://api.anthropic.com" \
  -e PROVIDER_0_API_KEY="sk-ant-your-key" \
  -e PROVIDER_1_BASE_URL="https://api.provider2.com" \
  -e PROVIDER_1_API_KEY="your-key-2" \
  -e CURRENT_PROVIDER_INDEX="0" \
  --name cilrouter \
  --restart unless-stopped \
  cilrouter

# 3. 查看日志
docker logs cilrouter

# 4. 测试服务
curl http://localhost:8000/
```

### Docker Compose 部署（推荐）

#### 标准部署

```bash
# 1. 准备配置文件
cp .env.example .env

# 2. 编辑环境变量
vim .env
```

`.env` 文件示例：
```bash
# 服务器配置
HOST=0.0.0.0
PORT=8000

# 当前供应商索引
CURRENT_PROVIDER_INDEX=0

# 超时配置
REQUEST_TIMEOUT=60
STREAM_TIMEOUT=120

# 鉴权配置（可选）
AUTH_KEY=your-secret-auth-key

# 供应商配置
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

PROVIDER_1_BASE_URL=https://api.provider2.com
PROVIDER_1_API_KEY=your-key-2

PROVIDER_2_BASE_URL=https://api.provider3.com
PROVIDER_2_API_KEY=your-key-3
```

```bash
# 3. 启动服务
docker-compose up -d

# 4. 查看状态
docker-compose ps
docker-compose logs -f

# 5. 停止服务
docker-compose down
```

#### 生产环境部署

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  cilrouter:
    build: .
    ports:
      - "80:8000"
    env_file:
      - .env.prod
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

```bash
# 生产环境启动
docker-compose -f docker-compose.prod.yml up -d
```

---

## ⚙️ 配置说明

### 环境变量配置

#### 服务器配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务端口 |
| `CURRENT_PROVIDER_INDEX` | `0` | 当前使用的供应商索引 |

#### 超时配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `REQUEST_TIMEOUT` | `60` | 普通请求超时（秒） |
| `STREAM_TIMEOUT` | `120` | 流式请求超时（秒） |

#### 鉴权配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AUTH_KEY` | `` | API访问密钥（可选） |

#### 供应商配置
供应商配置使用 `PROVIDER_N_*` 格式，支持多端点负载均衡：

```bash
# 供应商 0 - 单个端点
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

# 供应商 1 - 多个端点（逗号分隔，实现负载均衡）
PROVIDER_1_BASE_URL=https://api.provider2.com,https://api2.provider2.com,https://backup.provider2.com
PROVIDER_1_API_KEY=your-key-2a,your-key-2b,your-key-2c

# 供应商 2 - 两个端点
PROVIDER_2_BASE_URL=https://api.provider3.com,https://api-backup.provider3.com
PROVIDER_2_API_KEY=your-key-3a,your-key-3b

# 可以继续添加更多供应商...
```

#### 限流配置
| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `RATE_LIMIT_ENABLED` | `false` | 是否启用限流功能 |
| `RATE_LIMIT_RPM` | `100` | 每分钟允许的请求数 |
| `RATE_LIMIT_BURST` | `10` | 突发容量（允许短时间内超过平均速率的请求数） |
| `RATE_LIMIT_TRUST_PROXY` | `true` | 是否信任代理头部获取真实IP（适用于Cloudflare等CDN） |

**注意事项：**
- 索引必须从 0 开始且连续，不能有间断
- 每个供应商都需要同时配置 `BASE_URL` 和 `API_KEY`
- 如果某个索引缺失，后续的供应商将被忽略

### 代码配置

如果不使用环境变量，可以直接修改 `config/config.py` 文件：

```python
# config/config.py
DEFAULT_PROVIDERS = [
    {
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-your-key-1"  # 在这里填入你的 API Key
    },
    {
        "base_url": "https://api.provider2.com", 
        "api_key": "your-key-2"  # 第二个供应商的 API Key
    },
    {
        "base_url": "https://api.provider3.com",
        "api_key": "your-key-3"  # 第三个供应商的 API Key
    }
]
```

### 配置优先级

配置加载优先级如下：
1. **环境变量** - 最高优先级
2. **代码配置** - 当环境变量不存在时使用

---

## 📚 API 文档

### 基础接口

#### 1. 状态查询

```http
GET /
```

**响应示例：**
```json
{
  "app": "CIL Router",
  "version": "1.0.1",
  "current_provider_index": 0,
  "total_providers": 3,
  "current_provider_endpoints": 1,
  "current_provider_urls": ["https://api.anthropic.com"],
  "load_balancing": "round_robin"
}
```

#### 2. 供应商切换

```http
POST /select
Content-Type: text/plain

0
```

**请求参数：**
- Body: 供应商索引（数字字符串，如 `"0"`, `"1"`, `"2"`）

**成功响应：**
```json
{
  "success": true,
  "message": "已切换到供应商 1",
  "current_index": 1,
  "total_providers": 3
}
```

**错误响应：**
```json
{
  "success": false,
  "message": "无效的供应商索引: 5. 有效范围: 0-2",
  "current_index": 0,
  "total_providers": 3
}
```

### 转发接口

#### 通用转发规则

所有非 `/` 和 `/select` 的路径都会被转发到当前供应商。

**转发过程：**
1. 保留原始请求的所有内容（路径、参数、头部、请求体）
2. 替换 `Authorization` 头部为当前供应商的 API Key
3. 转发到当前供应商的 `base_url`
4. 返回供应商的完整响应

#### 支持的HTTP方法

- ✅ GET - 查询请求
- ✅ POST - 创建请求  
- ✅ PUT - 更新请求
- ✅ DELETE - 删除请求
- ✅ PATCH - 部分更新请求
- ✅ HEAD - 头部请求
- ✅ OPTIONS - 选项请求
- ✅ TRACE - 跟踪请求

### 使用示例

#### 基础使用

```bash
# 1. 查看当前状态
curl http://localhost:8000/

# 2. 切换到供应商 1
curl -X POST http://localhost:8000/select -d "1"

# 3. 发送 Claude API 请求
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024
  }'
```

#### Claude API 转发示例

**普通聊天请求：**
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "请介绍一下人工智能"}
    ],
    "max_tokens": 1024
  }'
```

**流式聊天请求：**
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "请写一首诗"}
    ],
    "max_tokens": 1024,
    "stream": true
  }'
```

**获取模型列表：**
```bash
curl -X GET http://localhost:8000/v1/models
```

**带参数的请求：**
```bash
curl -X GET "http://localhost:8000/v1/messages/limit?count=10&offset=0"
```

#### 多供应商使用

```bash
# 场景：在多个API供应商之间切换使用

# 1. 使用供应商 0（Anthropic官方）
curl -X POST http://localhost:8000/select -d "0"
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 0"}], "max_tokens": 100}'

# 2. 切换到供应商 1（第三方API）
curl -X POST http://localhost:8000/select -d "1" 
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 1"}], "max_tokens": 100}'

# 3. 切换到供应商 2（备用API）
curl -X POST http://localhost:8000/select -d "2"
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 2"}], "max_tokens": 100}'
```

#### 客户端集成示例

**Python 示例：**
```python
import requests
import json

class CILRouterClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    def select_provider(self, index):
        """切换供应商"""
        response = requests.post(f"{self.base_url}/select", data=str(index))
        return response.json()
    
    def chat(self, messages, model="claude-3-5-sonnet-20241022", stream=False):
        """发送聊天请求"""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "stream": stream
        }
        
        headers = {"Content-Type": "application/json"}
        if stream:
            headers["Accept"] = "text/event-stream"
            
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
            stream=stream
        )
        
        if stream:
            return response.iter_lines()
        else:
            return response.json()

# 使用示例
client = CILRouterClient()

# 切换到供应商 1
client.select_provider(1)

# 发送聊天请求
messages = [{"role": "user", "content": "Hello, Claude!"}]
response = client.chat(messages)
print(response)
```

**JavaScript 示例：**
```javascript
class CILRouterClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }
    
    async selectProvider(index) {
        const response = await fetch(`${this.baseUrl}/select`, {
            method: 'POST',
            body: index.toString()
        });
        return await response.json();
    }
    
    async chat(messages, model = 'claude-3-5-sonnet-20241022', stream = false) {
        const payload = {
            model,
            messages,
            max_tokens: 1024,
            stream
        };
        
        const headers = {
            'Content-Type': 'application/json'
        };
        
        if (stream) {
            headers['Accept'] = 'text/event-stream';
        }
        
        const response = await fetch(`${this.baseUrl}/v1/messages`, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });
        
        if (stream) {
            return response.body.getReader();
        } else {
            return await response.json();
        }
    }
}

// 使用示例
const client = new CILRouterClient();

// 切换供应商并发送请求
await client.selectProvider(0);
const response = await client.chat([
    { role: 'user', content: 'Hello, Claude!' }
]);
console.log(response);
```

---

## 🔧 高级功能

### 流式请求支持

CIL Router 自动检测并处理流式请求，无需额外配置。

#### 流式检测机制

系统通过以下方式检测流式请求：
1. **Accept头部检测** - `Accept: text/event-stream`
2. **请求体检测** - 请求体中包含 `"stream": true`

#### 流式请求示例

```bash
# 方式1：通过Accept头部
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "写一首诗"}],
    "max_tokens": 1024
  }'

# 方式2：通过请求体参数
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022", 
    "messages": [{"role": "user", "content": "写一首诗"}],
    "max_tokens": 1024,
    "stream": true
  }'
```

#### 流式响应处理

```python
import requests

def handle_stream_response():
    response = requests.post(
        "http://localhost:8000/v1/messages",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        },
        json={
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "写一首诗"}],
            "max_tokens": 1024,
            "stream": True
        },
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            print(line.decode('utf-8'))

handle_stream_response()
```

### 鉴权功能

CIL Router 支持可选的API密钥鉴权功能。

#### 启用鉴权

在环境变量中设置 `AUTH_KEY`：
```bash
AUTH_KEY=your-secret-auth-key
```

#### 使用鉴权

当启用鉴权后，所有转发请求（除 `/` 和 `/select`）都需要在Authorization头部提供正确的密钥：

```bash
# 正确的鉴权请求
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer your-secret-auth-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024
  }'

# 错误的鉴权请求（将返回401错误）
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 1024}'
```

#### 鉴权错误响应

```json
{
  "detail": "Invalid authentication credentials"
}
```

### 健康检查

CIL Router 内置健康检查功能，适用于容器化部署和负载均衡器。

#### 健康检查端点

```bash
# 基本健康检查
curl http://localhost:8000/

# 响应示例
{
  "app": "CIL Router",
  "version": "1.0.0", 
  "current_provider_index": 0,
  "total_providers": 2,
  "current_provider_url": "https://api.anthropic.com"
}
```

#### Docker健康检查

Docker Compose 配置自动包含健康检查：
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

#### Kubernetes健康检查

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: cilrouter
    image: cilrouter:latest
    livenessProbe:
      httpGet:
        path: /
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 30
    readinessProbe:
      httpGet:
        path: /
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 10
```

---

## 🐛 故障排除

### 常见问题

#### 1. 无法启动服务

**问题：** `Address already in use`
```bash
ERROR: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

**解决方案：**
```bash
# 查找占用端口的进程
lsof -i :8000

# 杀死占用进程
kill -9 <PID>

# 或者使用不同端口
PORT=8001 python app/main.py
```

#### 2. 供应商配置问题

**问题：** 供应商索引无效
```json
{
  "success": false,
  "message": "无效的供应商索引: 2. 有效范围: 0-1"
}
```

**解决方案：**
1. 检查环境变量配置是否连续
2. 确认 `PROVIDER_N_BASE_URL` 和 `PROVIDER_N_API_KEY` 都已设置
3. 重启服务使配置生效

#### 3. API Key 无效

**问题：** 供应商返回认证错误
```json
{
  "error": {
    "type": "authentication_error",
    "message": "Invalid API Key"
  }
}
```

**解决方案：**
1. 检查 API Key 是否正确
2. 确认 API Key 格式符合供应商要求
3. 验证 API Key 是否有足够权限

#### 4. 网络连接问题

**问题：** 连接超时
```bash
httpx.TimeoutException: timeout
```

**解决方案：**
1. 检查网络连接
2. 调整超时配置：
```bash
REQUEST_TIMEOUT=120
STREAM_TIMEOUT=300
```
3. 验证供应商 URL 是否可访问

#### 5. Docker 相关问题

**问题：** Docker 构建失败
```bash
Error: Could not find config.config module
```

**解决方案：**
确保项目结构完整，包含所有必要文件：
```bash
# 检查项目结构
ls -la app/ config/

# 重新构建镜像
docker build --no-cache -t cilrouter .
```

### 日志调试

#### 启用详细日志

```bash
# 设置日志级别
export LOG_LEVEL=DEBUG

# 启动服务
python app/main.py
```

#### Docker 日志查看

```bash
# 查看容器日志
docker logs cilrouter

# 实时跟踪日志
docker logs -f cilrouter

# 查看最近100行日志
docker logs --tail 100 cilrouter
```

#### 请求跟踪

使用curl的详细输出来调试请求：
```bash
# 显示详细的请求和响应信息
curl -v -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 1024}'
```

### 性能优化

#### 1. 连接池优化

修改 `config/config.py` 添加连接池配置：
```python
# 连接池配置
CONNECTION_POOL_SIZE = 100
CONNECTION_POOL_MAX_SIZE = 1000
```

#### 2. 超时优化

根据使用场景调整超时设置：
```bash
# 快速响应场景
REQUEST_TIMEOUT=30
STREAM_TIMEOUT=60

# 长时间处理场景  
REQUEST_TIMEOUT=180
STREAM_TIMEOUT=600
```

#### 3. 资源限制

Docker 部署时设置资源限制：
```yaml
services:
  cilrouter:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

---

## 🛠️ 开发指南

### 项目结构

```
CILRouter/
├── app/
│   ├── __init__.py
│   └── main.py              # 主应用文件（FastAPI应用）
├── config/
│   ├── __init__.py
│   └── config.py            # 配置管理模块
├── test_suites/             # 测试套件
│   ├── unit/                # 单元测试
│   ├── integration/         # 集成测试
│   ├── stress/              # 压力测试
│   ├── security/            # 安全测试
│   ├── performance/         # 性能测试
│   └── reports/             # 测试报告
├── .env.example             # 环境变量示例
├── .gitignore               # Git忽略文件
├── CLAUDE.md                # 项目文档（私有）
├── Dockerfile               # Docker构建文件
├── docker-compose.yml       # Docker Compose配置
├── requirements.txt         # Python依赖
└── README.md               # 项目文档
```

### 本地开发

#### 1. 开发环境设置

```bash
# 克隆项目
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-asyncio black flake8

# 配置开发环境
cp .env.example .env
vim .env
```

#### 2. 代码风格

项目使用以下代码规范：
- **Python**: PEP 8 标准
- **格式化工具**: Black
- **代码检查**: Flake8

```bash
# 格式化代码
black app/ config/ tests/

# 代码检查
flake8 app/ config/ tests/
```

#### 3. 运行测试

```bash
# 使用测试运行器（推荐）
python run_tests.py all -v          # 运行所有测试
python run_tests.py quick           # 快速测试
python run_tests.py unit            # 单元测试
python run_tests.py integration     # 集成测试
python run_tests.py stress          # 压力测试
python run_tests.py security        # 安全测试
python run_tests.py report          # 生成测试报告

# 或直接使用pytest
pytest test_suites/ -v              # 运行所有测试
pytest test_suites/unit/ -v         # 运行单元测试

# 生成覆盖率报告
pytest test_suites/ --cov=app --cov=config --cov-report=html
```

#### 4. 开发服务器

```bash
# 启动开发服务器（自动重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者直接运行
python app/main.py
```

### 扩展开发

#### 1. 添加新功能

在 `app/main.py` 中添加新的路由：
```python
@app.get("/custom/endpoint")
async def custom_endpoint():
    """自定义端点"""
    return {"message": "Custom functionality"}
```

#### 2. 修改配置

在 `config/config.py` 中添加新的配置项：
```python
# 新配置项
custom_setting: str = os.getenv('CUSTOM_SETTING', 'default_value')

def get_custom_setting() -> str:
    """获取自定义配置"""
    return custom_setting
```

#### 3. 添加中间件

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 测试开发

#### 1. 编写单元测试

```python
# test_suites/unit/test_custom.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_custom_endpoint():
    """测试自定义端点"""
    response = client.get("/custom/endpoint")
    assert response.status_code == 200
    assert response.json()["message"] == "Custom functionality"
```

#### 2. 集成测试

```python
# test_suites/integration/test_integration.py
import pytest
import httpx

@pytest.mark.asyncio
async def test_full_workflow():
    """测试完整工作流程"""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # 1. 检查状态
        response = await client.get(f"{base_url}/")
        assert response.status_code == 200
        
        # 2. 切换供应商
        response = await client.post(f"{base_url}/select", data="1")
        assert response.status_code == 200
        
        # 3. 发送请求
        response = await client.post(
            f"{base_url}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10
            }
        )
        # 注：这个测试需要有效的API密钥
```

### 部署最佳实践

#### 1. 环境分离

```bash
# 开发环境
.env.development

# 测试环境  
.env.testing

# 生产环境
.env.production
```

#### 2. 安全配置

生产环境配置示例：
```bash
# .env.production

# 服务器配置
HOST=127.0.0.1  # 仅本地访问
PORT=8000

# 启用鉴权
AUTH_KEY=your-very-secure-secret-key

# 较短的超时时间
REQUEST_TIMEOUT=30
STREAM_TIMEOUT=60

# 供应商配置（从安全的地方获取）
PROVIDER_0_API_KEY=${SECRET_API_KEY_1}
PROVIDER_1_API_KEY=${SECRET_API_KEY_2}
```

#### 3. 监控和日志

```python
# app/main.py - 添加日志记录
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.3f}s"
    )
    
    return response
```

---

## 🔒 安全说明

### API Key 安全

1. **环境变量存储** - 始终使用环境变量存储API密钥，never硬编码
2. **访问控制** - 在生产环境中启用 `AUTH_KEY` 鉴权
3. **网络隔离** - 考虑在内网环境中部署
4. **定期轮换** - 定期更换API密钥

### 网络安全

1. **HTTPS代理** - 在生产环境中使用反向代理（如Nginx）提供HTTPS
2. **防火墙配置** - 限制访问来源IP
3. **速率限制** - 考虑添加请求频率限制

### 容器安全

1. **非root用户** - 容器内使用非特权用户运行
2. **最小权限** - 只授予必要的系统权限
3. **镜像扫描** - 定期扫描基础镜像漏洞

---

## 📝 更新日志

### v1.0.1 (当前版本)
- ✅ 基于令牌桶算法的智能限流
- ✅ 支持突发流量处理，允许合理的瞬时高峰
- ✅ 基于IP的请求频率控制（完整支持IPv4/IPv6）
- ✅ 完整的Cloudflare代理支持（CF-Connecting-IP, CF-IPCountry等）
- ✅ 可配置代理信任模式（安全性与实用性平衡）
- ✅ 中文错误提示信息，用户体验友好
- ✅ 自动过期bucket清理机制，防止内存泄露
- ✅ 多端点负载均衡，提高服务可用性
- ✅ 自动失败重试机制
- ✅ 环境变量支持逗号分隔的多URL配置

### v1.0.0
- ✅ 初始版本发布
- ✅ 支持多供应商配置和切换
- ✅ 完整的环境变量配置支持
- ✅ Docker 和 Docker Compose 支持
- ✅ 流式请求自动检测和处理
- ✅ 可选的API密钥鉴权功能
- ✅ 健康检查和监控支持
- ✅ 完整的文档和测试覆盖

### 计划功能
- 📊 请求统计和监控面板
- 🔐 更多鉴权方式支持
- 🌐 WebSocket 支持  
- 📈 性能优化和缓存

---

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

### 贡献规范

- 遵循现有代码风格
- 添加适当的测试
- 更新文档
- 确保所有测试通过

---

## 📄 许可证

本项目采用 MIT 许可证。详情请参阅 [LICENSE](LICENSE) 文件。

---

## 📞 支持与反馈

- **Issues**: [GitHub Issues](https://github.com/alencryenfo/cilrouter/issues)
- **讨论**: [GitHub Discussions](https://github.com/alencryenfo/cilrouter/discussions)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star！**

[⬆ 回到顶部](#cil-router---极简版-claude-api-转发器)

</div>
