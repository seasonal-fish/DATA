"""URL의 기사 본문을 추출해 JSONL로 저장한다.

사용 예:
  python crawl_urls.py https://example.com/article1 https://example.com/article2
  python crawl_urls.py --url-file urls.txt
  python crawl_urls.py --legacy-json adguard_db_v3.json   # 과거 adguard_db_v3.json 형식 호환용

자세한 사용법은 README.md 참고.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import trafilatura

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_content(url: str, timeout: float = 15.0) -> dict:
    """URL 하나의 기사 본문을 추출한다.

    실패해도 예외를 던지지 않고 status="error"인 dict를 반환한다 — 배치 실행 중
    한 URL이 죽어도 나머지 URL 처리가 멈추지 않게 하기 위함.
    """
    try:
        resp = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return {"url": url, "status": "error", "error": f"fetch_failed: {e}"}

    try:
        extracted = trafilatura.extract(html, url=url, with_metadata=True, output_format="json")
    except Exception as e:
        return {"url": url, "status": "error", "error": f"extract_failed: {e}"}

    if extracted:
        data = json.loads(extracted)
        text = data.get("text")
        if text:
            return {
                "url": url,
                "status": "ok",
                "title": data.get("title"),
                "date": data.get("date"),
                "text": text,
            }

    return {"url": url, "status": "error", "error": "extraction_failed"}


def read_url_file(path: Path) -> list[str]:
    """한 줄에 URL 하나씩 적힌 텍스트 파일을 읽는다. 빈 줄/`#`로 시작하는 줄은 무시한다."""
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def read_legacy_json(path: Path) -> list[str]:
    """과거 adguard_db_v3.json 형식(`sensitive_issues.records[].urls`)에서 URL만 뽑아낸다.

    이후 입력 형식이 이 구조를 따르지 않을 수 있어 호환용으로만 둔다 — 새 입력은
    --url-file(한 줄에 URL 하나)을 쓰는 걸 권장한다.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("sensitive_issues", {}).get("records", [])
    urls = []
    for record in records:
        urls.extend(record.get("urls") or [])
    return urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="URL의 기사 본문을 추출해 JSONL로 저장")
    parser.add_argument("urls", nargs="*", help="직접 입력하는 URL (공백으로 구분)")
    parser.add_argument("--url-file", type=Path, help="한 줄에 URL 하나씩 적힌 텍스트 파일")
    parser.add_argument("--legacy-json", type=Path, help="(호환용) sensitive_issues.records[].urls 구조의 기존 json 파일")
    parser.add_argument("--output", type=Path, help="결과를 저장할 JSONL 경로 (기본: output/url_content_<timestamp>.jsonl)")
    parser.add_argument("--delay", type=float, default=1.0, help="요청 간 대기 시간(초), 기본 1초")
    parser.add_argument("--timeout", type=float, default=15.0, help="요청 타임아웃(초), 기본 15초")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    urls: list[str] = list(args.urls)
    if args.url_file:
        urls += read_url_file(args.url_file)
    if args.legacy_json:
        urls += read_legacy_json(args.legacy_json)
    urls = list(dict.fromkeys(urls))  # 순서 유지하며 중복 제거

    if not urls:
        raise SystemExit("URL을 하나 이상 지정하세요 (직접 입력 / --url-file / --legacy-json 중 하나). --help 참고.")

    output_path = args.output
    if output_path is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = Path("output") / f"url_content_{timestamp}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    with output_path.open("w", encoding="utf-8") as out:
        for i, url in enumerate(urls, 1):
            result = fetch_content(url, timeout=args.timeout)
            out.write(json.dumps(result, ensure_ascii=False))
            out.write("\n")
            out.flush()

            if result["status"] == "ok":
                ok += 1
            else:
                fail += 1
            print(f"[{i}/{len(urls)}] {result['status']}: {url}", flush=True)

            if i < len(urls):
                time.sleep(args.delay)

    print(f"Done. ok={ok} fail={fail} total={len(urls)} -> {output_path}")


if __name__ == "__main__":
    main()
