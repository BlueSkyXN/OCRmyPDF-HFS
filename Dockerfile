# Local development image. HFS deployments use cloud/hfs/Dockerfile, which checks out
# the immutable application source commit recorded in BUILD_SOURCE.json.
ARG PYTHON_BASE_IMAGE=python:3.11.9-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

ARG OCRMY_PDF_VERSION=16.0.4
ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# OCRmyPDF needs these system tools for PDF conversion, OCR, language data, and
# the existing optimize modes. Keep the dependency surface explicit rather than
# inheriting an opaque OCR application image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ghostscript \
        jbig2enc \
        pngquant \
        qpdf \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
        unpaper \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt \
    "ocrmypdf==${OCRMY_PDF_VERSION}"

COPY main.py entrypoint.sh ./
RUN install -d -m 1777 /app/temp \
    && chmod 755 /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
