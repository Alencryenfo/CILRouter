FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 安装运行时系统依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# 创建非root用户（安全最佳实践）
RUN groupadd --system cilrouter \
    && useradd --system --gid cilrouter --home-dir /app --no-create-home cilrouter

# 复制并安装生产依赖
COPY requirements-prod.txt ./
RUN python -m pip install -r requirements-prod.txt

# 复制应用代码
COPY --chown=cilrouter:cilrouter app/ ./app/
COPY --chown=cilrouter:cilrouter config.yaml ./config.yaml

# 创建必要的目录
RUN install -d -o cilrouter -g cilrouter /app/logs

# 切换到非root用户
USER cilrouter

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/', timeout=5)" || exit 1

# 启动命令
CMD ["python", "-m", "app.main"]
