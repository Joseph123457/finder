from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "JeAnFinder"


@dataclass
class AppConfig:
    data_dir: Path = field(default_factory=default_data_dir)
    enable_ocr: bool = False
    snippet_radius: int = 10  # 검색어 앞/뒤 글자 수

    @property
    def db_path(self) -> Path:
        return self.data_dir / "index.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
