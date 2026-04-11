from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor, ExtractorError
from .docx import DocxExtractor
from .hwp import HwpExtractor
from .hwpx import HwpxExtractor
from .pdf import PdfExtractor
from .pptx import PptxExtractor
from .xlsx import XlsExtractor, XlsxExtractor


def build_default_registry(enable_ocr: bool = False) -> "Registry":
    reg = Registry()
    reg.register(PdfExtractor(enable_ocr=enable_ocr))
    reg.register(DocxExtractor())
    reg.register(XlsxExtractor())
    reg.register(XlsExtractor())
    reg.register(PptxExtractor())
    reg.register(HwpxExtractor())
    reg.register(HwpExtractor())
    return reg


class Registry:
    def __init__(self) -> None:
        self._by_ext: dict[str, BaseExtractor] = {}

    def register(self, extractor: BaseExtractor) -> None:
        for ext in extractor.extensions:
            self._by_ext[ext.lower()] = extractor

    def for_path(self, path: Path) -> BaseExtractor | None:
        return self._by_ext.get(path.suffix.lower())

    def supported_extensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_ext.keys()))


__all__ = [
    "Registry",
    "build_default_registry",
    "ExtractorError",
    "init_worker",
    "extract_in_worker",
]


# ---- ProcessPoolExecutor용 워커 API ----------------------------------------
# Why: 워커 프로세스마다 Registry를 한 번만 만들고 재사용하려고 글로벌에 둔다.
# 워커 프로세스는 짧지 않게 살아 있으므로 인스턴스 재사용 효과가 크다.

_WORKER_REGISTRY: Registry | None = None


def init_worker(enable_ocr: bool) -> None:
    global _WORKER_REGISTRY
    _WORKER_REGISTRY = build_default_registry(enable_ocr=enable_ocr)


def extract_in_worker(path_str: str) -> tuple[str, int, str | None]:
    """워커에서 호출되는 추출 함수.

    Returns: (text, page_count, error_or_none)
    """
    if _WORKER_REGISTRY is None:
        # 안전망: initializer 없이 호출된 경우.
        init_worker(False)
    assert _WORKER_REGISTRY is not None

    p = Path(path_str)
    extractor = _WORKER_REGISTRY.for_path(p)
    if extractor is None:
        return ("", 0, "no extractor")
    try:
        result = extractor.extract(p)
        return (result.text, result.page_count, None)
    except ExtractorError as e:
        return ("", 0, str(e))
    except Exception as e:  # noqa: BLE001
        return ("", 0, f"unexpected: {e}")
