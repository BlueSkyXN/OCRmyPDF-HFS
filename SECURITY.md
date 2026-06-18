# Security Policy

## 安全改进 (Security Improvements)

本项目已经过全面的安全审查和改进。以下是已实施的安全措施：

### 1. 依赖包安全 (Dependency Security)

#### 已修复的漏洞
- **FastAPI**: 更新至 ≥0.109.1，修复了 Content-Type Header ReDoS 漏洞
- **python-multipart**: 更新至 ≥0.0.22，修复了以下漏洞：
  - 任意文件写入漏洞
  - DoS 攻击漏洞（通过畸形的 multipart/form-data boundary）
  - Content-Type Header ReDoS 漏洞

#### 依赖管理建议
- 定期检查依赖包更新: `pip list --outdated`
- 使用 `pip-audit` 或 GitHub Dependabot 监控安全漏洞
- 定期更新 `requirements.txt` 中的依赖版本

### 2. 资源管理 (Resource Management)

#### 临时文件清理
- **问题**: 之前在错误情况下可能导致临时目录泄漏
- **解决方案**: 实现了 `cleanup_registered` 标志，确保在以下情况下临时文件被正确清理：
  - PDF 页数超过限制
  - PDF 文件损坏或无效
  - OCR 处理失败
  - 任何其他异常情况

#### 文件权限
- **改进**: 临时目录权限从 `777` (rwxrwxrwx) 改为 `750` (rwxr-x---)
- **效果**: 遵循最小权限原则，减少潜在的安全风险

### 3. DoS 防护 (DoS Protection)

#### 请求体大小限制
- **实施**: 添加了中间件在请求开始时检查 Content-Length 头
- **限制**: 最大请求体大小为 `MAX_FILE_SIZE_MB * 1.5` (考虑 multipart 开销)
- **效果**: 防止攻击者通过上传超大文件消耗服务器资源

#### 其他资源限制
- 最大文件大小: 200MB
- 最大 PDF 页数: 1000 页
- 处理超时: 1800 秒 (30 分钟)
- OCR 并行任务: 2 个线程

### 4. 输入验证 (Input Validation)

#### 已实施的验证
- **文件类型**: 仅接受 `.pdf` 文件
- **文件大小**: 在上传前和上传后双重检查
- **页数**: 检查 PDF 页数防止过大文件
- **语言参数**: 使用 `Literal` 类型限制可选值，防止命令注入
- **优化级别**: 验证范围 0-3

#### 安全的命令执行
- 使用 `subprocess.run()` 的列表参数而非字符串，防止 shell 注入
- 不使用 `shell=True` 选项
- 所有参数都经过验证和类型检查

### 5. 错误处理 (Error Handling)

#### 安全的错误信息
- 不向客户端暴露详细的系统错误信息
- 使用通用错误消息，避免信息泄露
- 详细错误信息仅记录在服务器日志中

#### 特殊情况处理
- **加密 PDF**: 返回明确的错误信息，不尝试处理
- **已有 OCR 的 PDF**: 安全地返回原始文档
- **超时**: 正确终止进程，清理资源

## 部署建议 (Deployment Recommendations)

### 1. 容器安全
- 使用非 root 用户运行容器（考虑添加 `USER` 指令到 Dockerfile）
- 定期更新基础镜像 `jbarlow83/ocrmypdf-alpine`
- 使用容器扫描工具（如 Trivy）检查漏洞

### 2. 网络安全
- 在生产环境中使用反向代理（如 Nginx）
- 启用 HTTPS/TLS
- 配置适当的 CORS 策略
- 实施速率限制

### 3. 监控和日志
- 监控磁盘空间使用情况
- 设置临时文件清理的定时任务
- 监控异常的请求模式
- 定期审查日志中的错误和异常

### 4. 资源限制
- 在容器编排平台（如 Kubernetes）中设置 CPU 和内存限制
- 配置最大并发请求数
- 实施请求队列机制处理高负载

## 报告安全问题 (Reporting Security Issues)

如果您发现安全漏洞，请**不要**公开提交 issue。请通过以下方式私密报告：

1. 创建一个 [Security Advisory](https://github.com/BlueSkyXN/OCRmyPDF-HFS/security/advisories)
2. 或通过 GitHub 私信联系项目维护者

我们会尽快响应并处理安全问题。

## 版本历史 (Version History)

### v1.1.0 (2026-01-31)
- 修复临时目录资源泄漏问题
- 更新依赖包修复已知漏洞
- 添加请求体大小限制中间件
- 改进文件权限设置
- 删除 Dockerfile 中的重复指令

### v1.0.0 (初始版本)
- 基础 OCR API 功能
