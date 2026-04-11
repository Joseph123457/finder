from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    filename    TEXT NOT NULL,
    folder      TEXT NOT NULL,
    ext         TEXT NOT NULL,
    size        INTEGER NOT NULL,
    mtime       INTEGER NOT NULL,
    indexed_at  INTEGER NOT NULL,
    hash        TEXT,
    status      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime DESC);
CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder);

-- trigram 토크나이저: 공백 없는 한국어 문서에서도 substring 검색이 동작.
-- 일반(contentful) FTS5 테이블이라 snippet()이 실제 텍스트를 반환한다.
CREATE VIRTUAL TABLE IF NOT EXISTS file_contents USING fts5(
    content,
    tokenize = 'trigram'
);

CREATE TABLE IF NOT EXISTS scan_roots (
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,
    added_at    INTEGER NOT NULL,
    last_scan   INTEGER
);
"""


@dataclass
class FileRecord:
    id: int
    path: str
    filename: str
    folder: str
    ext: str
    size: int
    mtime: int
    indexed_at: int
    status: str


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---- scan roots --------------------------------------------------------

    def add_scan_root(self, path: Path) -> None:
        with self.transaction() as c:
            c.execute(
                "INSERT OR IGNORE INTO scan_roots(path, added_at) VALUES (?, ?)",
                (str(path), int(time.time())),
            )

    def list_scan_roots(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT path FROM scan_roots ORDER BY added_at")]

    def update_scan_root_timestamp(self, path: Path) -> None:
        with self.transaction() as c:
            c.execute(
                "UPDATE scan_roots SET last_scan=? WHERE path=?",
                (int(time.time()), str(path)),
            )

    # ---- file upsert -------------------------------------------------------

    def get_file_mtime(self, path: str) -> Optional[int]:
        row = self._conn.execute("SELECT mtime FROM files WHERE path=?", (path,)).fetchone()
        return row[0] if row else None

    def upsert_file(
        self,
        *,
        path: str,
        filename: str,
        folder: str,
        ext: str,
        size: int,
        mtime: int,
        content: str,
        status: str,
    ) -> int:
        with self.transaction() as c:
            return self._upsert_file_no_commit(
                c,
                path=path,
                filename=filename,
                folder=folder,
                ext=ext,
                size=size,
                mtime=mtime,
                content=content,
                status=status,
            )

    def _upsert_file_no_commit(
        self,
        c: sqlite3.Connection,
        *,
        path: str,
        filename: str,
        folder: str,
        ext: str,
        size: int,
        mtime: int,
        content: str,
        status: str,
    ) -> int:
        now = int(time.time())
        cur = c.execute("SELECT id FROM files WHERE path=?", (path,))
        row = cur.fetchone()
        if row:
            file_id = row[0]
            c.execute(
                """UPDATE files
                   SET filename=?, folder=?, ext=?, size=?, mtime=?, indexed_at=?, status=?
                   WHERE id=?""",
                (filename, folder, ext, size, mtime, now, status, file_id),
            )
            c.execute("DELETE FROM file_contents WHERE rowid=?", (file_id,))
        else:
            cur = c.execute(
                """INSERT INTO files(path, filename, folder, ext, size, mtime, indexed_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (path, filename, folder, ext, size, mtime, now, status),
            )
            file_id = cur.lastrowid
        if content:
            c.execute(
                "INSERT INTO file_contents(rowid, content) VALUES (?, ?)",
                (file_id, content),
            )
        return file_id

    @contextmanager
    def bulk_writer(self, batch_size: int = 200) -> Iterator["BulkWriter"]:
        """대량 인덱싱용. 여러 upsert를 한 트랜잭션으로 묶어 쓰기 비용을 줄인다."""
        writer = BulkWriter(self, batch_size)
        try:
            yield writer
            writer.flush()
        except Exception:
            try:
                self._conn.rollback()
            except Exception:
                pass
            raise

    def delete_missing(self, existing_paths: set[str]) -> int:
        rows = self._conn.execute("SELECT id, path FROM files").fetchall()
        deleted = 0
        with self.transaction() as c:
            for file_id, path in rows:
                if path not in existing_paths:
                    c.execute("DELETE FROM files WHERE id=?", (file_id,))
                    c.execute("DELETE FROM file_contents WHERE rowid=?", (file_id,))
                    deleted += 1
        return deleted

    def stats(self) -> dict[str, int]:
        total = self._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        ok = self._conn.execute("SELECT COUNT(*) FROM files WHERE status='ok'").fetchone()[0]
        return {"total": total, "ok": ok}

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn


class BulkWriter:
    """배치 단위로 commit하는 헬퍼.

    Why: 파일 1만개를 1건씩 commit하면 fsync 비용이 너무 크다.
    한 트랜잭션 안에 batch_size개를 모아 commit하면 인덱싱이 수배 빨라진다.
    """

    def __init__(self, db: "Database", batch_size: int):
        self.db = db
        self.batch_size = max(1, batch_size)
        self._pending = 0
        self._tx_open = False

    def _ensure_tx(self) -> None:
        if not self._tx_open:
            self.db.conn.execute("BEGIN")
            self._tx_open = True

    def upsert(self, **kwargs) -> int:
        self._ensure_tx()
        file_id = self.db._upsert_file_no_commit(self.db.conn, **kwargs)
        self._pending += 1
        if self._pending >= self.batch_size:
            self.flush()
        return file_id

    def flush(self) -> None:
        if self._tx_open:
            self.db.conn.commit()
            self._tx_open = False
            self._pending = 0
