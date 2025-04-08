import fastapi
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Response, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import subprocess
import tempfile
import os
import shutil
import logging
import uuid
import PyPDF2
from typing import Literal, Optional, List

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 配置 ---
# 定义支持的 Tesseract 语言参数
SUPPORTED_LANG_ARGS = {
    "eng": "English only",
    "chi_sim": "Simplified Chinese only",
    "eng+chi_sim": "English and Simplified Chinese"
}
DEFAULT_LANGUAGE_ARG = "eng+chi_sim"  # 默认处理中英文混合
ALLOWED_LANGUAGES = Literal["eng", "chi_sim", "eng+chi_sim"]  # FastAPI 类型提示

# 资源限制配置
MAX_FILE_SIZE_MB = 200  # 最大文件大小，MB
MAX_PAGES = 1000  # 最大页数
TIMEOUT_SECONDS = 1800  # OCR 处理超时时间，秒
TEMP_DIR = "/app/temp"  # 临时文件目录
# ----------------

# 初始化 FastAPI 应用
app = FastAPI(
    title="OCRmyPDF API",
    description="API to add OCR text layer (English/Chinese) to PDF files using OCRmyPDF.",
    version="1.0.0"
)

# 确保临时目录存在
os.makedirs(TEMP_DIR, exist_ok=True)

@app.get("/", summary="API Root Check")
async def read_root():
    """提供简单的API可用性检查"""
    return {
        "status": "running",
        "service": "OCRmyPDF API",
        "endpoints": {
            "POST /ocr/": "OCR处理PDF文件",
            "GET /health": "健康检查",
            "GET /supported-languages/": "查询支持的语言"
        },
        "supported_languages": list(SUPPORTED_LANG_ARGS.keys())
    }

