import argparse
import mimetypes
import os
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

ENRICHED_FILES = [
    "yuhaengo_enriched.json",
]


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


def upload_group(s3_client, bucket, base_dir: Path, prefix: str, run_id: str, filenames):
    uploaded = []
    normalized_prefix = prefix.strip("/")

    for filename in filenames:
        file_path = base_dir / filename
        if not file_path.exists():
            print(f"건너뜀: {file_path.name} 없음")
            continue

        key = f"{normalized_prefix}/{run_id}/{file_path.name}" if normalized_prefix else f"{run_id}/{file_path.name}"
        extra_args = {"ContentType": guess_content_type(file_path)}

        s3_client.upload_file(str(file_path), bucket, key, ExtraArgs=extra_args)
        uploaded.append({"file": file_path.name, "s3_key": key})
        print(f"업로드 완료: {file_path.name} -> s3://{bucket}/{key}")

    return uploaded


def main():
    parser = argparse.ArgumentParser(description="trending_word_crawler 산출물을 S3에 업로드합니다.")
    parser.add_argument("--base-dir", default=".", help="산출물 디렉터리")
    parser.add_argument("--run-id", default="", help="S3 하위 경로에 사용할 실행 ID")
    args = parser.parse_args()

    bucket = os.getenv("S3_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("S3_BUCKET 환경변수가 비어 있습니다.")

    raw_prefix = os.getenv("S3_RAW_PREFIX", "trending-word/raw")
    enriched_prefix = os.getenv("S3_ENRICHED_PREFIX", "trending-word/enriched")

    run_id = args.run_id.strip() or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_dir = Path(args.base_dir).resolve()

    s3_client = build_s3_client()

    raw_uploaded = upload_group(s3_client, bucket, base_dir, raw_prefix, run_id, RAW_FILES)
    enriched_uploaded = upload_group(s3_client, bucket, base_dir, enriched_prefix, run_id, ENRICHED_FILES)

    print(f"원본 업로드: {len(raw_uploaded)}개")
    print(f"정제본 업로드: {len(enriched_uploaded)}개")


if __name__ == "__main__":
    main()