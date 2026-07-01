"""
Step 3: 수집된 모든 데이터를 병합하여
        최종 JSON과 CSV로 저장한 뒤 S3에 업로드

출력 파일:
  - yuhaengo_final.json  : 전체 구조화 데이터
  - yuhaengo_final.csv   : 스프레드시트용
  - yuhaengo_stats.json  : 통계 요약
"""
import argparse
import csv
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv


_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

RAW_FILES = [
    "word_list.json",
    "words_with_body.json",
    "yuhaengo_final.json",
    "yuhaengo_final.csv",
    "yuhaengo_stats.json",
]


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace('\n', ' ').replace('\r', ' ')
    return text


def load_json(path):
    if not os.path.exists(path):
        print(f"  파일 없음: {path}")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_s3_client():
    kwargs = {}
    endpoint_url = os.getenv("S3_ENDPOINT_URL", "").strip()
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    region = os.getenv("AWS_DEFAULT_REGION", "").strip()
    if region:
        kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)


def guess_content_type(path: Path) -> str:
    content_type, _ = mimetypes.guess_type(str(path))
    return content_type or "application/octet-stream"


def upload_to_s3(base_dir: Path, bucket: str, raw_prefix: str, run_id: str):
    s3 = build_s3_client()
    normalized = raw_prefix.strip("/")
    for filename in RAW_FILES:
        file_path = base_dir / filename
        if not file_path.exists():
            print(f"건너뜀: {filename} 없음")
            continue
        key = f"{normalized}/{run_id}/{filename}" if normalized else f"{run_id}/{filename}"
        s3.upload_file(str(file_path), bucket, key, ExtraArgs={"ContentType": guess_content_type(file_path)})
        print(f"업로드 완료: {filename} -> s3://{bucket}/{key}")


def merge_and_save(run_id: str):
    print("=== 데이터 병합 시작 ===\n")

    words_data = load_json("words_with_body.json") or load_json("words_with_desc.json")
    if not words_data:
        print("ERROR: words_with_body.json 없음. step2를 먼저 실행하세요.")
        return

    all_entries = []
    seen_urls = set()

    for item in words_data:
        url = item.get('url', '')
        if url in seen_urls:
            continue
        seen_urls.add(url)

        entry = {
            'word': clean_text(item.get('word', '')),
            'section': item.get('section', ''),
            'source': '메인목록',
            'body_text': clean_text(item.get('body_text', item.get('description', ''))),
            'display_text': clean_text(item.get('display_text', '')),
            'url': url,
            'href': item.get('href', ''),
            'crawl_status': item.get('status', ''),
        }
        all_entries.append(entry)

    print(f"총 {len(all_entries)}개 항목")
    print(f"  - 메인 목록: {len(words_data)}개")
    text_count = sum(1 for e in all_entries if e['body_text'])
    print(f"  - 본문 있음: {text_count}개 ({text_count/len(all_entries)*100:.1f}%)")

    final_data = {
        "meta": {
            "total_count": len(all_entries),
            "with_body_text": text_count,
            "sources": ["속어·유행어 관련 정보"]
        },
        "words": all_entries
    }

    with open("yuhaengo_final.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    print("\nyuhaengo_final.json 저장 완료!")

    csv_fields = ['word', 'section', 'source', 'body_text', 'display_text', 'url']
    with open("yuhaengo_final.csv", "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for entry in all_entries:
            writer.writerow({k: entry.get(k, '') for k in csv_fields})
    print("yuhaengo_final.csv 저장 완료!")

    section_stats = {}
    for e in all_entries:
        sec = e['section'] or e['source']
        if sec not in section_stats:
            section_stats[sec] = {'total': 0, 'with_body_text': 0}
        section_stats[sec]['total'] += 1
        if e['body_text']:
            section_stats[sec]['with_body_text'] += 1

    stats = {
        "total": len(all_entries),
        "with_body_text": text_count,
        "by_section": section_stats
    }
    with open("yuhaengo_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("yuhaengo_stats.json 저장 완료!")

    print("\n=== 샘플 출력 (본문 있는 항목) ===")
    samples = [e for e in all_entries if e['body_text']][:10]
    for e in samples:
        print(f"\n단어: {e['word']}")
        print(f"섹션: {e['section']}")
        print(f"본문: {e['body_text'][:150]}...")

    bucket = os.getenv("S3_BUCKET", "").strip()
    if not bucket:
        print("\nS3_BUCKET 미설정 - S3 업로드 건너뜀")
        return all_entries

    raw_prefix = os.getenv("S3_RAW_PREFIX", "trending-word/raw")
    base_dir = Path(".").resolve()
    print(f"\n=== S3 업로드 (run_id={run_id}) ===")
    upload_to_s3(base_dir, bucket, raw_prefix, run_id)
    print("S3 업로드 완료!")

    return all_entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="", help="S3 경로에 사용할 실행 ID")
    args = parser.parse_args()
    run_id = args.run_id.strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    merge_and_save(run_id)
