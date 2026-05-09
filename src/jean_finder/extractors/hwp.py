from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .base import BaseExtractor, ExtractionResult, ExtractorError

# 구형 HWP(.hwp) 텍스트 추출기.
# Why: HWP 5.x는 OLE 컨테이너 안에 BodyText/SectionN 스트림을 두며, 압축 옵션이 켜진
# 경우 zlib 압축이 들어간다. PrvText 스트림은 미리보기 텍스트를 담지만 일부만 포함된다.
# 본 구현은 BodyText/Section* 레코드에서 텍스트 레코드(tag id 67)를 파싱한다.
# 한계는 PLAN.md 리스크 항목 참고: 표/그림이 많거나 비표준 문서는 누락 가능.


HWPTAG_BEGIN = 0x10
HWPTAG_PARA_TEXT = 67  # HWPTAG_BEGIN + 51 (PARA_TEXT)


class HwpExtractor(BaseExtractor):
    name = "hwp"
    extensions = (".hwp",)

    def extract(self, path: Path) -> ExtractionResult:
        try:
            import olefile
        except ImportError as e:
            raise ExtractorError(f"olefile not installed: {e}")

        if not olefile.isOleFile(str(path)):
            # .hwp 확장자지만 실제로는 HWPX(ZIP) 인 경우가 종종 있다 -> 위임.
            with open(path, "rb") as f:
                magic = f.read(4)
            if magic.startswith(b"PK\x03\x04"):
                from .hwpx import HwpxExtractor
                return HwpxExtractor().extract(path)
            raise ExtractorError("Not an OLE compound file (.hwp)")

        ole = olefile.OleFileIO(str(path))
        warnings: list[str] = []
        parts: list[str] = []

        try:
            compressed = self._is_compressed(ole, warnings)
            section_streams = sorted(
                "/".join(entry) for entry in ole.listdir()
                if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section")
            )

            if not section_streams:
                # PrvText는 본문이 아니라 미리보기지만 fallback으로 사용
                if ole.exists("PrvText"):
                    raw = ole.openstream("PrvText").read()
                    try:
                        parts.append(raw.decode("utf-16-le", errors="ignore"))
                        warnings.append("used PrvText fallback (preview only)")
                    except Exception as e:
                        warnings.append(f"PrvText decode failed: {e}")
                else:
                    warnings.append("no BodyText/Section* and no PrvText")

            for stream_name in section_streams:
                try:
                    raw = ole.openstream(stream_name).read()
                    if compressed:
                        try:
                            raw = zlib.decompress(raw, -15)
                        except zlib.error as e:
                            warnings.append(f"{stream_name} decompress failed: {e}")
                            continue
                    parts.append(self._parse_section(raw, warnings))
                except Exception as e:
                    warnings.append(f"{stream_name} parse failed: {e}")
        finally:
            ole.close()

        return ExtractionResult(text="\n".join(p for p in parts if p), warnings=warnings)

    @staticmethod
    def _is_compressed(ole, warnings: list[str]) -> bool:
        if not ole.exists("FileHeader"):
            warnings.append("FileHeader missing; assuming uncompressed")
            return False
        header = ole.openstream("FileHeader").read()
        # signature(32) + version(4) + properties(4)
        if len(header) < 40:
            warnings.append("FileHeader too short")
            return False
        properties = struct.unpack("<I", header[36:40])[0]
        return bool(properties & 0x1)

    @staticmethod
    def _parse_section(data: bytes, warnings: list[str]) -> str:
        # Records: 32-bit header. tag(10b) | level(10b) | size(12b).
        # If size==0xFFF, real size is the following 32-bit little-endian value.
        out: list[str] = []
        i = 0
        n = len(data)
        while i + 4 <= n:
            header = struct.unpack("<I", data[i:i + 4])[0]
            i += 4
            tag = header & 0x3FF
            size = (header >> 20) & 0xFFF
            if size == 0xFFF:
                if i + 4 > n:
                    break
                size = struct.unpack("<I", data[i:i + 4])[0]
                i += 4
            if i + size > n:
                break
            payload = data[i:i + size]
            i += size

            if tag == HWPTAG_PARA_TEXT:
                # UTF-16LE characters; control codes occupy 8 wide-chars (16 bytes).
                # Characters in 0x0001..0x001F (except a few) are control markers.
                try:
                    out.append(_decode_para_text(payload))
                except Exception as e:
                    warnings.append(f"para_text decode failed: {e}")
        return "\n".join(s for s in out if s)


def _decode_para_text(payload: bytes) -> str:
    chars: list[str] = []
    i = 0
    n = len(payload)
    while i + 2 <= n:
        code = payload[i] | (payload[i + 1] << 8)
        i += 2
        if 1 <= code <= 31:
            # Inline control characters: 0x00..0x1F.
            # Some are 1 wchar; control records 4,5,6,7,8,9,10,13,17,18,19,20,21,22,23 are 8 wchar (16 bytes).
            wide_controls = {4, 5, 6, 7, 8, 9, 10, 13, 17, 18, 19, 20, 21, 22, 23}
            if code in wide_controls:
                i += 14  # already read 2; total 16
            elif code == 11:
                # tab/newline marker; render as newline
                chars.append("\n")
            else:
                pass
        else:
            chars.append(chr(code))
    return "".join(chars)
