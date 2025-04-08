import fastapi
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Response
from fastapi.responses import FileResponse
import tempfile
import os
import shutil
import logging
import uuid
import PyPDF2
from typing import Literal # 用于精确类型提示
import ocrmypdf  # 直接导入OCRmyPDF的Python API

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
        # 检查OCRmyPDF版本
        ocrmypdf_version = ocrmypdf.__version__
        
        # 检查Tesseract
        import subprocess
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
    language: ALLOWED_LANGUAGES = Form(DEFAULT_LANGUAGE_ARG, description=f"Language(s) for OCR. Choose from: {list(SUPPORTED_LANG_ARGS.keys())}. Default: '{DEFAULT_LANGUAGE_ARG}'."),
    pdf_file: UploadFile = File(..., description="The PDF file to be processed."),
    force_ocr: bool = Form(False, description="Force OCR even if text seems present?"),
    deskew: bool = Form(False, description="Deskew the image before OCR?"),
    optimize: int = Form(0, description="PDF optimization level (0=None, 1=Safe, 2=Strong, 3=Max) - 0 recommended for stability in Spaces")
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

        # 使用OCRmyPDF Python API处理PDF
        logger.info("Starting OCR processing using OCRmyPDF Python API")
        try:
            ocrmypdf.ocr(
                input_file=input_path,
                output_file=output_path,
                language=language,
                force_ocr=force_ocr,
                skip_text=(not force_ocr),  # 如果不强制OCR，则跳过已有文本
                deskew=deskew,
                optimize=optimize if optimize >= 0 and optimize <= 3 else 0,
                jobs=1,  # 在资源受限的环境中使用单线程
                progress_bar=False  # 禁用进度条（在Web服务中不需要）
            )
            logger.info("OCR processing completed successfully")
        except ocrmypdf.exceptions.PriorOcrFoundError as e:
            logger.warning(f"Prior OCR found: {str(e)}")
            # 这种情况下我们可以考虑复制原始文件作为输出
            shutil.copy(input_path, output_path)
            logger.info("Copied original file as it already contains OCR")
        except ocrmypdf.exceptions.MissingDependencyError as e:
            logger.error(f"Missing dependency: {str(e)}")
            raise HTTPException(status_code=500, detail=f"OCR processing failed due to missing dependency: {str(e)}")
        except ocrmypdf.exceptions.EncryptedPdfError as e:
            logger.error(f"Encrypted PDF: {str(e)}")
            raise HTTPException(status_code=400, detail="Cannot process encrypted PDF. Please remove the password protection first.")
        except ocrmypdf.exceptions.BadArgsError as e:
            logger.error(f"Bad arguments: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid processing parameters: {str(e)}")
        except Exception as e:
            logger.error(f"OCR processing failed: {str(e)}")
            raise HTTPException(status_code=500, detail="OCR processing failed. Please try again with different parameters.")

        # 检查输出文件是否存在
        if not os.path.exists(output_path):
            error_message = "OCR processing seemed successful but output file was not found."
            logger.error(error_message)
            raise HTTPException(status_code=500, detail=error_message)
        
        # OCR 成功，准备返回文件
        logger.info(f"OCR successful. Output file generated at '{output_path}'")
        # 生成友好的下载文件名
        download_filename = f"ocr_{pdf_file.filename}" if pdf_file.filename else "processed_document.pdf"

        # 返回处理后的文件
        return FileResponse(
            path=output_path,
            media_type='application/pdf',
            filename=download_filename
        )

    except HTTPException as http_exc:
        # 重新抛出已知的 HTTP 异常
        raise http_exc
    except Exception as e:
        # 捕获其他意外错误
        logger.error(f"An unexpected error occurred during OCR processing for file '{pdf_file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred. Please try again later.")
    finally:
        # 无论成功与否，都清理临时目录及其内容
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
    current_position = upload_file.file.tell()
    upload_file.file.seek(0, 2)  # 2 表示从文件末尾
    size = upload_file.file.tell()
    upload_file.file.seek(current_position)
    return size