@app.get("/health", summary="Health Check")
async def health_check():
    """提供详细的API和依赖健康状态检查"""
    try:
        # 检查 OCRmyPDF 是否可用
        result = subprocess.run(['ocrmypdf', '--version'], capture_output=True, text=True, timeout=5)
        ocrmypdf_version = result.stdout.strip() if result.returncode == 0 else "Not available"
        
        # 检查 Tesseract 是否可用
        tesseract_result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=5)
        tesseract_version = tesseract_result.stdout.split('\n')[0] if tesseract_result.returncode == 0 else "Not available"
        
        # 检查支持的语言
        langs_result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True, timeout=5)
        available_langs = langs_result.stdout.strip().split('\n')[1:] if langs_result.returncode == 0 else []
        
        # 检查磁盘空间
        disk_info = os.statvfs(TEMP_DIR)
        free_space_mb = (disk_info.f_bavail * disk_info.f_frsize) / (1024 * 1024)
        
        # 返回健康状态
        return {
            "status": "healthy",
            "ocrmypdf": ocrmypdf_version,
            "tesseract": tesseract_version,
            "available_languages": available_langs,
            "disk_space": {
                "free_mb": round(free_space_mb, 2),
                "temp_dir": TEMP_DIR
            },
            "resource_limits": {
                "max_file_size_mb": MAX_FILE_SIZE_MB,
                "max_pages": MAX_PAGES,
                "timeout_seconds": TIMEOUT_SECONDS
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/supported-languages/", summary="List Supported Languages")
async def get_supported_languages():
    """返回支持的语言参数及其描述的字典"""
    return SUPPORTED_LANG_ARGS

@app.post("/ocr/",
          summary="Perform OCR on PDF",
          response_class=FileResponse,
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
    language: ALLOWED_LANGUAGES = Form(DEFAULT_LANGUAGE_ARG, description=f"Language(s) for OCR. Choose from: {list(SUPPORTED_LANG_ARGS.keys())}. Default: '{DEFAULT_LANGUAGE_ARG}'."),
    pdf_file: UploadFile = File(..., description="The PDF file to be processed."),
    force_ocr: bool = Form(False, description="Force OCR even if text seems present?"),
    deskew: bool = Form(False, description="Deskew the image before OCR?"),
    optimize: int = Form(0, description="PDF optimization level (0=None, 1=Safe, 2=Strong, 3=Max)"),
    background_tasks: BackgroundTasks = None
):
    """
    接收PDF文件，使用指定的语言进行OCR处理，并返回处理后的PDF文件。
    """
    logger.info(f"Received request: filename={pdf_file.filename}, language={language}, force_ocr={force_ocr}, deskew={deskew}, optimize={optimize}")

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
    session_id = str(uuid.uuid4())
    temp_dir = os.path.join(TEMP_DIR, session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    # 在临时目录中定义输入和输出文件的路径
    input_filename = f"input_{session_id}.pdf"
    output_filename = f"output_{session_id}.pdf"
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

        # 构建 ocrmypdf 命令列表 - 利用镜像中预装的ocrmypdf
        cmd = [
            'ocrmypdf',
            '-l', language,  # 语言参数
            '--jobs', '2',   # 并行处理线程，根据资源调整
        ]
        
        # 根据用户选项添加参数
        if force_ocr:
            cmd.append('--force-ocr')
        else:
            # 默认跳过已有文本的页面
            cmd.append('--skip-text')
            
        if deskew:
            cmd.append('--deskew')
            
        if optimize >= 0 and optimize <= 3:
            cmd.extend(['--optimize', str(optimize)])
        
        # 添加输入和输出文件路径
        cmd.extend([input_path, output_path])

        command_str = ' '.join(cmd)
        logger.info(f"Executing command: {command_str}")

        # 执行命令，设置超时
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS
        )

        # 检查命令执行结果
        if result.returncode != 0:
            # 处理已有OCR文本的情况
            if "PriorOcrFoundError" in result.stderr:
                logger.info("Document already contains OCR text. Returning original document.")
                shutil.copy(input_path, output_path)
            # 处理加密PDF的情况
            elif "EncryptedPdfError" in result.stderr:
                logger.error("PDF is encrypted and cannot be processed")
                raise HTTPException(status_code=400, detail="Cannot process encrypted PDF. Please remove password protection first.")
            # 其他错误
            else:
                error_message = f"OCRmyPDF failed with exit code {result.returncode}."
                logger.error(f"{error_message}\nStderr: {result.stderr[:1000]}\nStdout: {result.stdout[:1000]}")
                raise HTTPException(status_code=500, detail="OCR processing failed. Please check your PDF file or try different parameters.")
        
        # 验证输出文件存在
        if not os.path.exists(output_path):
            error_message = "OCR command seemed successful but output file was not found."
            logger.error(error_message)
            raise HTTPException(status_code=500, detail=error_message)
        
        # OCR 成功
        logger.info(f"OCR successful. Output file generated at '{output_path}'")
        
        # 生成友好的下载文件名
        download_filename = f"ocr_{pdf_file.filename}" if pdf_file.filename else "processed_document.pdf"

        # 注册清理临时目录的后台任务
        if background_tasks:
            background_tasks.add_task(cleanup_temp_dir, temp_dir)

        # 返回处理后的文件
        return FileResponse(
            path=output_path,
            media_type='application/pdf',
            filename=download_filename,
            background=background_tasks
        )

    except subprocess.TimeoutExpired:
        logger.error(f"OCR processing timed out after {TIMEOUT_SECONDS} seconds for file '{pdf_file.filename}'.")
        raise HTTPException(status_code=504, detail=f"OCR processing took too long and timed out after {TIMEOUT_SECONDS} seconds. Try with a smaller file or disable heavy options.")
    except HTTPException as http_exc:
        # 重新抛出已知的 HTTP 异常
        raise http_exc
    except Exception as e:
        # 捕获其他意外错误
        logger.error(f"An unexpected error occurred during OCR processing for file '{pdf_file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred. Please try again later.")
    finally:
        # 确保关闭上传的文件句柄
        await pdf_file.close()
        
        # 清理临时目录会由后台任务处理，这里不需要额外操作
        # 如果没有注册后台任务，则在这里清理
        if not background_tasks and os.path.exists(temp_dir):
            cleanup_temp_dir(temp_dir)

def cleanup_temp_dir(temp_dir: str):
    """清理临时目录及其内容的辅助函数"""
    try:
        if os.path.exists(temp_dir):
            logger.info(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)
            logger.info("Temporary directory cleaned up successfully.")
    except Exception as cleanup_error:
        logger.error(f"Error cleaning up temporary directory {temp_dir}: {cleanup_error}", exc_info=True)

async def get_upload_file_size(upload_file: UploadFile) -> int:
    """获取上传文件的大小（以字节为单位）"""
    current_position = upload_file.file.tell()
    upload_file.file.seek(0, 2)  # 2 表示从文件末尾
    size = upload_file.file.tell()
    upload_file.file.seek(current_position)
    return size