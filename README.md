---
title: OCRmyPDF API
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---

# OCRmyPDF API 服务

本项目提供基于 FastAPI 和 OCRmyPDF 的 REST API，为 PDF 添加可搜索的文本层。服务支持英语和简体中文 OCR。它是无状态服务：上传文件和 OCR 中间文件仅在 `/app/temp` 中短暂存在，请求结束后清理；服务重启不会恢复在途请求或上传文件。

## API

- `GET /`：服务和端点摘要。
- `GET /health`：OCRmyPDF、Tesseract、`eng`、`chi_sim` 和临时空间均正常时返回 `200`；任何关键依赖不可用时返回 `503`。
- `GET /supported-languages/`：支持的语言组合。
- `POST /ocr/`：处理 PDF，响应为 PDF 文件。

```bash
curl -X POST "https://your-space-name.hf.space/ocr/" \
  -H "accept: application/pdf" \
  -F "pdf_file=@your_file.pdf" \
  -F "language=eng+chi_sim" \
  -F "force_ocr=false" \
  -F "deskew=true" \
  -F "optimize=1" \
  --output processed.pdf
```

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `language` | string | `eng+chi_sim` | `eng`、`chi_sim` 或 `eng+chi_sim`。 |
| `force_ocr` | boolean | `false` | 已有文本时仍强制 OCR。 |
| `deskew` | boolean | `false` | OCR 前校正倾斜页面。 |
| `optimize` | integer | `0` | PDF 优化等级，范围为 `0` 到 `3`。 |

现有运行限制保持不变：最大文件大小为 200 MB、最大页数为 1000 页、单次 OCR 超时为 1800 秒。带 `Content-Length` 的超大 multipart 请求会在解析前被拒绝；实际 PDF 大小仍由接口按 200 MB 上限校验。

## Docker 依赖与本地运行

根 `Dockerfile` 适用于本地直接构建，显式安装 Ghostscript、qpdf、Tesseract（含 `eng` 与 `chi_sim`）、unpaper、pngquant 和固定的 OCRmyPDF PyPI 版本；它不再继承 `jbarlow83/ocrmypdf-alpine:latest` 业务镜像。基础镜像使用 Debian trixie，以获得不受 OCRmyPDF 禁用的 Ghostscript 10.05 系列；仓库仍不宣称支持未安装的可选 `jbig2enc` 有损单色优化器。

```bash
docker build -t ocrmypdf-hfs .
docker run --rm -p 8000:8000 ocrmypdf-hfs
```

`PYTHON_BASE_IMAGE`、`OCRMY_PDF_VERSION` 和 `PIKEPDF_VERSION` 是 Dockerfile 中可审查的构建输入。手工发布 workflow 会解析基础镜像 tag 的 registry digest，将 digest、固定 OCRmyPDF `16.0.4` 与兼容的 pikepdf `8.15.1` 一并写入 `BUILD_SOURCE.json`；导出器拒绝浮动的 wrapper 输入。pikepdf 不能只依赖 OCRmyPDF 的开放下界：pikepdf 10 已移除 OCRmyPDF 16.0.4 在输出校验中使用的 `Pdf.check()`。之后必须用下述 OCR 回归确认该组合符合旧服务基线；不得把未验证的基础镜像、语言包或 OCRmyPDF/pikepdf 版本直接切到生产 Space。

## HFS v2 source wrapper

Hugging Face Space 不再以仓库根目录作为产品副本。`cloud/hfs/` 是薄 wrapper，其导出物仅包含：

```text
.dockerignore
BUILD_SOURCE.json
Dockerfile
README.md
entrypoint.sh
hfs-dev.toml
```

导出器 `cloud/hfs/export_space_bundle.sh` 只接受已检出的完整 40 位 Git commit，并拒绝脏工作树、暂存修改或未跟踪输入。它生成 `BUILD_SOURCE.json`，Space Docker build 从公开 GitHub 仓检出该 commit 并再次断言 `HEAD` 相同。检出、依赖安装、语言包或启动预检失败时均失败退出，不会回退到旧业务镜像、其他 Git ref 或运行时下载路径。

`hfs-dev.toml` 是 HFS v2 的最小关系登记：该项目是 `sovereign`、`source`、`commit` 车道。它只登记键名；`.env` 和 `local/` 均不会进入 Git、Docker context 或 Space bundle。`.env.example` 仅为本地部署控制面的空模板，`HF_TOKEN` 不会作为 Space Secret 或 Variable 写入。

