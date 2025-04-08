#!/bin/bash

# 打印环境信息用于调试
echo "Starting OCRmyPDF API"
echo "Environment: PORT=$PORT"

# 确保使用正确的端口变量
PORT="${PORT:-8000}"
echo "Using port: $PORT"

# 执行 uvicorn 服务器
exec uvicorn main:app --host 0.0.0.0 --port $PORT