# CIL Router - 极简版

极简的 Claude API 转发器，只负责替换 API Key 并转发请求。

## 功能特性

- 🌐 **全HTTP方法支持**：支持所有HTTP方法（GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, TRACE）
- 🎯 **完全透明转发**：完整转发所有请求内容（URL参数、请求头、请求体）
- 🔑 **智能API Key处理**：自动检测并替换Authorization头部，没有则添加
- 🌊 **流式请求支持**：自动检测并正确处理流式响应（如Claude的stream模式）
- 🔄 **手动切换**：通过 `/select` 接口手动选择供应商
- 🚀 **零配置**：只需配置供应商的 `base_url` 和 `api_key`
- 📦 **轻量级**：只有 3 个依赖包，代码极简

## 快速开始

### 1. 配置供应商

编辑 `config/config.py` 文件，添加你的供应商信息：

```python
providers = [
    {
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-your-api-key-1"
    },
    {
        "base_url": "https://api.provider2.com", 
        "api_key": "your-api-key-2"
    }
]
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务

```bash
python app/main.py
```

服务将在 `http://localhost:8000` 启动。

## API 使用

### 选择供应商

```bash
# 切换到第0个供应商
curl -X POST http://localhost:8000/select -d "0"

# 切换到第1个供应商  
curl -X POST http://localhost:8000/select -d "1"
```

### 转发 Claude API 请求

```bash
# 普通聊天请求
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024
  }'

# 流式聊天请求
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024,
    "stream": true
  }'

# 获取模型列表
curl -X GET http://localhost:8000/v1/models

# 支持所有HTTP方法和路径
curl -X GET "http://localhost:8000/v1/any/path?param=value"
curl -X PUT http://localhost:8000/v1/another/endpoint -d "data"
```

### 查看状态

```bash
curl http://localhost:8000/
```

## Docker 运行

### 方式1：直接使用 docker-compose（推荐）

```bash
# 复制环境变量配置
cp .env.example .env

# 编辑 .env 文件，配置你的供应商信息
# vim .env

# 启动服务
docker-compose up -d
```

### 方式2：手动构建和运行

```bash
# 构建镜像
docker build -t cilrouter .

# 运行容器（使用环境变量）
docker run -d \
  -p 8000:8000 \
  -e PROVIDER_0_BASE_URL="https://api.anthropic.com" \
  -e PROVIDER_0_API_KEY="sk-ant-your-key" \
  -e PROVIDER_1_BASE_URL="https://api.provider2.com" \
  -e PROVIDER_1_API_KEY="your-key-2" \
  --name cilrouter \
  cilrouter
```

### 环境变量配置

**供应商配置格式**
```bash
# 供应商配置（PROVIDER_N_BASE_URL + PROVIDER_N_API_KEY 格式）
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1
PROVIDER_1_BASE_URL=https://api.provider2.com
PROVIDER_1_API_KEY=your-key-2
PROVIDER_2_BASE_URL=https://api.provider3.com
PROVIDER_2_API_KEY=your-key-3

# 注意：索引必须连续，从0开始，中间不能有间断
```

**其他配置**
```bash
HOST=0.0.0.0                    # 服务监听地址
PORT=8000                       # 服务端口
CURRENT_PROVIDER_INDEX=0        # 当前使用的供应商索引
REQUEST_TIMEOUT=60              # 普通请求超时（秒）
STREAM_TIMEOUT=120              # 流式请求超时（秒）
```

## 工作原理

1. **接收请求**：接收任何HTTP方法的请求，完整保留URL参数、请求头、请求体
2. **智能检测**：
   - 自动检测是否为流式请求（检查Accept头部和请求体中的stream参数）
   - 检测并处理Authorization头部
3. **API Key处理**：无论原请求是否有Authorization头部，都替换为当前供应商的API Key
4. **完全转发**：将请求完整转发到当前供应商的 `base_url`，保持所有原始特性
5. **响应处理**：
   - 普通请求：直接返回完整响应
   - 流式请求：建立流式连接，实时转发数据流
6. **透明返回**：将供应商的响应完全透明地返回给客户端

**核心特点**：除了API Key替换，其他完全透明！✨