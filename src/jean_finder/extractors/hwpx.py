from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .base import BaseExtractor, ExtractionResult, ExtractorError


class HwpxExtractor(BaseExtractor):
    name = "hwpx"
    extensions = (".hwpx",)

    def extract(self, path: Path) -> ExtractionResult:
        try:
            zf = zipfile.ZipFile(str(path))
        except zipfile.BadZipFile as e:
            raise ExtractorError(f"HWPX is not a valid zip: {e}")

        parts: list[str] = []
        warnings: list[str] = []

        try:
            section_names = sorted(
                n for n in zf.namelist()
                if n.startswith("Contents/section") and n.endswith(".xml")
            )
            if not section_names:
                warnings.append("no Contents/section*.xml found")

            for name in section_names:
                try:
                    data = zf.read(name)
                    parts.append(self._extract_text_from_xml(data))
                except Exception as e:
                    warnings.append(f"section {name} failed: {e}")
        finally:
            zf.close()

        return ExtractionResult(text="\n".join(p for p in parts if p), warnings=warnings)

    @staticmethod
    def _extract_text_from_xml(xml_bytes: bytes) -> str:
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return ""

        # HWPX uses namespaced tags like {http://www.hancom.co.kr/hwpml/2011/paragraph}t
        # Extract text from any element whose local name is "t".
        chunks: list[str] = []
        for elem in root.iter():
            tag = elem.tag
            local = tag.split("}", 1)[-1] if "}" in tag else tag
            if local == "t" and elem.text:
                chunks.append(elem.text)
        return "".join(chunks)
