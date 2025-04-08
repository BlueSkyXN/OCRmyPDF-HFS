---
# Hugging Face Spaces 所需的配置信息
title: OCRmyPDF API 接口 # 显示在 Space 页面的标题 (可自定义)
emoji: 📄 # Space 图标的 Emoji (可选)
colorFrom: blue # 主题颜色起始 (可选)
colorTo: green # 主题颜色结束 (可选)
sdk: docker # 指定这是一个基于 Docker 的 Space (非常重要)
app_port: 8000 # 你的 FastAPI 应用在容器内部监听的端口 (必须与 Dockerfile CMD 中指定的端口一致)
pinned: false # 是否在你的个人资料页置顶这个 Space (可选)
---

# OCRmyPDF API on Hugging Face Spaces

这个 Space 提供了一个 REST API 接口，可以使用 OCRmyPDF 为 PDF 文件添加 OCR 文本层。此实例已配置为处理包含**英文**、**简体中文**和**数字**的文档。

## 如何使用

向 `/ocr/` 端点发送 POST 请求，请求体中包含 PDF 文件和所需的参数。

**API 端点:** `/ocr/`

**请求方法:** `POST`

**表单数据参数 (Form Data):**

* `pdf_file`: (必需) 需要处理的 PDF 文件。
* `language`: (必需) 用于 OCR 的语言。可选值：
    * `eng` (仅英文)
    * `chi_sim` (仅简体中文)
    * `eng+chi_sim` (英文和简体中文 - **默认值**)
* `force_ocr`: (可选) `true` 或 `false`。即使文件看起来已有文本，是否强制进行 OCR？ (默认: `false`)
* `deskew`: (可选) `true` 或 `false`。在 OCR 前是否进行图像歪斜校正？ (默认: `false`)
* `optimize`: (可选) `0`, `1`, `2`, 或 `3`。PDF 优化级别 (0=无, 1=安全, 2=较强, 3=最强)。 (默认: `0` 以保证稳定性)。

**成功响应:**

* 状态码: `200 OK`
* Content-Type: `application/pdf`
* 响应体: 处理完成的、带有 OCR 文本层的 PDF 文件。

**错误响应:**

* 状态码: `400`, `422`, `500`, `504`
* Content-Type: `application/json`
* 响应体: 包含错误详情的 JSON 对象。

**其他端点:**

* `/`: GET - 检查 API 是否运行的基本端点。
* `/supported-languages/`: GET - 返回支持的语言参数列表。

## 使用示例 (curl)

```bash
curl -X POST \
  -F "pdf_file=@/path/to/your/local/input.pdf" \
  -F "language=eng+chi_sim" \
  -F "deskew=true"
