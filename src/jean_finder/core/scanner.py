from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


@dataclass
class ScanCandidate:
    path: Path
    size: int
    mtime: int


def iter_candidates(roots: Iterable[Path], extensions: set[str]) -> Iterator[ScanCandidate]:
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            try:
                if not p.is_file():
                    continue
                if p.suffix.lower() not in extensions:
                    continue
                stat = p.stat()
                yield ScanCandidate(path=p, size=stat.st_size, mtime=int(stat.st_mtime))
            except (PermissionError, OSError):
                continue
