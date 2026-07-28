#!/usr/bin/env python3
"""Generate the reviewed OCR smoke corpus committed under test/fixtures/."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
WIDTH, HEIGHT = 1654, 2339


def font(size: int, *, chinese: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/3419f2a427639ad8c8e139149a287865a90fa17e.asset/AssetData/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        if chinese
        else [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise SystemExit("required reviewed corpus font is not installed")


def image_pdf(name: str, lines: list[tuple[str, bool]], *, angle: float = 0) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    y = 260
    for text, chinese in lines:
        draw.text((180, y), text, fill="black", font=font(72, chinese=chinese))
        y += 150
    if angle:
        image = image.rotate(angle, expand=False, fillcolor="white")
    image.save(FIXTURES / name, "PDF", resolution=200.0)


def text_pdf() -> None:
    output = FIXTURES / "existing-text.pdf"
    pdf = canvas.Canvas(str(output), pagesize=(595, 842), pageCompression=0)
    pdf.setTitle("HFS OCR existing text fixture")
    pdf.setFont("Helvetica", 24)
    pdf.drawString(72, 760, "HFS EXISTING TEXT 20260728")
    pdf.save()


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    image_pdf(
        "english.pdf",
        [("HFS OCR ENGLISH 20260728", False), ("Verified searchable document", False)],
    )
    image_pdf(
        "chinese.pdf",
        [("HFS 中文 OCR 测试 20260728", True), ("可搜索文档验证", True)],
    )
    image_pdf(
        "mixed.pdf",
        [("HFS MIXED OCR 20260728", False), ("中英文混合识别测试", True)],
    )
    image_pdf(
        "deskew.pdf",
        [("HFS DESKEW OCR 20260728", False)],
        angle=3.0,
    )
    text_pdf()
    (FIXTURES / "corrupt.pdf").write_bytes(b"%PDF-1.7\ninvalid-fixed-corpus\n")


if __name__ == "__main__":
    main()
