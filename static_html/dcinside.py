"""디시인사이드 갤러리 정적 HTML 크롤러 (httpx + BeautifulSoup).

robots.txt(gall.dcinside.com)는 일반 크롤러(User-agent: *)에게 기본적으로 전체
허용이지만, 특정 갤러리/게시물 목록을 명시적으로 비허용한다. 이 목록은
PoliteHTTPClient -> RobotsChecker가 요청 시점에 실제 robots.txt를 받아와
동적으로 판단하므로, 차단된 갤러리를 호출하면 RobotsDisallowedError로 자동
스킵된다(코드에 차단 목록을 하드코딩하지 않는다).
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common.http_client import PoliteHTTPClient, RobotsDisallowedError
from common.logging_config import get_logger
from common.models import CommunityPost

logger = get_logger(__name__)

BASE_URL = "https://gall.dcinside.com"


class DCInsideCrawler:
    def __init__(
        self,
        gallery_id: str,
        gallery_type: str = "major",
        client: PoliteHTTPClient | None = None,
    ) -> None:
        if gallery_type not in {"major", "minor"}:
            raise ValueError("gallery_type은 'major' 또는 'minor'여야 합니다.")
        self._gallery_id = gallery_id
        self._board_path = "board" if gallery_type == "major" else "mgallery/board"
        self._client = client or PoliteHTTPClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "DCInsideCrawler":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _list_url(self, page: int) -> str:
        return f"{BASE_URL}/{self._board_path}/lists/?id={self._gallery_id}&page={page}"

    @staticmethod
    def _parse_posted_at(date_td) -> datetime | None:
        title_attr = date_td.get("title") if date_td else None
        if not title_attr:
            return None
        try:
            return datetime.strptime(title_attr, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    @staticmethod
    def _parse_int(cell) -> int | None:
        text = cell.get_text(strip=True) if cell else ""
        return int(text) if text.isdigit() else None

    def iter_post_summaries(self, max_pages: int = 50, since: datetime | None = None) -> Iterator[CommunityPost]:
        """목록 페이지만 순회하며 글 요약(제목/링크/시각/조회수/추천수)을 수집한다.

        디시인사이드 목록은 최신글이 위에 오므로, since보다 오래된 글을 만나면
        더 이전 페이지를 볼 필요가 없어 즉시 중단한다(1년치만 필요한 경우 등).
        """
        for page in range(1, max_pages + 1):
            url = self._list_url(page)
            try:
                response = self._client.get(url)
            except RobotsDisallowedError as exc:
                logger.warning("디시인사이드 수집 건너뜀(robots.txt): %s", exc)
                return

            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")
            rows = soup.select("tr.ub-content")

            yielded_any = False
            for row in rows:
                num_cell = row.select_one("td.gall_num")
                if not num_cell or not num_cell.get_text(strip=True).isdigit():
                    continue  # 공지/AD/설문 등 일반 게시물이 아닌 행은 제외

                title_a = row.select_one("td.gall_tit a")
                date_cell = row.select_one("td.gall_date")
                if title_a is None or date_cell is None:
                    continue

                posted_at = self._parse_posted_at(date_cell)
                if since is not None and posted_at is not None and posted_at < since:
                    logger.info("%s: cutoff(%s) 도달, 수집 종료", self._gallery_id, since.date())
                    return

                yield CommunityPost(
                    community="dcinside",
                    board=self._gallery_id,
                    title=title_a.get_text(strip=True),
                    url=urljoin(BASE_URL, title_a["href"]),
                    posted_at=posted_at,
                    views=self._parse_int(row.select_one("td.gall_count")),
                    likes=self._parse_int(row.select_one("td.gall_recommend")),
                )
                yielded_any = True

            if not yielded_any:
                logger.info("%s: 더 이상 게시물이 없어 수집 종료 (page=%d)", self._gallery_id, page)
                return

    def fetch_post_body(self, url: str) -> str | None:
        """개별 게시물 본문이 필요할 때만 호출한다(목록 수집보다 요청 비용이 큼)."""
        try:
            response = self._client.get(url)
        except RobotsDisallowedError as exc:
            logger.warning("게시물 본문 수집 건너뜀(robots.txt): %s", exc)
            return None
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        content = soup.select_one("div.write_div")
        return content.get_text(" ", strip=True) if content else None
