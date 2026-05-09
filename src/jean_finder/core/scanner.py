from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass
class ScanCandidate:
    path: Path
    size: int
    mtime: int


def _is_office_lock_file(name: str) -> bool:
    # Word/Excel/PowerPoint가 문서 열어둔 동안 만드는 lock 파일 (~$xxxx.docx 등).
    # 정상적인 문서가 아니라 추출하면 항상 실패한다. 스캔 단계에서 컷.
    return name.startswith("~$")


def iter_candidates(roots: Iterable[Path], extensions: set[str]) -> Iterator[ScanCandidate]:
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if _is_office_lock_file(p.name):
                    continue
                if p.suffix.lower() not in extensions:
                    continue
                stat = p.stat()
                yield ScanCandidate(path=p, size=stat.st_size, mtime=int(stat.st_mtime))
            except (PermissionError, OSError):
                continue
