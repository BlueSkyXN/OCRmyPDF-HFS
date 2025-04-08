import fastapi
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Response
from fastapi.responses import FileResponse
import subprocess
import tempfile
import os
import shutil
import logging
import uuid
import PyPDF2
from typing import Literal # 用于精确类型提示

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 配置 ---
# 定义支持的 Tesseract 语言参数 (对应 Dockerfile 中安装的包)
SUPPORTED_LANG_ARGS = {
    "eng": "English only",
    "chi_sim": "Simplified Chinese only",
    "eng+chi_sim": "English and Simplified Chinese"
}
DEFAULT_LANGUAGE_ARG = "eng+chi_sim" # 默认处理中英文混合
ALLOWED_LANGUAGES = Literal["eng", "chi_sim", "eng+chi_sim"] # FastAPI 类型提示

# 资源限制配置
MAX_FILE_SIZE_MB = 200  # 最大文件大小，MB
MAX_PAGES = 1000  # 最大页数
TIMEOUT_SECONDS = 1800  # OCR 处理超时时间，秒
# ----------------

# 初始化 FastAPI 应用
app = FastAPI(
    title="OCRmyPDF API",
    description="API to add OCR text layer (English/Chinese) to PDF files using OCRmyPDF.",
    version="1.0.0"
)

@app.get("/", summary="API Root Check")
async def read_root():
    """Provides a simple check that the API is running."""
    return {"message": f"OCRmyPDF API is running. Use POST /ocr/ to process PDFs. Supported languages: {list(SUPPORTED_LANG_ARGS.keys())}"}