## 受控部署

`.github/workflows/sync-to-hf-space.yml` 仅支持 `workflow_dispatch`。操作者必须提供完整 source commit，并明确选择 `deploy` 才会产生远端写入。工作流通过 Hugging Face HTTP API 创建受控 commit，不使用含凭据的 Git URL，也不 force-push。

首次将旧的全仓 Space 迁为 wrapper 时，发布脚本会先读取远端 tree。发现 wrapper allowlist 之外的文件时拒绝写入；旧 tree 清理必须走独立 owner-approved 程序，不能与部署绑定。写后脚本会重新读取 Space tree、revision 和每个 wrapper 文件的精确字节；revision 或内容不一致均失败。candidate 必须预先创建为 private。该工作流不管理 Space Settings、bucket、挂载、重启或清理旧资源。

本项目当前没有 Space Secret/Variable，但仍保留本地事实源的对账入口：

```bash
python3 scripts/hf_space_sync.py diff --manifest hfs-dev.candidate.toml --env-file .env
python3 scripts/hf_space_sync.py push --manifest hfs-dev.candidate.toml --env-file .env
python3 scripts/hf_space_sync.py diff --manifest hfs-dev.candidate.toml --env-file .env
```

最后一次 `diff` 是 readback；不得在清理授权前使用 `--prune --yes`。

## OCR smoke contract

Docker build、Space build 和网络部署本身不能证明 OCR 输出等价。发布前应使用无敏感、合法分发的固定 corpus，至少覆盖英文、简体中文、混排、已有文本、倾斜、损坏 PDF 和加密 PDF。默认请求与强制 OCR 的输出合约不同，必须分开执行。

默认路径会让服务调用 `--skip-text --output-type pdf`。已有文本样本应返回普通 PDF，保留页数和原有可提取文本；这条 smoke 不要求 PDF/A：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 test/test.py \
  --api-url http://127.0.0.1:8000/ocr/ \
  --fixture existing-text=test/fixtures/existing-text.pdf \
  --expect-text 'existing-text=HFS EXISTING TEXT 20260728'
```

PDF/A 路径必须显式请求 `force_ocr=true`，并由 smoke 同时启用 `--force-ocr --require-pdfa`。固定 corpus 覆盖英文、简体中文、混排和倾斜页面：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 test/test.py \
  --api-url http://127.0.0.1:8000/ocr/ \
  --fixture english=test/fixtures/english.pdf \
  --fixture chinese=test/fixtures/chinese.pdf \
  --fixture mixed=test/fixtures/mixed.pdf \
  --fixture deskew=test/fixtures/deskew.pdf \
  --force-ocr \
  --deskew \
  --require-pdfa \
  --reject-fixture test/fixtures/corrupt.pdf
```

两条 smoke 都验证 HTTP 成功结果是可读 PDF、页数未意外变化且有可提取文本层；`existing-text` 还核对原有文本仍可提取。`--require-pdfa` 只验证强制 OCR 路径的 PDF/A 标识。拒绝样本必须返回 4xx/5xx 而不产生可下载的半成品；加密 PDF 需使用另行审查的合法 fixture 验证。只有 owner 批准具体数值后才附加 `--max-output-bytes` 和 `--max-seconds`。各 `optimize` 等级应分别运行，并记录耗时、输出大小、文本质量和 PDF/A/兼容性结果，与迁移前基线及批准的容差比较。

## 发布前 owner 门禁

以下事项需要 release owner 明确签认，不能由静态检查替代：

1. 用旧 Space build digest、真实 `/health` 和 corpus 重新建立只读基线；旧 `latest` 业务镜像没有可验证基线时不得切换或清理。
2. 批准 Python/Debian digest、OCRmyPDF 版本、系统工具组合，以及中文、PDF/A、优化与性能容差。
3. 创建并审查包含本次 wrapper 的干净 deployment commit 或 tag；不得从脏工作树发布。
4. 手动确认 Space tree prune、部署窗口和发布后真实 OCR smoke。服务无登录、SQL、缓存、持久化挂载或备份/恢复契约，这些项目均为不适用，而非已验证的部署步骤。
