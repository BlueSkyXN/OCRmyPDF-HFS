# 使用官方 Python 3.9 slim 镜像作为基础
FROM python:3.9-slim

# 设置环境变量，防止安装过程中出现交互式提示
ENV DEBIAN_FRONTEND=noninteractive
# 设置默认端口
ENV PORT=8000

# 更新包列表并安装系统依赖:
# - ocrmypdf: 核心工具
# - ghostscript: PDF 处理依赖
# - tesseract-ocr: OCR 引擎
# - tesseract-ocr-eng: Tesseract 英语语言包
# - tesseract-ocr-chi-sim: Tesseract 简体中文语言包 (包含数字识别能力)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ocrmypdf \
    ghostscript \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-chi-sim \
    # 如果还需要其他语言，在这里添加相应的 tesseract-ocr-[LANG] 包
    # 清理 apt 缓存以减小镜像大小
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件
COPY requirements.txt .

# 安装 Python 依赖
# --no-cache-dir 减小镜像大小
RUN pip install --no-cache-dir -r requirements.txt

# 复制 FastAPI 应用代码和入口脚本
COPY main.py .
COPY entrypoint.sh .

# 设置入口脚本可执行权限
RUN chmod +x /app/entrypoint.sh

# 暴露端口
EXPOSE 8000

# 使用入口脚本启动应用
ENTRYPOINT ["/app/entrypoint.sh"]