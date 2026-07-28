---
title: OCRmyPDF API
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# OCRmyPDF API

这是 `BlueSkyXN/OCRmyPDF-HFS` 的最小 Hugging Face Space wrapper。它不包含
FastAPI 产品源码、测试、`.env*`、`local/` 或运行数据。构建时，`Dockerfile` 从
`BUILD_SOURCE.json` 读取由导出器写入的完整 Git commit，并从公开 GitHub 源检出该
commit；无法检出或提交不匹配时构建失败。

运行时服务保持无状态：上传和 OCR 中间文件仅位于 `/app/temp`，请求结束后清理。
`/health` 只有在 OCRmyPDF、Tesseract、`eng`、`chi_sim` 和临时空间均可用时才返回
`200`。

该目录只能通过产品仓的 `cloud/hfs/export_space_bundle.sh` 导出。发布由 GitHub
Actions 的手动确认工作流执行，并在写入后读取 Space tree、revision 和 wrapper 文件字节进行验证。
