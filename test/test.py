#!/usr/bin/env python3
"""Run a real, local OCRmyPDF API smoke contract against a supplied PDF corpus.

The script never selects a hosted endpoint or fixture by default. Provide an explicit
local/candidate URL and harmless fixture paths, for example:

  PYTHONDONTWRITEBYTECODE=1 python3 test/test.py \\
    --api-url http://127.0.0.1:8000 \\
    --fixture english=fixtures/english.pdf \\
    --fixture chinese=fixtures/chinese.pdf \\
    --fixture mixed=fixtures/mixed.pdf \\
    --fixture existing-text=fixtures/existing-text.pdf \\
    --fixture deskew=fixtures/deskew.pdf --deskew \\
    --reject-fixture fixtures/corrupt.pdf

It verifies each successful output is a readable PDF, retains its page count, and has
a text layer. Record output size and duration in the release evidence; set optional
thresholds only after an approved baseline exists.
"""

from __future__ import annotations

import argparse
import http.client
import mimetypes
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit



def parse_fixture(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("fixture must use NAME=PATH")
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"fixture does not exist: {path}")
    return name, path


def parse_expected_text(value: str) -> tuple[str, str]:
    name, separator, expected = value.partition("=")
    if not separator or not name or not expected:
        raise argparse.ArgumentTypeError("expected text must use NAME=TEXT")
    return name, expected


def connection_for(url: str) -> tuple[http.client.HTTPConnection, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("api-url must be an absolute http(s) URL")
    target = parsed.path or "/ocr/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    return connection_class(parsed.hostname, parsed.port, timeout=1_900), target


def multipart_parts(
    boundary: str,
    fixture: Path,
    *,
    language: str,
    force_ocr: bool,
    deskew: bool,
    optimize: int,
) -> tuple[bytes, bytes]:
    fields = {
        "language": language,
        "force_ocr": str(force_ocr).lower(),
        "deskew": str(deskew).lower(),
        "optimize": str(optimize),
    }
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    content_type = mimetypes.guess_type(fixture.name)[0] or "application/pdf"
    chunks.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="pdf_file"; filename="{fixture.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
    )
    return b"".join(chunks), f"\r\n--{boundary}--\r\n".encode()


def stream_file(path: Path, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            yield chunk


def request_ocr(args: argparse.Namespace, fixture: Path) -> tuple[int, bytes, float]:
    boundary = f"----ocrmypdf-smoke-{secrets.token_hex(12)}"
    prefix, suffix = multipart_parts(
        boundary,
        fixture,
        language=args.language,
        force_ocr=args.force_ocr,
        deskew=args.deskew,
        optimize=args.optimize,
    )
    content_length = len(prefix) + fixture.stat().st_size + len(suffix)
    connection, target = connection_for(args.api_url)
    started = time.monotonic()
    try:
        connection.putrequest("POST", target)
        connection.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        connection.putheader("Content-Length", str(content_length))
        connection.putheader("Accept", "application/pdf, application/json")
        hf_token = os.getenv("HF_TOKEN", "")
        if hf_token:
            connection.putheader("X-HF-Authorization", f"Bearer {hf_token}")
        connection.endheaders()
        connection.send(prefix)
        for chunk in stream_file(fixture):
            connection.send(chunk)
        connection.send(suffix)
        response = connection.getresponse()
        body = response.read()
        return response.status, body, time.monotonic() - started
    finally:
        connection.close()


def verify_success(name: str, fixture: Path, body: bytes, elapsed: float, args: argparse.Namespace) -> None:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        raise RuntimeError("PyPDF2 is required to validate PDF structure; install project dependencies first") from exc

    if args.max_seconds is not None and elapsed > args.max_seconds:
        raise RuntimeError(f"{name}: processing exceeded {args.max_seconds}s ({elapsed:.2f}s)")
    if args.max_output_bytes is not None and len(body) > args.max_output_bytes:
        raise RuntimeError(f"{name}: output exceeded {args.max_output_bytes} bytes")
    if not body.startswith(b"%PDF-"):
        raise RuntimeError(f"{name}: response is not a PDF")
    if args.require_pdfa and b"pdfaid:" not in body and b"GTS_PDFA" not in body:
        raise RuntimeError(f"{name}: output does not expose PDF/A identification metadata")

    with tempfile.TemporaryDirectory(prefix="ocrmypdf-smoke-") as temp_dir:
        output_path = Path(temp_dir) / "output.pdf"
        output_path.write_bytes(body)
        input_reader = PdfReader(str(fixture))
        output_reader = PdfReader(str(output_path))
        if len(input_reader.pages) != len(output_reader.pages):
            raise RuntimeError(f"{name}: page count changed unexpectedly")
        output_text = "".join(page.extract_text() or "" for page in output_reader.pages).strip()
        if not output_text:
            raise RuntimeError(f"{name}: output has no extractable text layer")
        expected = dict(args.expect_text).get(name)
        if expected and "".join(expected.split()).casefold() not in "".join(output_text.split()).casefold():
            raise RuntimeError(f"{name}: expected OCR text was not found in the output text layer")

    print(
        f"PASS {name}: pages={len(input_reader.pages)}, output_bytes={len(body)}, "
        f"elapsed_seconds={elapsed:.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", required=True, help="explicit local or candidate /ocr/ endpoint")
    parser.add_argument("--fixture", action="append", type=parse_fixture, required=True, metavar="NAME=PATH")
    parser.add_argument("--expect-text", action="append", type=parse_expected_text, default=[], metavar="NAME=TEXT")
    parser.add_argument("--reject-fixture", action="append", type=Path, default=[], metavar="PATH")
    parser.add_argument("--language", default="eng+chi_sim", choices=["eng", "chi_sim", "eng+chi_sim"])
    parser.add_argument("--force-ocr", action="store_true")
    parser.add_argument("--deskew", action="store_true")
    parser.add_argument("--optimize", type=int, choices=range(4), default=0)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--max-output-bytes", type=int)
    parser.add_argument("--require-pdfa", action="store_true")
    args = parser.parse_args()

    for name, fixture in args.fixture:
        status, body, elapsed = request_ocr(args, fixture)
        if status != 200:
            raise RuntimeError(f"{name}: expected HTTP 200, got {status}: {body[:500]!r}")
        verify_success(name, fixture, body, elapsed, args)

    for fixture in args.reject_fixture:
        if not fixture.is_file():
            raise RuntimeError(f"reject fixture does not exist: {fixture}")
        status, body, elapsed = request_ocr(args, fixture)
        if status < 400:
            raise RuntimeError(f"{fixture.name}: expected rejection, got HTTP {status}: {body[:500]!r}")
        print(f"PASS reject {fixture.name}: status={status}, elapsed_seconds={elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
