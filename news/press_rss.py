"""언론사 RSS 피드를 feedparser로 안정적으로 수집한다.

httpx(PoliteHTTPClient)로 직접 바이트를 받아온 뒤 feedparser.parse()에 넘긴다.
feedparser가 자체적으로 URL을 열게 하면 타임아웃/재시도/robots.txt 준수를
제어할 수 없기 때문이다.
"""

from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import feedparser
import yaml

from common.http_client import PoliteHTTPClient, RobotsDisallowedError
from common.logging_config import get_logger
from common.models import NewsArticle

logger = get_logger(__name__)

DEFAULT_FEEDS_CONFIG = Path(__file__).resolve().parent / "feeds_config.yaml"


def load_feeds(config_path: Path = DEFAULT_FEEDS_CONFIG) -> list[dict]:
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("feeds", [])


def _to_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)


def fetch_feed(client: PoliteHTTPClient, source_name: str, url: str) -> list[NewsArticle]:
    try:
        response = client.get(url)
    except RobotsDisallowedError as exc:
        logger.warning("RSS 수집 건너뜀(robots.txt): %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001 - 개별 피드 실패가 전체 수집을 막지 않도록 함
        logger.warning("RSS 가져오기 실패 (%s): %s", source_name, exc)
        return []

    parsed = feedparser.parse(response.content)
    if parsed.bozo:
        logger.warning("RSS 파싱 경고 (%s): %s", source_name, parsed.bozo_exception)

    articles = []
    for entry in parsed.entries:
        articles.append(
            NewsArticle(
                source=source_name,
                title=entry.get("title", "").strip(),
                link=entry.get("link", ""),
                published_at=_to_datetime(entry),
                summary=entry.get("summary", "").strip(),
            )
        )
    return articles


def collect_press_rss(
    config_path: Path = DEFAULT_FEEDS_CONFIG,
    keywords: Iterable[str] | None = None,
    since: datetime | None = None,
) -> list[NewsArticle]:
    """모든 등록된 언론사 RSS를 수집한다.

    keywords가 주어지면 제목/요약에 키워드가 포함된 기사만 남긴다(과거 논란·민감 이슈 검색용).
    since가 주어지면 그 시점 이후 기사만 남긴다.
    """
    feeds = load_feeds(config_path)
    keywords = [k.lower() for k in keywords] if keywords else None

    all_articles: list[NewsArticle] = []
    with PoliteHTTPClient() as client:
        for feed in feeds:
            articles = fetch_feed(client, feed["name"], feed["url"])
            logger.info("%s: %d건 수집", feed["name"], len(articles))
            all_articles.extend(articles)

    if since is not None:
        all_articles = [a for a in all_articles if a.published_at is None or a.published_at >= since]

    if keywords:
        all_articles = [
            a
            for a in all_articles
            if any(k in a.title.lower() or k in a.summary.lower() for k in keywords)
        ]

    return all_articles
