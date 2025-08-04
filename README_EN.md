# CIL Router - Minimalist Claude Code API Forwarder

<div align="center">

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-framework-green.svg)

**Minimalist Claude Code API forwarder designed for API Key replacement and transparent forwarding**

[Features](#features) • [Quick Start](#quick-start) • [Deployment](#deployment) • [API Documentation](#api-documentation) • [Configuration](#configuration)

English | [简体中文](README.md)

</div>

> Warning: Use of this project must comply with local regulations. All consequences are borne by the user.
> 
> This project is built for personal use as open source ~~level rookie~~, heavily AI-coded. Use at your own risk. PRs welcome for feature additions.

---

## 📋 Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Deployment](#deployment)
  - [Local Deployment](#local-deployment)
  - [Docker Deployment](#docker-deployment)
  - [Docker Compose Deployment (Recommended)](#docker-compose-deployment-recommended)
- [Configuration](#configuration)
  - [Environment Variable Configuration](#environment-variable-configuration)
  - [Code Configuration](#code-configuration)
- [API Documentation](#api-documentation)
  - [Basic Endpoints](#basic-endpoints)
  - [Forwarding Endpoints](#forwarding-endpoints)
  - [Usage Examples](#usage-examples)
- [Advanced Features](#advanced-features)
  - [Streaming Request Support](#streaming-request-support)
  - [Authentication Features](#authentication-features)
  - [Health Check](#health-check)
- [Troubleshooting](#troubleshooting)
- [Development Guide](#development-guide)
- [License](#license)

---

## 🚀 Features

### Core Features
- 🌐 **Full HTTP Method Support** - Supports all HTTP methods (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS, TRACE)
- 🎯 **Complete Transparent Forwarding** - Fully forwards all request content (URL parameters, headers, request body)
- 🔑 **Smart API Key Handling** - Automatically detects and replaces Authorization header, adds if missing
- 🌊 **Streaming Request Support** - Automatically detects and correctly handles streaming responses (like Claude's stream mode)
- 🔄 **Manual Provider Switching** - Switch API providers in real-time via `/select` endpoint
- ⚖️ **Load Balancing** - Automatic round-robin load balancing across multiple endpoints within the same provider
- 🔁 **Failure Retry** - Automatic retry on other endpoints when one fails
- 🛡️ **Smart Rate Limiting** - Token bucket algorithm-based IP rate limiting with burst traffic support
- 🌏 **Cloudflare Support** - Complete CDN proxy support for accurate real client IP detection
- 🚀 **Zero Configuration Startup** - Only requires configuring provider `base_url` and `api_key`
- 📦 **Lightweight Design** - Only 3 core dependencies, extremely simple code

### Technical Features
- ⚡ **High Performance** - Based on FastAPI and httpx, supports async concurrency
- 🐳 **Container Ready** - Complete Docker support and health checks
- 🔧 **Flexible Configuration** - Supports both environment variables and code configuration
- 🛡️ **Secure and Reliable** - Optional API key authentication features
- 📊 **Monitoring Friendly** - Built-in status endpoints and health checks

---

## ⚡ Quick Start

### Method 1: Docker Compose (Recommended)

```bash
# 1. Clone the project
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter

# 2. Configure environment variables
cp .env.example .env
vim .env  # Edit configuration file

# 3. Start the service
docker-compose up -d

# 4. Test the service
curl http://localhost:8000/
```

### Method 2: Local Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure providers (choose one)
# Method A: Environment variable configuration
cp .env.example .env
vim .env

# Method B: Code configuration
vim config/config.py

# 3. Start the service
python app/main.py
```

---

## 🚀 Deployment

### Local Deployment

#### Requirements
- Python 3.10+
- pip package manager

#### Detailed Steps

1. **Clone the project**
```bash
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter
```

2. **Create virtual environment (recommended)**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure provider information**

**Method A: Environment Variable Configuration (Recommended)**
```bash
cp .env.example .env
```

Edit `.env` file:
```bash
# Provider configuration
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

PROVIDER_1_BASE_URL=https://api.provider2.com
PROVIDER_1_API_KEY=your-key-2

# Server configuration
HOST=0.0.0.0
PORT=8000
CURRENT_PROVIDER_INDEX=0
```

**Method B: Code Configuration**
Edit `config/config.py`:
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

5. **Start the service**
```bash
python app/main.py
```

6. **Verify installation**
```bash
curl http://localhost:8000/
```

### Docker Deployment

#### Single Container Deployment

```bash
# 1. Build image
docker build -t cilrouter .

# 2. Run container
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

# 3. View logs
docker logs cilrouter

# 4. Test service
curl http://localhost:8000/
```

### Docker Compose Deployment (Recommended)

#### Standard Deployment

```bash
# 1. Prepare configuration file
cp .env.example .env

# 2. Edit environment variables
vim .env
```

`.env` file example:
```bash
# Server configuration
HOST=0.0.0.0
PORT=8000

# Current provider index
CURRENT_PROVIDER_INDEX=0

# Timeout configuration
REQUEST_TIMEOUT=60
STREAM_TIMEOUT=120

# Authentication configuration (optional)
AUTH_KEY=your-secret-auth-key

# Provider configuration
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

PROVIDER_1_BASE_URL=https://api.provider2.com
PROVIDER_1_API_KEY=your-key-2

PROVIDER_2_BASE_URL=https://api.provider3.com
PROVIDER_2_API_KEY=your-key-3
```

```bash
# 3. Start service
docker-compose up -d

# 4. Check status
docker-compose ps
docker-compose logs -f

# 5. Stop service
docker-compose down
```

#### Production Environment Deployment

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
# Production environment startup
docker-compose -f docker-compose.prod.yml up -d
```

---

## ⚙️ Configuration

### Environment Variable Configuration

#### Server Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Service listening address |
| `PORT` | `8000` | Service port |
| `CURRENT_PROVIDER_INDEX` | `0` | Current provider index |

#### Timeout Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_TIMEOUT` | `60` | Regular request timeout (seconds) |
| `STREAM_TIMEOUT` | `120` | Streaming request timeout (seconds) |

#### Authentication Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_KEY` | `` | API access key (optional) |

#### Rate Limiting Configuration
| Variable | Default | Description |
|----------|---------|-----------|
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting functionality |
| `RATE_LIMIT_RPM` | `100` | Requests per minute allowed |
| `RATE_LIMIT_BURST` | `10` | Burst capacity (allows short-term excess over average rate) |
| `RATE_LIMIT_TRUST_PROXY` | `true` | Whether to trust proxy headers for real IP (suitable for Cloudflare etc.) |

#### Provider Configuration
Provider configuration uses `PROVIDER_N_*` format, supports multi-endpoint load balancing:

```bash
# Provider 0 - Single endpoint
PROVIDER_0_BASE_URL=https://api.anthropic.com
PROVIDER_0_API_KEY=sk-ant-your-key-1

# Provider 1 - Multiple endpoints (comma-separated for load balancing)
PROVIDER_1_BASE_URL=https://api.provider2.com,https://api2.provider2.com,https://backup.provider2.com
PROVIDER_1_API_KEY=your-key-2a,your-key-2b,your-key-2c

# Provider 2 - Two endpoints
PROVIDER_2_BASE_URL=https://api.provider3.com,https://api-backup.provider3.com
PROVIDER_2_API_KEY=your-key-3a,your-key-3b

# Continue adding more providers...
```

**Notes:**
- Indexes must start from 0 and be consecutive, no gaps allowed
- Each provider requires both `BASE_URL` and `API_KEY` configuration
- If an index is missing, subsequent providers will be ignored

### Code Configuration

If not using environment variables, you can directly modify the `config/config.py` file:

```python
# config/config.py
DEFAULT_PROVIDERS = [
    {
        "base_url": "https://api.anthropic.com",
        "api_key": "sk-ant-your-key-1"  # Enter your API Key here
    },
    {
        "base_url": "https://api.provider2.com", 
        "api_key": "your-key-2"  # Second provider's API Key
    },
    {
        "base_url": "https://api.provider3.com",
        "api_key": "your-key-3"  # Third provider's API Key
    }
]
```

### Configuration Priority

Configuration loading priority:
1. **Environment Variables** - Highest priority
2. **Code Configuration** - Used when environment variables don't exist

---

## 📚 API Documentation

### Basic Endpoints

#### 1. Status Query

```http
GET /
```

**Response Example:**
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

#### 2. Provider Switching

```http
POST /select
Content-Type: text/plain

0
```

**Request Parameters:**
- Body: Provider index (numeric string, like `"0"`, `"1"`, `"2"`)

**Success Response:**
```json
{
  "success": true,
  "message": "Switched to provider 1",
  "current_index": 1,
  "total_providers": 3
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Invalid provider index: 5. Valid range: 0-2",
  "current_index": 0,
  "total_providers": 3
}
```

### Forwarding Endpoints

#### General Forwarding Rules

All paths except `/` and `/select` will be forwarded to the current provider.

**Forwarding Process:**
1. Preserve all original request content (path, parameters, headers, request body)
2. Replace `Authorization` header with current provider's API Key
3. Forward to current provider's `base_url`
4. Return complete provider response

#### Supported HTTP Methods

- ✅ GET - Query requests
- ✅ POST - Create requests  
- ✅ PUT - Update requests
- ✅ DELETE - Delete requests
- ✅ PATCH - Partial update requests
- ✅ HEAD - Header requests
- ✅ OPTIONS - Options requests
- ✅ TRACE - Trace requests

### Usage Examples

#### Basic Usage

```bash
# 1. Check current status
curl http://localhost:8000/

# 2. Switch to provider 1
curl -X POST http://localhost:8000/select -d "1"

# 3. Send Claude API request
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024
  }'
```

#### Claude API Forwarding Examples

**Regular Chat Request:**
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "Please introduce artificial intelligence"}
    ],
    "max_tokens": 1024
  }'
```

**Streaming Chat Request:**
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "Please write a poem"}
    ],
    "max_tokens": 1024,
    "stream": true
  }'
```

**Get Model List:**
```bash
curl -X GET http://localhost:8000/v1/models
```

**Request with Parameters:**
```bash
curl -X GET "http://localhost:8000/v1/messages/limit?count=10&offset=0"
```

#### Multi-Provider Usage

```bash
# Scenario: Switching between multiple API providers

# 1. Use provider 0 (Anthropic official)
curl -X POST http://localhost:8000/select -d "0"
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 0"}], "max_tokens": 100}'

# 2. Switch to provider 1 (third-party API)
curl -X POST http://localhost:8000/select -d "1" 
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 1"}], "max_tokens": 100}'

# 3. Switch to provider 2 (backup API)
curl -X POST http://localhost:8000/select -d "2"
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello from provider 2"}], "max_tokens": 100}'
```

#### Client Integration Examples

**Python Example:**
```python
import requests
import json

class CILRouterClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    def select_provider(self, index):
        """Switch provider"""
        response = requests.post(f"{self.base_url}/select", data=str(index))
        return response.json()
    
    def chat(self, messages, model="claude-3-5-sonnet-20241022", stream=False):
        """Send chat request"""
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

# Usage example
client = CILRouterClient()

# Switch to provider 1
client.select_provider(1)

# Send chat request
messages = [{"role": "user", "content": "Hello, Claude!"}]
response = client.chat(messages)
print(response)
```

**JavaScript Example:**
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

// Usage example
const client = new CILRouterClient();

// Switch provider and send request
await client.selectProvider(0);
const response = await client.chat([
    { role: 'user', content: 'Hello, Claude!' }
]);
console.log(response);
```

---

## 🔧 Advanced Features

### Streaming Request Support

CIL Router automatically detects and handles streaming requests without additional configuration.

#### Streaming Detection Mechanism

The system detects streaming requests through:
1. **Accept Header Detection** - `Accept: text/event-stream`
2. **Request Body Detection** - Request body contains `"stream": true`

#### Streaming Request Examples

```bash
# Method 1: Via Accept header
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Write a poem"}],
    "max_tokens": 1024
  }'

# Method 2: Via request body parameter
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022", 
    "messages": [{"role": "user", "content": "Write a poem"}],
    "max_tokens": 1024,
    "stream": true
  }'
```

#### Streaming Response Handling

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
            "messages": [{"role": "user", "content": "Write a poem"}],
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

### Authentication Features

CIL Router supports optional API key authentication features.

#### Enable Authentication

Set `AUTH_KEY` in environment variables:
```bash
AUTH_KEY=your-secret-auth-key
```

#### Using Authentication

When authentication is enabled, all forwarding requests (except `/` and `/select`) require providing the correct key in the Authorization header:

```bash
# Correct authentication request
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer your-secret-auth-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 1024
  }'

# Incorrect authentication request (will return 401 error)
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer wrong-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 1024}'
```

#### Authentication Error Response

```json
{
  "detail": "Invalid authentication credentials"
}
```

### Rate Limiting (v1.0.1)

CIL Router includes intelligent rate limiting based on token bucket algorithm.

#### Rate Limiting Configuration

```bash
# Enable rate limiting
RATE_LIMIT_ENABLED=true

# Requests per minute
RATE_LIMIT_RPM=100

# Burst capacity
RATE_LIMIT_BURST=10

# Trust proxy headers for real IP detection
RATE_LIMIT_TRUST_PROXY=true
```

#### Rate Limiting Features

- **Token Bucket Algorithm** - Allows burst traffic while maintaining average rate
- **Per-IP Limiting** - Independent rate limits for each client IP
- **IPv4/IPv6 Support** - Full support for both IP versions
- **Cloudflare Integration** - Automatic real IP detection through CF-Connecting-IP headers
- **Automatic Cleanup** - Expired rate limit buckets are automatically cleaned up

#### Rate Limiting Headers

When rate limiting is active, responses include informational headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1640995200
```

#### Rate Limiting Error Response

When rate limit is exceeded:

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests from 192.168.1.1",
  "requests_per_minute": 100,
  "burst_size": 10,
  "current_tokens": 0,
  "retry_after": 60
}
```

### Load Balancing (v1.0.1)

Support for multiple endpoints within the same provider with automatic load balancing.

#### Multi-Endpoint Configuration

```bash
# Provider with multiple endpoints
PROVIDER_0_BASE_URL=https://api1.example.com,https://api2.example.com,https://api3.example.com
PROVIDER_0_API_KEY=key1,key2,key3
```

#### Load Balancing Features

- **Round-Robin Distribution** - Requests are distributed evenly across endpoints
- **Automatic Failover** - Failed endpoints are automatically retried with other endpoints
- **Independent API Keys** - Each endpoint can have its own API key
- **Health Monitoring** - Failed endpoints are tracked and retried appropriately

### Health Check

CIL Router has built-in health check functionality for containerized deployment and load balancers.

#### Health Check Endpoint

```bash
# Basic health check
curl http://localhost:8000/

# Response example
{
  "app": "CIL Router",
  "version": "1.0.1", 
  "current_provider_index": 0,
  "total_providers": 2,
  "current_provider_endpoints": 1,
  "current_provider_urls": ["https://api.anthropic.com"],
  "load_balancing": "round_robin"
}
```

#### Docker Health Check

Docker Compose configuration automatically includes health check:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

#### Kubernetes Health Check

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

## 🐛 Troubleshooting

### Common Issues

#### 1. Cannot Start Service

**Issue:** `Address already in use`
```bash
ERROR: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8000): address already in use
```

**Solution:**
```bash
# Find process using the port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
PORT=8001 python app/main.py
```

#### 2. Provider Configuration Issues

**Issue:** Invalid provider index
```json
{
  "success": false,
  "message": "无效的供应商索引: 2. 有效范围: 0-1"
}
```

**Solution:**
1. Check if environment variable configuration is consecutive
2. Confirm both `PROVIDER_N_BASE_URL` and `PROVIDER_N_API_KEY` are set
3. Restart service for configuration to take effect

#### 3. Invalid API Key

**Issue:** Provider returns authentication error
```json
{
  "error": {
    "type": "authentication_error",
    "message": "Invalid API Key"
  }
}
```

**Solution:**
1. Check if API Key is correct
2. Confirm API Key format meets provider requirements
3. Verify API Key has sufficient permissions

#### 4. Network Connection Issues

**Issue:** Connection timeout
```bash
httpx.TimeoutException: timeout
```

**Solution:**
1. Check network connection
2. Adjust timeout configuration:
```bash
REQUEST_TIMEOUT=120
STREAM_TIMEOUT=300
```
3. Verify provider URL is accessible

#### 5. Docker Related Issues

**Issue:** Docker build failure
```bash
Error: Could not find config.config module
```

**Solution:**
Ensure project structure is complete with all necessary files:
```bash
# Check project structure
ls -la app/ config/

# Rebuild image
docker build --no-cache -t cilrouter .
```

### Debugging Logs

#### Enable Verbose Logging

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Start service
python app/main.py
```

#### Docker Log Viewing

```bash
# View container logs
docker logs cilrouter

# Real-time log tracking
docker logs -f cilrouter

# View last 100 lines of logs
docker logs --tail 100 cilrouter
```

#### Request Tracing

Use curl's verbose output to debug requests:
```bash
# Show detailed request and response information
curl -v -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "Hello!"}], "max_tokens": 1024}'
```

### Performance Optimization

#### 1. Connection Pool Optimization

Modify `config/config.py` to add connection pool configuration:
```python
# Connection pool configuration
CONNECTION_POOL_SIZE = 100
CONNECTION_POOL_MAX_SIZE = 1000
```

#### 2. Timeout Optimization

Adjust timeout settings based on use case:
```bash
# Fast response scenario
REQUEST_TIMEOUT=30
STREAM_TIMEOUT=60

# Long processing scenario  
REQUEST_TIMEOUT=180
STREAM_TIMEOUT=600
```

#### 3. Resource Limits

Set resource limits when deploying with Docker:
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

## 🛠️ Development Guide

### Project Structure

```
CILRouter/
├── app/
│   ├── __init__.py
│   └── main.py              # Main application file (FastAPI app)
├── config/
│   ├── __init__.py
│   └── config.py            # Configuration management module
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # pytest configuration
│   └── test_main.py         # Unit tests
├── .env.example             # Environment variable example
├── .gitignore               # Git ignore file
├── CLAUDE.md                # Project documentation (private)
├── Dockerfile               # Docker build file
├── docker-compose.yml       # Docker Compose configuration
├── requirements.txt         # Python dependencies
└── README.md               # Project documentation
```

### Local Development

#### 1. Development Environment Setup

```bash
# Clone project
git clone https://github.com/alencryenfo/cilrouter.git
cd cilrouter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio black flake8

# Configure development environment
cp .env.example .env
vim .env
```

#### 2. Code Style

Project uses the following code standards:
- **Python**: PEP 8 standard
- **Formatting Tool**: Black
- **Code Checking**: Flake8

```bash
# Format code
black app/ config/ tests/

# Code checking
flake8 app/ config/ tests/
```

#### 3. Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_main.py::test_root -v

# Generate coverage report
pytest tests/ --cov=app --cov=config --cov-report=html
```

#### 4. Development Server

```bash
# Start development server (auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or run directly
python app/main.py
```

### Extension Development

#### 1. Adding New Features

Add new routes in `app/main.py`:
```python
@app.get("/custom/endpoint")
async def custom_endpoint():
    """Custom endpoint"""
    return {"message": "Custom functionality"}
```

#### 2. Modifying Configuration

Add new configuration items in `config/config.py`:
```python
# New configuration item
custom_setting: str = os.getenv('CUSTOM_SETTING', 'default_value')

def get_custom_setting() -> str:
    """Get custom configuration"""
    return custom_setting
```

#### 3. Adding Middleware

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

### Test Development

#### 1. Writing Unit Tests

```python
# tests/test_custom.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_custom_endpoint():
    """Test custom endpoint"""
    response = client.get("/custom/endpoint")
    assert response.status_code == 200
    assert response.json()["message"] == "Custom functionality"
```

#### 2. Integration Tests

```python
# tests/test_integration.py
import pytest
import httpx

@pytest.mark.asyncio
async def test_full_workflow():
    """Test complete workflow"""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # 1. Check status
        response = await client.get(f"{base_url}/")
        assert response.status_code == 200
        
        # 2. Switch provider
        response = await client.post(f"{base_url}/select", data="1")
        assert response.status_code == 200
        
        # 3. Send request
        response = await client.post(
            f"{base_url}/v1/messages",
            json={
                "model": "claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 10
            }
        )
        # Note: This test requires valid API keys
```

### Deployment Best Practices

#### 1. Environment Separation

```bash
# Development environment
.env.development

# Testing environment  
.env.testing

# Production environment
.env.production
```

#### 2. Security Configuration

Production environment configuration example:
```bash
# .env.production

# Server configuration
HOST=127.0.0.1  # Local access only
PORT=8000

# Enable authentication
AUTH_KEY=your-very-secure-secret-key

# Shorter timeout
REQUEST_TIMEOUT=30
STREAM_TIMEOUT=60

# Provider configuration (from secure sources)
PROVIDER_0_API_KEY=${SECRET_API_KEY_1}
PROVIDER_1_API_KEY=${SECRET_API_KEY_2}
```

#### 3. Monitoring and Logging

```python
# app/main.py - Add logging
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

## 🔒 Security Notes

### API Key Security

1. **Environment Variable Storage** - Always use environment variables to store API keys, never hardcode
2. **Access Control** - Enable `AUTH_KEY` authentication in production environments
3. **Network Isolation** - Consider deploying in internal network environments
4. **Regular Rotation** - Regularly rotate API keys

### Network Security

1. **HTTPS Proxy** - Use reverse proxy (like Nginx) to provide HTTPS in production environments
2. **Firewall Configuration** - Limit source IP access
3. **Rate Limiting** - Consider adding request frequency limits

### Container Security

1. **Non-root User** - Run with non-privileged user inside container
2. **Minimal Privileges** - Only grant necessary system permissions
3. **Image Scanning** - Regularly scan base images for vulnerabilities

---

## 📝 Changelog

### v1.0.1 (Current Version)
- ✅ Smart rate limiting based on token bucket algorithm
- ✅ Burst traffic support with reasonable instantaneous peaks
- ✅ IP-based request frequency control (full IPv4/IPv6 support)
- ✅ Complete Cloudflare proxy support (CF-Connecting-IP, CF-IPCountry, etc.)
- ✅ Configurable proxy trust mode (balance between security and practicality)
- ✅ English error messages for user-friendly experience
- ✅ Auto-expiring bucket cleanup mechanism to prevent memory leaks
- ✅ Multi-endpoint load balancing for improved service availability
- ✅ Automatic failure retry mechanism
- ✅ Environment variable support for comma-separated multi-URL configuration

### v1.0.0
- ✅ Initial version release
- ✅ Support for multi-provider configuration and switching
- ✅ Complete environment variable configuration support
- ✅ Docker and Docker Compose support
- ✅ Automatic streaming request detection and handling
- ✅ Optional API key authentication features
- ✅ Health check and monitoring support
- ✅ Complete documentation and test coverage

### Planned Features
- 📊 Request statistics and monitoring dashboard
- 🔐 More authentication method support
- 🌐 WebSocket support
- 📈 Performance optimization and caching

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the project
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Create Pull Request

### Contribution Guidelines

- Follow existing code style
- Add appropriate tests
- Update documentation
- Ensure all tests pass

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 📞 Support & Feedback

- **Issues**: [GitHub Issues](https://github.com/alencryenfo/cilrouter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/alencryenfo/cilrouter/discussions)

---

<div align="center">

**If this project helps you, please give it a ⭐ Star!**

[⬆ Back to Top](#cil-router---minimalist-claude-api-forwarder)

</div>