"""Tesseract OCR 래퍼.

Why: 스캔본 PDF에서 텍스트 레이어가 없는 경우 이미지를 OCR해야 검색 가능.
외부 바이너리 의존(Tesseract + kor.traineddata)이므로 설치/경로 문제를
명확히 리포팅한다. 엔진 자체는 지연 임포트(lazy import)되어 OCR 미사용
환경에서는 파이썬 의존성 외 아무 비용도 없다.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


class OcrUnavailable(RuntimeError):
    pass


def _resolve_tesseract_cmd() -> str:
    """환경 변수 / 번들 경로 / PATH 순으로 tesseract 실행파일을 찾는다.

    PyInstaller 번들에서는 `resources/tesseract/tesseract.exe`를 기대하며,
    환경 변수 `JF_TESSERACT_CMD`로 사용자 지정도 허용한다.
    """
    env = os.environ.get("JF_TESSERACT_CMD")
    if env and Path(env).exists():
        return env

    # PyInstaller 런타임 디렉토리 (sys._MEIPASS) 내부
    try:
        import sys

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "resources" / "tesseract" / "tesseract.exe"
            if candidate.exists():
                return str(candidate)
    except Exception:
        pass

    found = shutil.which("tesseract")
    if found:
        return found

    raise OcrUnavailable(
        "Tesseract 실행파일을 찾을 수 없습니다. PATH에 등록하거나 "
        "JF_TESSERACT_CMD 환경변수에 경로를 지정하세요."
    )


def _resolve_tessdata_dir() -> Optional[str]:
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).exists():
        return env

    try:
        import sys

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "resources" / "tesseract" / "tessdata"
            if candidate.exists():
                return str(candidate)
    except Exception:
        pass
    return None


def configure_pytesseract() -> None:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()


def ocr_pdf(path: Path, lang: str = "kor+eng", dpi: int = 200) -> str:
    """PDF 전체를 이미지로 래스터화 후 OCR한다.

    10,000개 파일 규모에선 대부분의 시간이 여기서 소비될 수 있음에 주의.
    PyMuPDF로 직접 픽스맵을 뽑으면 pdf2image(Poppler) 의존을 회피할 수 있다.
    """
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    configure_pytesseract()
    tessdata = _resolve_tessdata_dir()
    config = f'--tessdata-dir "{tessdata}"' if tessdata else ""

    texts: list[str] = []
    doc = fitz.open(str(path))
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mode = "RGB" if pix.n < 4 else "RGBA"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            page_text = pytesseract.image_to_string(img, lang=lang, config=config)
            texts.append(page_text)
    finally:
        doc.close()
    return "\n".join(texts)


def probe() -> dict:
    """설치 상태를 리포팅한다. 설정 다이얼로그/CLI에서 사용."""
    info: dict = {"available": False, "cmd": None, "tessdata": None, "error": None}
    try:
        cmd = _resolve_tesseract_cmd()
        info["cmd"] = cmd
        info["tessdata"] = _resolve_tessdata_dir()
        info["available"] = True
    except OcrUnavailable as e:
        info["error"] = str(e)
    return info
