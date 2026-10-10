import math
import re
from typing import BinaryIO, Callable, Literal

import pdfplumber
import pytesseract
from pdfplumber.utils.exceptions import PdfminerException
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pypdf import PageObject, PdfReader
from pypdf.errors import PdfReadError

from checker.extract import MAX_PREVIEW_BYTES, ParsedDocument, _append_text, _as_stream, image_info
from checker.schemas import ImageInfo, TextBlock

def _image_coverage(page: pdfplumber.page.Page) -> float:
    area = max(page.width * page.height, 1)
    total = sum(
        max(0, image["x1"] - image["x0"]) * max(0, image["bottom"] - image["top"])
        for image in page.images
    )
    return min(total / area, 1)


def _needs_ocr(page: pdfplumber.page.Page, text: str, mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "off":
        return False
    chars = sum(character.isalnum() for character in text)
    return chars < 80 and _image_coverage(page) >= 0.3


def _ocr_text(page: pdfplumber.page.Page, number: int) -> str:
    pixels = page.width * page.height
    dpi = min(200, math.floor(72 * math.sqrt(20_000_000 / max(pixels, 1))))
    if dpi < 100:
        raise ValueError(f"PDF 第 {number} 页尺寸过大，无法以足够分辨率进行 OCR")
    try:
        image = page.to_image(resolution=dpi).original.convert("RGB")
        return pytesseract.image_to_string(image, lang="chi_sim+eng", config="--psm 3")
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError) as exc:
        raise ValueError("OCR 不可用；请安装 Tesseract 的简体中文及英文语言包，或关闭 PDF OCR") from exc


def _page_images(page: PageObject, number: int, warnings: list[str]) -> list[ImageInfo]:
    images: list[ImageInfo] = []
    try:
        for item in page.images:
            if not item.is_displayed:
                continue
            raw = item.data
            if len(raw) > MAX_PREVIEW_BYTES:
                warnings.append(f"第 {number} 页存在较大图片，仅进行字节一致核查，不生成预览")
            images.append(image_info(raw, f"第 {number} 页 · {item.name}"))
    except (PdfReadError, OSError, ValueError) as exc:
        warnings.append(f"第 {number} 页图片解析失败，图片核查可能不完整：{type(exc).__name__}")
    return images


def parse_pdf(
    data: bytes | BinaryIO,
    name: str,
    document_id: str,
    ocr_mode: Literal["auto", "always", "off"],
    progress: Callable[[str, int, int], None] | None = None,
) -> ParsedDocument:
    try:
        stream = _as_stream(data)
        with pdfplumber.open(stream) as pdf:
            blocks: list[TextBlock] = []
            warnings: list[str] = []
            ocr_pages = 0
            page_count = len(pdf.pages)
            for index, page in enumerate(pdf.pages):
                number = index + 1
                native_text = page.extract_text() or ""
                text = native_text
                if _needs_ocr(page, native_text, ocr_mode):
                    ocr_pages += 1
                    text = _ocr_text(page, number)
                if not re.search(r"\w", text):
                    warnings.append(f"第 {number} 页没有可用于文本比对的文字")
                _append_text(blocks, text, f"PDF · 第 {number} 页")
                if progress:
                    progress("text", number, page_count)
        stream.seek(0)
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            raise ValueError("加密 PDF 请先解密后上传")
        images: list[ImageInfo] = []
        for index in range(page_count):
            images.extend(_page_images(reader.pages[index], index + 1, warnings))
            if progress:
                progress("images", index + 1, page_count)
        return ParsedDocument(
            id=document_id,
            name=name,
            blocks=blocks,
            images=images,
            format="pdf",
            pages=page_count,
            ocr_pages=ocr_pages,
            warnings=tuple(warnings[:30]),
        )
    except ValueError:
        raise
    except PDFPasswordIncorrect as exc:
        raise ValueError("加密 PDF 请先解密后上传") from exc
    except (PDFSyntaxError, PdfminerException, PdfReadError, OSError, TypeError, IndexError) as exc:
        raise ValueError("文件不是有效的 PDF 文档") from exc
