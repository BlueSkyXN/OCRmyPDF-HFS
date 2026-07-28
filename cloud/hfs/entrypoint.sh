#!/bin/sh
set -eu

TEMP_DIR="/app/temp"
PORT="${PORT:-8000}"

printf '%s\n' 'Starting OCRmyPDF API service'

for command in ocrmypdf tesseract gs qpdf; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'Required command is unavailable: %s\n' "$command" >&2
        exit 1
    fi
done

ocrmypdf --version >/dev/null
tesseract --version >/dev/null
for language in eng chi_sim; do
    if ! tesseract --list-langs 2>/dev/null | grep -Fx "$language" >/dev/null; then
        printf 'Required Tesseract language is unavailable: %s\n' "$language" >&2
        exit 1
    fi
done

if [ ! -d "$TEMP_DIR" ] || [ ! -w "$TEMP_DIR" ]; then
    printf 'OCR temporary directory is unavailable: %s\n' "$TEMP_DIR" >&2
    exit 1
fi

printf 'Listening on port %s\n' "$PORT"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
