FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 创建非root用户（安全最佳实践）
RUN groupadd -r cilrouter && useradd -r -g cilrouter cilrouter

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制应用代码和配置
COPY app/ ./app/
COPY config/ ./config/

# 创建必要的目录
RUN mkdir -p /app/logs \
    && chown -R cilrouter:cilrouter /app

# 切换到非root用户
USER cilrouter

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 启动命令
CMD ["python", "app/main.py"]