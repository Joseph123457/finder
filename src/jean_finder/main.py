from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jean_finder import __app_name__, __version__
from jean_finder.core.config import AppConfig
from jean_finder.core.database import Database
from jean_finder.core.indexer import Indexer, IndexProgress
from jean_finder.core.searcher import Searcher


def _print_progress(p: IndexProgress) -> None:
    sys.stdout.write(
        f"\r[{p.indexed + p.skipped + p.failed}/{p.total_seen}] "
        f"indexed={p.indexed} skip={p.skipped} fail={p.failed} :: {p.current_path}"[:160]
    )
    sys.stdout.flush()


def cmd_scan(args, cfg: AppConfig) -> int:
    cfg.ensure_dirs()
    db = Database(cfg.db_path)
    try:
        roots = [Path(r).resolve() for r in args.roots]
        for r in roots:
            db.add_scan_root(r)

        indexer = Indexer(db, enable_ocr=cfg.enable_ocr)
        progress = indexer.index_roots(roots, progress_cb=_print_progress, force=args.force)
        sys.stdout.write("\n")
        print(
            f"done: indexed={progress.indexed} skipped={progress.skipped} failed={progress.failed}"
        )
        if progress.warnings:
            print(f"warnings ({len(progress.warnings)}):")
            for w in progress.warnings[:10]:
                print(f"  - {w}")
            if len(progress.warnings) > 10:
                print(f"  ... and {len(progress.warnings) - 10} more")
        return 0
    finally:
        db.close()


def cmd_search(args, cfg: AppConfig) -> int:
    db = Database(cfg.db_path)
    try:
        searcher = Searcher(db, snippet_radius=cfg.snippet_radius)
        hits = searcher.search(args.query, limit=args.limit)
        if not hits:
            print("(no results)")
            return 0
        for hit in hits:
            print(f"{hit.mtime_iso}  {hit.filename}")
            print(f"    {hit.path}")
            print(f"    > {hit.snippet}")
        print(f"\n{len(hits)} hits")
        return 0
    finally:
        db.close()


def cmd_stats(args, cfg: AppConfig) -> int:
    db = Database(cfg.db_path)
    try:
        s = db.stats()
        print(f"db: {cfg.db_path}")
        print(f"files total={s['total']} ok={s['ok']}")
        print(f"scan roots: {db.list_scan_roots()}")
        return 0
    finally:
        db.close()


def cmd_gui(args, cfg: AppConfig) -> int:
    from jean_finder.gui.main_window import run_app

    return run_app(cfg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jean_finder", description=f"{__app_name__} v{__version__}")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="폴더를 스캔하여 인덱스에 추가")
    p_scan.add_argument("roots", nargs="+", help="스캔할 폴더 경로(들)")
    p_scan.add_argument("--force", action="store_true", help="mtime 무시하고 재인덱싱")
    p_scan.set_defaults(func=cmd_scan)

    p_search = sub.add_parser("search", help="인덱스에서 검색")
    p_search.add_argument("query", help="검색어")
    p_search.add_argument("--limit", type=int, default=50)
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser("stats", help="인덱스 통계 출력")
    p_stats.set_defaults(func=cmd_stats)

    p_gui = sub.add_parser("gui", help="GUI 실행")
    p_gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = AppConfig()

    # 인자 없이 실행되면(더블클릭 등) 기본으로 GUI를 띄운다.
    # console=False로 빌드된 exe에서 stdout 안내문은 보이지 않기 때문.
    if not getattr(args, "func", None):
        return cmd_gui(args, cfg)

    return args.func(args, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
