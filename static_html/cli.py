"""사용 예:
  python -m static_html.cli namuwiki --title "버닝썬 게이트"
  python -m static_html.cli dcinside --gallery programming --since-days 365
  python -m static_html.cli fmkorea --board humor --since-days 365
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from common.logging_config import get_logger
from common.storage import save_jsonl
from static_html.dcinside import DCInsideCrawler
from static_html.fmkorea import FmKoreaCrawler
from static_html.namuwiki import NamuWikiCrawler

logger = get_logger(__name__)


def _since(days: int | None) -> datetime | None:
    return datetime.now() - timedelta(days=days) if days else None


def run_namuwiki(args: argparse.Namespace) -> None:
    with NamuWikiCrawler() as crawler:
        docs = crawler.fetch_documents(args.title)
    out_path = save_jsonl(docs, collector_name="namuwiki", subdir="namuwiki")
    logger.info("저장 완료: %s (%d개 문서)", out_path, len(docs))


def run_dcinside(args: argparse.Namespace) -> None:
    with DCInsideCrawler(args.gallery, gallery_type=args.gallery_type) as crawler:
        posts = list(crawler.iter_post_summaries(max_pages=args.max_pages, since=_since(args.since_days)))
    out_path = save_jsonl(posts, collector_name=f"dcinside_{args.gallery}", subdir="dcinside")
    logger.info("저장 완료: %s (%d건)", out_path, len(posts))


def run_fmkorea(args: argparse.Namespace) -> None:
    with FmKoreaCrawler(args.board) as crawler:
        posts = list(crawler.iter_post_summaries(max_pages=args.max_pages, since=_since(args.since_days)))
    out_path = save_jsonl(posts, collector_name=f"fmkorea_{args.board}", subdir="fmkorea")
    logger.info("저장 완료: %s (%d건)", out_path, len(posts))


def main() -> None:
    parser = argparse.ArgumentParser(description="정적 HTML 크롤러 실행")
    sub = parser.add_subparsers(dest="command", required=True)

    p_namu = sub.add_parser("namuwiki", help="나무위키 문서 수집")
    p_namu.add_argument("--title", action="append", required=True, help="문서 제목 (반복 가능)")
    p_namu.set_defaults(func=run_namuwiki)

    p_dc = sub.add_parser("dcinside", help="디시인사이드 갤러리 목록 수집")
    p_dc.add_argument("--gallery", required=True, help="갤러리 ID")
    p_dc.add_argument("--gallery-type", choices=["major", "minor"], default="major")
    p_dc.add_argument("--max-pages", type=int, default=50)
    p_dc.add_argument("--since-days", type=int, default=365)
    p_dc.set_defaults(func=run_dcinside)

    p_fm = sub.add_parser("fmkorea", help="FM코리아 목록 수집 (best/best2/humor만 가능)")
    p_fm.add_argument("--board", required=True, choices=["best", "best2", "humor"])
    p_fm.add_argument("--max-pages", type=int, default=50)
    p_fm.add_argument("--since-days", type=int, default=365)
    p_fm.set_defaults(func=run_fmkorea)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
