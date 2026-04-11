from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor, ExtractionResult, ExtractorError


class PdfExtractor(BaseExtractor):
    name = "pdf"
    extensions = (".pdf",)

    # OCR 폴백 임계치: 페이지당 평균 글자 수가 이 값 미만이면 스캔본으로 간주
    OCR_TRIGGER_CHARS_PER_PAGE = 20

    def __init__(self, enable_ocr: bool = False):
        self.enable_ocr = enable_ocr

    def extract(self, path: Path) -> ExtractionResult:
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise ExtractorError(f"PyMuPDF not installed: {e}")

        text_parts: list[str] = []
        warnings: list[str] = []

        try:
            doc = fitz.open(str(path))
        except Exception as e:
            raise ExtractorError(f"PDF open failed: {e}")

        try:
            page_count = doc.page_count
            for page in doc:
                text_parts.append(page.get_text("text") or "")
        finally:
            doc.close()

        text = "\n".join(text_parts)
        avg_chars = (len(text) / page_count) if page_count else 0

        ocr_used = False
        if self.enable_ocr and avg_chars < self.OCR_TRIGGER_CHARS_PER_PAGE:
            try:
                from jean_finder.ocr.tesseract import ocr_pdf

                ocr_text = ocr_pdf(path)
                if ocr_text.strip():
                    text = ocr_text
                    ocr_used = True
                else:
                    warnings.append("OCR returned empty text")
            except Exception as e:
                warnings.append(f"OCR failed: {e}")

        return ExtractionResult(
            text=text,
            page_count=page_count,
            ocr_used=ocr_used,
            warnings=warnings,
        )
