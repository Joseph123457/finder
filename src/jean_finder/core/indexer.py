from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from jean_finder.extractors.registry import (
    Registry,
    build_default_registry,
    extract_in_worker,
    init_worker,
)

from .database import Database
from .scanner import ScanCandidate, iter_candidates


@dataclass
class IndexProgress:
    total_seen: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0
    current_path: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


ProgressCallback = Callable[[IndexProgress], None]


def _default_workers() -> int:
    cpu = os.cpu_count() or 4
    # I/O와 추출이 섞여 있으므로 코어 수에 살짝 못 미치게.
    return max(2, min(cpu - 1, 8))


class Indexer:
    """폴더를 스캔하고 추출 결과를 SQLite 인덱스에 기록한다.

    추출은 ProcessPoolExecutor로 병렬화하고 DB 쓰기는 메인 프로세스에서
    BulkWriter 한 트랜잭션에 묶어 처리한다. SQLite는 단일 writer라
    이 구조가 가장 안전하면서도 충분히 빠르다.
    """

    def __init__(
        self,
        db: Database,
        registry: Optional[Registry] = None,
        enable_ocr: bool = False,
        max_workers: Optional[int] = None,
        batch_commit: int = 100,
    ):
        self.db = db
        self.enable_ocr = enable_ocr
        # 메인 프로세스에서도 한 번 만들어 supported_extensions 등을 쓴다.
        self.registry = registry or build_default_registry(enable_ocr=enable_ocr)
        self.extensions = set(self.registry.supported_extensions())
        self.max_workers = max_workers or _default_workers()
        self.batch_commit = batch_commit

    def index_roots(
        self,
        roots: Iterable[Path],
        progress_cb: Optional[ProgressCallback] = None,
        force: bool = False,
    ) -> IndexProgress:
        progress = IndexProgress()
        roots_list = list(roots)

        # 1) 후보 수집 + mtime skip 판정 (싱글 스레드, 매우 빠름)
        to_extract: List[ScanCandidate] = []
        for cand in iter_candidates(roots_list, self.extensions):
            progress.total_seen += 1
            if not force:
                existing_mtime = self.db.get_file_mtime(str(cand.path))
                if existing_mtime is not None and existing_mtime >= cand.mtime:
                    progress.skipped += 1
                    progress.current_path = str(cand.path)
                    if progress_cb:
                        progress_cb(progress)
                    continue
            to_extract.append(cand)

        # 2) 병렬 추출 → 메인 프로세스에서 DB 쓰기
        if to_extract:
            self._run_parallel(to_extract, progress, progress_cb)

        # 3) 스캔 루트 타임스탬프 갱신 + 검색 최적화
        for root in roots_list:
            self.db.update_scan_root_timestamp(root)
        self.db.post_scan_optimize()

        return progress

    # ------------------------------------------------------------------

    def _run_parallel(
        self,
        candidates: List[ScanCandidate],
        progress: IndexProgress,
        progress_cb: Optional[ProgressCallback],
    ) -> None:
        # 파일 수가 적으면 풀 띄우는 비용(~1s, Windows)이 추출 시간보다 커서
        # 오히려 느려진다. 임계치는 벤치 결과(60파일=손해, 400파일=2.3x이득)를
        # 보고 보수적으로 30으로 잡았다.
        if len(candidates) <= 30 or self.max_workers <= 1:
            self._run_inline(candidates, progress, progress_cb)
            return

        cand_by_path = {str(c.path): c for c in candidates}
        path_strs = [str(c.path) for c in candidates]

        with self.db.bulk_writer(batch_size=self.batch_commit) as writer:
            with ProcessPoolExecutor(
                max_workers=self.max_workers,
                initializer=init_worker,
                initargs=(self.enable_ocr,),
            ) as pool:
                future_to_path = {
                    pool.submit(extract_in_worker, p): p for p in path_strs
                }
                for future in as_completed(future_to_path):
                    p = future_to_path[future]
                    cand = cand_by_path[p]
                    progress.current_path = p
                    try:
                        text, _page_count, err = future.result()
                    except Exception as e:  # noqa: BLE001
                        text, err = "", f"worker crash: {e}"

                    if err:
                        progress.failed += 1
                        progress.warnings.append(f"{p}: {err}")
                        self._write(writer, cand, content="", status=f"error:{err[:200]}")
                    else:
                        progress.indexed += 1
                        self._write(writer, cand, content=text, status="ok")

                    if progress_cb:
                        progress_cb(progress)

    def _run_inline(
        self,
        candidates: List[ScanCandidate],
        progress: IndexProgress,
        progress_cb: Optional[ProgressCallback],
    ) -> None:
        with self.db.bulk_writer(batch_size=self.batch_commit) as writer:
            for cand in candidates:
                progress.current_path = str(cand.path)
                extractor = self.registry.for_path(cand.path)
                if extractor is None:
                    progress.failed += 1
                    progress.warnings.append(f"{cand.path}: no extractor")
                    self._write(writer, cand, content="", status="error:no extractor")
                else:
                    try:
                        result = extractor.extract(cand.path)
                        progress.indexed += 1
                        self._write(writer, cand, content=result.text, status="ok")
                    except Exception as e:  # noqa: BLE001
                        progress.failed += 1
                        msg = str(e)
                        progress.warnings.append(f"{cand.path}: {msg}")
                        self._write(writer, cand, content="", status=f"error:{msg[:200]}")

                if progress_cb:
                    progress_cb(progress)

    @staticmethod
    def _write(writer, cand: ScanCandidate, *, content: str, status: str) -> None:
        writer.upsert(
            path=str(cand.path),
            filename=cand.path.name,
            folder=str(cand.path.parent),
            ext=cand.path.suffix.lower(),
            size=cand.size,
            mtime=cand.mtime,
            content=content,
            status=status,
        )
