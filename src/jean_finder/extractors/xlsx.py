from __future__ import annotations

from pathlib import Path

from .base import BaseExtractor, ExtractionResult, ExtractorError


class XlsxExtractor(BaseExtractor):
    name = "xlsx"
    extensions = (".xlsx", ".xlsm")

    def extract(self, path: Path) -> ExtractionResult:
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise ExtractorError(f"openpyxl not installed: {e}")

        try:
            wb = load_workbook(filename=str(path), read_only=True, data_only=True)
        except Exception as e:
            raise ExtractorError(f"XLSX open failed: {e}")

        parts: list[str] = []
        try:
            for sheet in wb.worksheets:
                parts.append(f"# {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None and str(c).strip()]
                    if cells:
                        parts.append("\t".join(cells))
        finally:
            wb.close()

        return ExtractionResult(text="\n".join(parts))


class XlsExtractor(BaseExtractor):
    name = "xls"
    extensions = (".xls",)

    def extract(self, path: Path) -> ExtractionResult:
        try:
            import xlrd
        except ImportError as e:
            raise ExtractorError(f"xlrd not installed: {e}")

        try:
            book = xlrd.open_workbook(str(path))
        except Exception as e:
            raise ExtractorError(f"XLS open failed: {e}")

        parts: list[str] = []
        for sheet in book.sheets():
            parts.append(f"# {sheet.name}")
            for row_idx in range(sheet.nrows):
                row = sheet.row_values(row_idx)
                cells = [str(c) for c in row if c not in (None, "") and str(c).strip()]
                if cells:
                    parts.append("\t".join(cells))

        return ExtractionResult(text="\n".join(parts))
