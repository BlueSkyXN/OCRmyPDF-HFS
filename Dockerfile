# 使用官方OCRmyPDF Alpine镜像作为基础
FROM jbarlow83/ocrmypdf-alpine:latest

# 设置环境变量
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# 安装Python和必要的构建工具
RUN apk add --no-cache python3 py3-pip python3-dev build-base

# 设置工作目录
WORKDIR /app

# 创建和激活虚拟环境
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码和启动脚本
COPY main.py .
COPY entrypoint.sh .

# 设置启动脚本权限
RUN chmod +x /app/entrypoint.sh

# 创建临时工作目录
RUN mkdir -p /app/temp
RUN chmod 777 /app/temp

# 暴露端口
EXPOSE 8000

# 使用入口脚本启动应用
ENTRYPOINT ["/app/entrypoint.sh"]

# 复制应用代码和启动脚本
COPY main.py .
COPY entrypoint.sh .

# 设置启动脚本权限
RUN chmod +x /app/entrypoint.sh

# 创建临时工作目录
RUN mkdir -p /app/temp
RUN chmod 777 /app/temp

# 暴露端口
EXPOSE 8000

# 使用入口脚本启动应用
ENTRYPOINT ["/app/entrypoint.sh"]