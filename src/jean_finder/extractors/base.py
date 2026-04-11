from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractionResult:
    text: str
    page_count: int = 0
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)


class ExtractorError(Exception):
    pass


class BaseExtractor(ABC):
    name: str = "base"
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        ...

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions
