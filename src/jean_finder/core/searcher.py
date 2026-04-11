from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List

from .database import Database


@dataclass
class SearchHit:
    path: str
    filename: str
    folder: str
    ext: str
    mtime: int
    snippet: str

    @property
    def mtime_iso(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")


class Searcher:
    def __init__(self, db: Database, snippet_radius: int = 10):
        self.db = db
        self.snippet_radius = snippet_radius

    def search(self, query: str, limit: int = 200) -> List[SearchHit]:
        query = query.strip()
        if not query:
            return []

        # FTS5 MATCH 인자: 사용자 입력에서 위험한 토큰을 escape.
        # 사용자가 단순 키워드를 입력할 것이라고 가정하고 phrase로 감싼다.
        match_expr = self._to_match_expression(query)

        sql = """
            SELECT f.path, f.filename, f.folder, f.ext, f.mtime,
                   snippet(file_contents, 0, '<<', '>>', '...', 32) as snip
            FROM file_contents
            JOIN files f ON f.id = file_contents.rowid
            WHERE file_contents MATCH ?
            ORDER BY f.mtime DESC
            LIMIT ?
        """
        rows = self.db.conn.execute(sql, (match_expr, limit)).fetchall()

        hits: List[SearchHit] = []
        for path, filename, folder, ext, mtime, snip in rows:
            tight = self._tighten_snippet(snip, query)
            hits.append(
                SearchHit(
                    path=path,
                    filename=filename,
                    folder=folder,
                    ext=ext,
                    mtime=mtime,
                    snippet=tight,
                )
            )
        return hits

    @staticmethod
    def _to_match_expression(query: str) -> str:
        # FTS5 phrase 검색을 위한 escape: 큰따옴표는 두 번 반복.
        escaped = query.replace('"', '""')
        return f'"{escaped}"'

    def _tighten_snippet(self, fts_snippet: str, query: str) -> str:
        """FTS5 snippet은 단어 단위라 길이가 들쭉날쭉하다.
        사용자 요구사항(앞 10자 + 검색어 + 뒤 10자)을 맞추려고
        FTS5가 표시한 첫 매치 위치를 기준으로 글자 수를 다시 자른다.
        """
        if not fts_snippet:
            return ""

        clean = fts_snippet.replace("<<", "").replace(">>", "")
        radius = self.snippet_radius

        idx = clean.lower().find(query.lower())
        if idx < 0:
            # FTS가 매칭한 토큰이 정규화 차이로 substring 매칭에 실패한 경우
            return clean[: radius * 2 + len(query)]

        start = max(0, idx - radius)
        end = min(len(clean), idx + len(query) + radius)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(clean) else ""
        return f"{prefix}{clean[start:end]}{suffix}"