@app.get("/health", summary="Health Check")
async def health_check():
    """Provides a detailed health check of the API and its dependencies."""
    try:
        # 检查 OCRmyPDF 是否可用
        result = subprocess.run(['ocrmypdf', '--version'], capture_output=True, text=True, timeout=5)
        ocrmypdf_version = result.stdout.strip() if result.returncode == 0 else "Not available"
        
        # 检查 Tesseract 是否可用
        tesseract_result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=5)
        tesseract_version = tesseract_result.stdout.split('\n')[0] if tesseract_result.returncode == 0 else "Not available"
        
        # 返回健康状态
        return {
            "status": "healthy",
            "ocrmypdf": ocrmypdf_version,
            "tesseract": tesseract_version,
            "supported_languages": list(SUPPORTED_LANG_ARGS.keys())
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/supported-languages/", summary="List Supported Languages")
async def get_supported_languages():
    """Returns a dictionary of supported language arguments and descriptions."""
    return SUPPORTED_LANG_ARGS

@app.post("/ocr/",
          summary="Perform OCR on PDF",
          response_class=FileResponse, # 默认成功时返回文件
          responses={
              200: {
                  "content": {"application/pdf": {}},
                  "description": "Successfully OCR'd PDF file.",
              },
              400: {"description": "Bad Request (e.g., invalid language, wrong file type, no file uploaded)"},
              422: {"description": "Validation Error (e.g., language parameter missing)"},
              500: {"description": "Internal Server Error (OCR processing failed or unexpected error)"},
              504: {"description": "Gateway Timeout (OCR processing took too long)"}
          })
async def run_ocr_on_pdf(
    # 使用 Literal 类型强制 language 参数必须是允许的值之一
    language: ALLOWED_LANGUAGES = Form(DEFAULT_LANGUAGE_ARG, description=f"Language(s) for OCR. Choose from: {list(SUPPORTED_LANG_ARGS.keys())}. Default: '{DEFAULT_LANGUAGE_ARG}'."),
    # pdf_file 参数是必需的
    pdf_file: UploadFile = File(..., description="The PDF file to be processed."),
    # 可选：添加其他 OCRmyPDF 参数作为 Form 输入
    force_ocr: bool = Form(False, description="Force OCR even if text seems present?"),
    deskew: bool = Form(False, description="Deskew the image before OCR?"),
    optimize: int = Form(0, description="PDF optimization level (0=None, 1=Safe(Default in OCRmyPDF), 2=Strong, 3=Max) - 0 recommended for stability in Spaces")
):
    """
    Accepts a PDF file, performs OCR using the specified language(s),
    and returns the processed PDF file.
    """
    logger.info(f"Received request for language: {language}, force_ocr: {force_ocr}, deskew: {deskew}, optimize: {optimize}")

    # 基本文件验证
    if not pdf_file.filename.lower().endswith(".pdf"):
        logger.warning("Invalid file type uploaded.")
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
    
    # 检查文件大小
    file_size_mb = await get_upload_file_size(pdf_file) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        logger.warning(f"File too large: {file_size_mb:.2f}MB (max: {MAX_FILE_SIZE_MB}MB)")
        raise HTTPException(
            status_code=400, 
            detail=f"File too large. Maximum allowed size is {MAX_FILE_SIZE_MB}MB. Your file is {file_size_mb:.2f}MB."
        )

    # 创建唯一的临时工作目录
    temp_dir = tempfile.mkdtemp()
    # 在临时目录中定义输入和输出文件的路径
    # 使用 UUID 确保文件名唯一，即使原始文件名包含特殊字符
    input_filename = f"input_{uuid.uuid4()}.pdf"
    output_filename = f"output_{uuid.uuid4()}.pdf"
    input_path = os.path.join(temp_dir, input_filename)
    output_path = os.path.join(temp_dir, output_filename)

    logger.info(f"Processing in temporary directory: {temp_dir}")

    try:
        # 将上传的文件保存到临时输入路径
        logger.info(f"Saving uploaded file '{pdf_file.filename}' to '{input_path}'")
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(pdf_file.file, buffer)
        logger.info("File saved successfully.")
        
        # 检查PDF页数
        try:
            with open(input_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                page_count = len(reader.pages)
                logger.info(f"PDF has {page_count} pages")
                
                if page_count > MAX_PAGES:
                    logger.warning(f"PDF has too many pages: {page_count} (max: {MAX_PAGES})")
                    raise HTTPException(
                        status_code=400,
                        detail=f"PDF has {page_count} pages. Maximum allowed is {MAX_PAGES} pages."
                    )
        except PyPDF2.errors.PdfReadError as e:
            logger.error(f"Error reading PDF: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF file: {str(e)}")
        except Exception as e:
            logger.error(f"Error checking PDF pages: {str(e)}")
            # 继续处理，不中断流程

        # 构建 ocrmypdf 命令列表
        cmd = [
            'ocrmypdf',
            '-l', language, # 使用用户选择的语言参数
            '--jobs', '1', # 在资源受限的 Spaces 环境中，限制为单核处理可能更稳定
        ]
        # 根据用户选项添加参数
        if force_ocr:
            cmd.append('--force-ocr')
        else:
            # 默认跳过已有文本的页面，通常更安全快速
            cmd.append('--skip-text')
        if deskew:
            cmd.append('--deskew')
        if optimize >= 0 and optimize <= 3:
             # 警告：优化可能非常耗时耗内存，尤其 optimize 2 或 3
            cmd.extend(['--optimize', str(optimize)])
        
        # 添加输入和输出文件路径
        cmd.extend([input_path, output_path])

        command_str = ' '.join(cmd)
        logger.info(f"Executing command: {command_str}")

        # 执行命令，设置合理的超时
        result = subprocess.run(
            cmd,
            capture_output=True, # 捕获 stdout 和 stderr
            text=True,           # 以文本模式处理输出
            check=False,         # 不在返回码非零时自动抛出异常，手动检查
            timeout=TIMEOUT_SECONDS
        )

        # 检查命令执行结果
        if result.returncode != 0:
            # 如果 OCRmyPDF 失败
            error_message = f"OCRmyPDF failed with exit code {result.returncode}.\nStderr: {result.stderr[:1000]}\nStdout: {result.stdout[:1000]}" # 限制错误信息长度
            logger.error(error_message)
            raise HTTPException(status_code=500, detail=f"OCR processing failed. Please check server logs for details.") # 不要向客户端暴露过多内部错误
        elif not os.path.exists(output_path):
             # 如果命令成功但未找到输出文件（理论上不应发生，但作为保险）
            error_message = "OCR command seemed successful but output file was not found."
            logger.error(error_message)
            raise HTTPException(status_code=500, detail=error_message)
        else:
            # OCR 成功
            logger.info(f"OCR successful. Output file generated at '{output_path}'")
            # 准备返回文件响应
            # 生成一个对用户友好的下载文件名
            download_filename = f"ocr_{pdf_file.filename}" if pdf_file.filename else "processed_document.pdf"

            # 使用 FileResponse 高效地返回文件
            return FileResponse(
                path=output_path,
                media_type='application/pdf',
                filename=download_filename
            )

    except subprocess.TimeoutExpired:
        logger.error(f"OCR processing timed out after {TIMEOUT_SECONDS} seconds for file '{pdf_file.filename}'.")
        raise HTTPException(status_code=504, detail=f"OCR processing took too long and timed out after {TIMEOUT_SECONDS} seconds. Try with a smaller file or disable heavy options.")
    except HTTPException as http_exc:
        # 重新抛出已知的 HTTP 异常
        raise http_exc
    except Exception as e:
        # 捕获其他意外错误
        logger.error(f"An unexpected error occurred during OCR processing for file '{pdf_file.filename}': {e}", exc_info=True) # exc_info=True 记录堆栈跟踪
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred. Please contact support or check server logs.")
    finally:
        # *** 无论成功与否，都清理临时目录及其内容 ***
        if os.path.exists(temp_dir):
            logger.info(f"Cleaning up temporary directory: {temp_dir}")
            try:
                shutil.rmtree(temp_dir)
                logger.info("Temporary directory cleaned up successfully.")
            except Exception as cleanup_error:
                 logger.error(f"Error cleaning up temporary directory {temp_dir}: {cleanup_error}", exc_info=True)
        # 确保关闭上传的文件句柄
        await pdf_file.close()

async def get_upload_file_size(upload_file: UploadFile) -> int:
    """获取上传文件的大小（以字节为单位）"""
    # 记录当前位置
    current_position = upload_file.file.tell()
    # 移动到文件末尾
    upload_file.file.seek(0, 2)  # 2 表示从文件末尾
    # 获取文件大小
    size = upload_file.file.tell()
    # 恢复到原始位置
    upload_file.file.seek(current_position)
    return size