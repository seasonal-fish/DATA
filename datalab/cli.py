"""사용 예: python -m datalab.cli --keyword "급발진" --start 2025-06-23 --end 2026-06-23"""

from __future__ import annotations

import argparse

from common.logging_config import get_logger
from common.storage import save_jsonl
from datalab.client import NaverDataLabClient

logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="네이버 데이터랩 검색어트렌드 조회")
    parser.add_argument("--keyword", required=True, help="조회할 키워드 (그룹명과 동일하게 사용)")
    parser.add_argument("--synonym", action="append", default=[], help="같은 그룹으로 묶을 동의어/이형태 (반복 가능)")
    parser.add_argument("--start", required=True, help="조회 시작일 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="조회 종료일 YYYY-MM-DD")
    parser.add_argument("--time-unit", default="date", choices=["date", "week", "month"])
    args = parser.parse_args()

    keyword_groups = [{"groupName": args.keyword, "keywords": [args.keyword, *args.synonym]}]

    with NaverDataLabClient() as client:
        results = client.search_trend(
            keyword_groups=keyword_groups,
            start_date=args.start,
            end_date=args.end,
            time_unit=args.time_unit,
        )

    out_path = save_jsonl(results, collector_name=f"datalab_{args.keyword}", subdir="datalab")
    logger.info("저장 완료: %s (%d개 그룹)", out_path, len(results))


if __name__ == "__main__":
    main()
