---
title: OCRmyPDF API 接口 # 显示在 Space 页面的标题 (可自定义)
emoji: 📄 # Space 图标的 Emoji (可选)
colorFrom: blue # 主题颜色起始 (可选)
colorTo: green # 主题颜色结束 (可选)
sdk: docker # 指定这是一个基于 Docker 的 Space (非常重要)
app_port: 8000 # 你的 FastAPI 应用在容器内部监听的端口 (必须与 Dockerfile CMD 中指定的端口一致)
pinned: false # 是否在你的个人资料页置顶这个 Space (可选)
---

# OCRmyPDF API 服务

本项目提供一个基于FastAPI的REST API，用于通过OCRmyPDF对PDF文件进行OCR处理，添加可搜索的文本层。API支持中文和英文OCR识别。

## 🔒 安全性 (Security)

本项目已经过全面的安全审查和改进：
- ✅ 所有依赖包已更新，修复已知安全漏洞
- ✅ 实施了资源泄漏保护
- ✅ 添加了 DoS 攻击防护
- ✅ 遵循安全最佳实践

详细信息请查看 [SECURITY.md](SECURITY.md) 和 [CODE_REVIEW_REPORT.md](CODE_REVIEW_REPORT.md)

## 部署到Hugging Face Spaces

### 方法1：直接从GitHub仓库部署

1. 登录Hugging Face账户
2. 创建新的Space:
   - 点击"Create New Space"
   - 输入名称，例如"ocrmypdf-api"
   - 选择"Docker"作为Space SDK
   - 选择适当的硬件规格（推荐：CPU-M或更高配置，以处理大型PDF）
   - 输入GitHub仓库URL
   - 点击"Create Space"

### 方法2：手动上传文件

1. 创建新的Space，选择"Docker"作为Space SDK
2. 上传以下文件到Space:
   - `Dockerfile`
   - `requirements.txt`
   - `main.py`
   - `entrypoint.sh`
   - `README.md`(可选)
3. Space会自动构建Docker镜像并启动服务

## API使用说明

### 端点

- `GET /` - API根检查
- `GET /health` - 健康检查，返回OCRmyPDF和Tesseract版本信息
- `GET /supported-languages/` - 查询支持的语言
- `POST /ocr/` - 处理PDF文件

### 示例请求

使用cURL:

```bash
curl -X POST "https://your-space-name.hf.space/ocr/" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "pdf_file=@your_file.pdf" \
  -F "language=eng+chi_sim" \
  -F "force_ocr=false" \
  -F "deskew=true" \
  -F "optimize=1" \
  --output processed.pdf
```

使用Python:

```python
import requests

url = "https://your-space-name.hf.space/ocr/"

payload = {
    'language': 'eng+chi_sim',
    'force_ocr': 'false',
    'deskew': 'true',
    'optimize': '1'
}

files = {
    'pdf_file': open('your_file.pdf', 'rb')
}

response = requests.post(url, data=payload, files=files)

# 保存处理后的PDF
with open('processed.pdf', 'wb') as f:
    f.write(response.content)
```

## 参数说明

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| language | string | "eng+chi_sim" | OCR语言，可选: "eng"(英文), "chi_sim"(简体中文), "eng+chi_sim"(中英文) |
| force_ocr | boolean | false | 是否强制对所有页面进行OCR处理，即使已包含文本 |
| deskew | boolean | false | 是否在OCR前自动校正倾斜的页面 |
| optimize | integer | 0 | PDF优化级别: 0=不优化, 1=安全优化, 2=强力优化, 3=最大优化 |

## 资源限制

- 最大文件大小: 200MB
- 最大页数: 1000页
- 处理超时: 1800秒(30分钟)

## 性能注意事项

- 大型PDF文件处理可能需要较长时间
- 高优化级别(2-3)会显著增加处理时间和资源消耗
- 如遇到超时问题，请尝试减小文件大小或降低优化级别

## 技术实现

本服务基于:
- OCRmyPDF官方Docker镜像
- FastAPI框架
- Tesseract OCR引擎(支持英文和简体中文)
