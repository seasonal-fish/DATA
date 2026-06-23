"""네이버 뉴스 검색 오픈API(GET /v1/search/news.json) 클라이언트.

네이버는 2020년 뉴스 RSS를 공식 종료했고(2025년 초 완전 차단) 현재 '네이버 뉴스'를
feedparser/RSS로 안정적으로 수집할 방법이 없다. 대신 공식 REST API인 뉴스 검색
API를 사용한다. DataLab과 동일한 NAVER_CLIENT_ID/SECRET을 재사용한다.
"""

from __future__ import annotations

import html as html_module
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from common.config import settings
from common.logging_config import get_logger
from common.models import NewsArticle

logger = get_logger(__name__)

NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
MAX_DISPLAY_PER_CALL = 100
MAX_START = 1000  # API 제약: start + display가 1000을 넘을 수 없음


class NaverNewsAPIError(RuntimeError):
    """뉴스 검색 API가 200이 아닌 응답을 돌려줄 때 발생."""


def _clean_text(value: str) -> str:
    return html_module.unescape(BeautifulSoup(value, "html.parser").get_text())


def _parse_pub_date(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


class NaverNewsSearchClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if client_id and client_secret:
            self._client_id, self._client_secret = client_id, client_secret
        else:
            self._client_id, self._client_secret = settings.require_naver_credentials()
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NaverNewsSearchClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _get(self, params: dict) -> dict:
        response = self._client.get(
            NEWS_SEARCH_URL,
            params=params,
            headers={
                "X-Naver-Client-Id": self._client_id,
                "X-Naver-Client-Secret": self._client_secret,
            },
        )
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        if response.status_code != 200:
            raise NaverNewsAPIError(f"뉴스 검색 API 오류 {response.status_code}: {response.text}")
        return response.json()

    def search_news(
        self,
        query: str,
        sort: str = "date",
        max_results: int = 100,
    ) -> list[NewsArticle]:
        """query로 네이버 뉴스를 검색한다. sort: 'date'(최신순) 또는 'sim'(정확도순).

        API 제약상 start+display <= 1000이므로 최대 1000건까지 페이지네이션한다.
        """
        if sort not in {"date", "sim"}:
            raise ValueError("sort는 'date' 또는 'sim'이어야 합니다.")
        max_results = min(max_results, MAX_START)

        articles: list[NewsArticle] = []
        start = 1
        while len(articles) < max_results:
            display = min(MAX_DISPLAY_PER_CALL, max_results - len(articles))
            if start + display - 1 > MAX_START:
                break

            data = self._get({"query": query, "display": display, "start": start, "sort": sort})
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                articles.append(
                    NewsArticle(
                        source="naver_news_api",
                        title=_clean_text(item.get("title", "")),
                        link=item.get("originallink") or item.get("link", ""),
                        published_at=_parse_pub_date(item.get("pubDate", "")),
                        summary=_clean_text(item.get("description", "")),
                    )
                )

            start += display
            if len(items) < display:
                break

        logger.info("네이버 뉴스 검색 '%s': %d건 수집", query, len(articles))
        return articles
