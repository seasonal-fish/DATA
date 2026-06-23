"""사용 예:
  python -m news.cli --keyword "사건명" --naver --since-days 365
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from common.logging_config import get_logger
from common.storage import save_jsonl
from news.naver_news_api import NaverNewsSearchClient
from news.press_rss import collect_press_rss

logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="언론사 RSS + 네이버 뉴스 검색 수집")
    parser.add_argument("--keyword", required=True, help="제목/요약 필터 키워드 (네이버 뉴스 검색어로도 사용)")
    parser.add_argument("--since-days", type=int, default=None, help="최근 N일 이내 기사만 (언론사 RSS)")
    parser.add_argument("--naver", action="store_true", help="네이버 뉴스 검색 API도 함께 수집")
    parser.add_argument("--max-results", type=int, default=100, help="네이버 뉴스 검색 최대 건수")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.since_days) if args.since_days else None
    articles = collect_press_rss(keywords=[args.keyword], since=since)
    logger.info("언론사 RSS 수집: %d건", len(articles))

    if args.naver:
        with NaverNewsSearchClient() as client:
            articles += client.search_news(args.keyword, max_results=args.max_results)

    out_path = save_jsonl(articles, collector_name=f"news_{args.keyword}", subdir="news")
    logger.info("저장 완료: %s (총 %d건)", out_path, len(articles))


if __name__ == "__main__":
    main()
