"""에펨코리아(FM코리아) 정적 HTML 크롤러 (httpx + BeautifulSoup).

robots.txt(fmkorea.com)는 일반 크롤러(User-agent: *)에게 `/`, `/best`,
`/best2`, `/humor` 목록 페이지만 허용하고 나머지는 전부 비허용이다. 특히
개별 게시물 상세 페이지는 숫자 경로(`/<doc_srl>`)로 노출되는데, 이는 위
허용 prefix에 속하지 않아 **robots.txt상 비허용**이다. 즉 이 크롤러는
목록 페이지에서 보이는 정보(제목/글쓴이/시각/조회수/추천수)까지만 수집할
수 있고, 게시물 본문은 수집할 수 없다.

이 제약은 코드에서도 이중으로 강제한다: 허용된 게시판 키 외의 값은
생성 시점에 ValueError로 막고, 실제 요청은 PoliteHTTPClient의
RobotsChecker가 다시 한번 검사한다.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common.http_client import PoliteHTTPClient, RobotsDisallowedError
from common.logging_config import get_logger
from common.models import CommunityPost

logger = get_logger(__name__)

BASE_URL = "https://www.fmkorea.com"
ALLOWED_BOARDS = {"best", "best2", "humor"}

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_MMDD_RE = re.compile(r"^\d{2}\.\d{2}$")
_YYMMDD_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")


def _parse_relative_date(text: str, now: datetime | None = None) -> datetime | None:
    text = text.strip()
    now = now or datetime.now()
    if _TIME_RE.match(text):
        hour, minute = (int(p) for p in text.split(":"))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if _MMDD_RE.match(text):
        month, day = (int(p) for p in text.split("."))
        return datetime(now.year, month, day)
    if _YYMMDD_RE.match(text):
        year, month, day = (int(p) for p in text.split("."))
        return datetime(2000 + year, month, day)
    return None


class FmKoreaCrawler:
    def __init__(self, board: str, client: PoliteHTTPClient | None = None) -> None:
        if board not in ALLOWED_BOARDS:
            raise ValueError(
                f"'{board}'는 robots.txt상 허용되지 않은 게시판입니다. "
                f"허용 목록: {sorted(ALLOWED_BOARDS)}"
            )
        self._board = board
        self._client = client or PoliteHTTPClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FmKoreaCrawler":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _list_url(self, page: int) -> str:
        return f"{BASE_URL}/{self._board}?page={page}"

    @staticmethod
    def _parse_int(cell) -> int | None:
        text = cell.get_text(strip=True) if cell else ""
        return int(text) if text.isdigit() else None

    def iter_post_summaries(self, max_pages: int = 50, since: datetime | None = None) -> Iterator[CommunityPost]:
        """목록 페이지(/best, /best2, /humor)만 순회하며 글 요약을 수집한다.

        본문 페이지는 robots.txt상 비허용이라 절대 요청하지 않는다.
        """
        now = datetime.now()
        for page in range(1, max_pages + 1):
            url = self._list_url(page)
            try:
                response = self._client.get(url)
            except RobotsDisallowedError as exc:
                logger.warning("FM코리아 수집 건너뜀(robots.txt): %s", exc)
                return

            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            table = soup.select_one("table.bd_lst")
            rows = [r for r in table.select("tbody > tr") if not r.get("class")] if table else []

            yielded_any = False
            for row in rows:
                title_a = row.select_one("td.title a")
                time_cell = row.select_one("td.time")
                if title_a is None or time_cell is None:
                    continue

                posted_at = _parse_relative_date(time_cell.get_text(strip=True), now=now)
                if since is not None and posted_at is not None and posted_at < since:
                    logger.info("%s: cutoff(%s) 도달, 수집 종료", self._board, since.date())
                    return

                views_cell, votes_cell = row.select("td.m_no")[:2] if len(row.select("td.m_no")) >= 2 else (None, None)

                yield CommunityPost(
                    community="fmkorea",
                    board=self._board,
                    title=title_a.get_text(strip=True),
                    url=urljoin(BASE_URL, title_a["href"]),
                    posted_at=posted_at,
                    views=self._parse_int(views_cell),
                    likes=self._parse_int(votes_cell),
                )
                yielded_any = True

            if not yielded_any:
                logger.info("%s: 더 이상 게시물이 없어 수집 종료 (page=%d)", self._board, page)
                return
