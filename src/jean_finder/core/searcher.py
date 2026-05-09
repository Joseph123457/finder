from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List

from .database import Database


# 스니펫 표시용: 테이블 셀이 한 줄이라 \n/\t가 들어가면 그 뒤 글자가 잘려보인다.
# 제어문자(0x00~0x1F 중 일부)도 PDF 추출에서 종종 섞이므로 함께 정리.
_DISPLAY_WS = re.compile(r"[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f]+")


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

        # 두 단계로 나눠 snippet() 비용을 줄인다.
        # 1) MATCH+JOIN+ORDER BY+LIMIT 으로 먼저 N건만 추림 (snippet 계산 X)
        # 2) 추려진 rowid에 대해서만 snippet() 호출
        # 하나의 쿼리로 합치면 sqlite 옵티마이저가 snippet()을 매치 전체 행에
        # 호출해버려 한글 trigram 매치(수천 건)에서 1초 가까이 걸린다.
        # 측정: 460ms -> 145ms (3x).
        #
        # ORDER BY 의 sort_key:
        # 파일시스템 mtime이 미래(예: 2107년)로 박힌 파일이 4건 있는데,
        # 단순 mtime DESC면 그 4건이 매번 최상단을 차지해 검색 결과가 망가진다.
        # 한 달 이상 미래는 명백히 잘못된 데이터로 보고 0으로 클램프해 맨 뒤로 보낸다.
        sql = """
            WITH matched AS (
                SELECT file_contents.rowid AS rid,
                       f.path, f.filename, f.folder, f.ext, f.mtime,
                       CASE
                           WHEN f.mtime > strftime('%s','now') + 86400*30 THEN 0
                           ELSE f.mtime
                       END AS sort_key
                FROM file_contents
                JOIN files f ON f.id = file_contents.rowid
                WHERE file_contents MATCH ?
                ORDER BY sort_key DESC
                LIMIT ?
            )
            SELECT m.path, m.filename, m.folder, m.ext, m.mtime,
                   (SELECT snippet(file_contents, 0, '<<', '>>', '...', 64)
                    FROM file_contents
                    WHERE rowid = m.rid AND file_contents MATCH ?) AS snip
            FROM matched m
        """
        rows = self.db.conn.execute(sql, (match_expr, limit, match_expr)).fetchall()

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
        """FTS5 snippet 결과를 '앞 N자 + 매치 + 뒤 N자' 로 정리한다.

        FTS5가 매치 부분을 <<...>> 로 직접 표시해주므로 그 위치를 신뢰한다.
        과거 구현은 <<>> 를 떼어낸 후 사용자 입력으로 substring 검색을 다시 했는데,
        trigram 토크나이저 정규화/대소문자/유니코드 차이 때문에 매치 위치를 못 찾고
        결과가 '...' 만 보이는 일이 잦았다.
        """
        if not fts_snippet:
            return ""

        radius = self.snippet_radius
        open_pos = fts_snippet.find("<<")
        close_pos = fts_snippet.find(">>", open_pos + 2) if open_pos >= 0 else -1

        if open_pos < 0 or close_pos < 0:
            # 매치 마커가 없는 비정상 응답: 그대로 반환(안전망).
            return fts_snippet

        before = fts_snippet[:open_pos].replace("<<", "").replace(">>", "")
        matched = fts_snippet[open_pos + 2:close_pos]
        after = fts_snippet[close_pos + 2:].replace("<<", "").replace(">>", "")

        # FTS5가 본문 잘림을 표시한 '...' 마커 인지/제거.
        starts_truncated = before.startswith("...")
        ends_truncated = after.endswith("...")
        if starts_truncated:
            before = before[3:]
        if ends_truncated:
            after = after[:-3]

        if len(before) > radius:
            before = before[-radius:]
            starts_truncated = True
        if len(after) > radius:
            after = after[:radius]
            ends_truncated = True

        pre = "..." if starts_truncated else ""
        suf = "..." if ends_truncated else ""
        result = f"{pre}{before}{matched}{after}{suf}"
        # 줄바꿈/제어문자는 한 줄 셀에서 그 뒤가 잘려 보이므로 공백으로.
        return _DISPLAY_WS.sub(" ", result)
