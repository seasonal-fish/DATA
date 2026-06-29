"""mim_terms 테이블의 단어들에 대해 네이버 데이터랩 검색어트렌드 API로
최근 7일간의 일별 검색 비율(ratio) 평균을 구해 DB에 반영한다.

DB는 SSH 터널(베스천 서버)을 통해서만 접근 가능한 RDS PostgreSQL이므로
sshtunnel로 로컬 포트를 RDS:5432로 포워딩한 뒤 psycopg2로 접속한다.

주의: 데이터랩 API는 절대 검색량이 아니라 0~100으로 정규화된 상대 비율이다.
한 번의 호출에 최대 5개 키워드그룹만 묶이고, 정규화 기준(=100)이 호출마다
달라지므로 avg_search_ratio_7d 값은 같은 단어의 시계열 추세를 보는 용도이며
단어 간 절대 비교에는 쓸 수 없다.

사용:
    python3 sync_search_trend.py            # 전체 단어 처리
    python3 sync_search_trend.py --limit 5   # 일부만 테스트
"""
from __future__ import annotations

import argparse
import os
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import paramiko
import psycopg2
from dotenv import dotenv_values

if not hasattr(paramiko, "DSSKey"):
    # sshtunnel 0.4.0이 참조하는 DSSKey가 paramiko>=3에서 제거됨. 우리는 RSA 키만
    # 쓰므로 동작에는 영향 없는 더미 별칭으로 AttributeError만 막는다.
    paramiko.DSSKey = paramiko.RSAKey

from sshtunnel import SSHTunnelForwarder  # noqa: E402

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"
# 데이터랩은 같은 요청에 묶인 키워드그룹 전체를 합쳐 정규화(최댓값=100)한다.
# 여러 단어를 한 그룹에 묶으면 단어별 ratio가 묶인 상대방에 따라 달라지므로
# 반드시 단어 1개당 1번씩 단독으로 호출한다.
BATCH_SIZE = 1
REQUEST_DELAY_SECONDS = 0.3
MAX_RETRIES = 3


def load_env() -> dict:
    env = {**dotenv_values(ENV_PATH), **os.environ}
    required = [
        "SSH_HOST", "SSH_PORT", "SSH_USER", "SSH_PEM_PATH",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD",
        "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
    ]
    missing = [k for k in required if not env.get(k)]
    if missing:
        raise RuntimeError(f"{ENV_PATH}에 다음 값이 없습니다: {missing}")
    return env


def fetch_batch_averages(
    client: httpx.Client, headers: dict, words: list[str], start_date: str, end_date: str
) -> dict[str, float | None]:
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": [{"groupName": w, "keywords": [w]} for w in words],
    }

    # 데이터랩은 검색량이 거의 없는 날은 데이터 포인트를 생략한다(0으로 채워주지 않음).
    # 누락된 날을 그냥 빼고 평균을 내면 검색량이 적을수록 평균이 더 높게 나오는
    # 왜곡이 생기므로, 빠진 날은 ratio=0으로 채워서 항상 전체 기간으로 나눈다.
    start_d = date.fromisoformat(start_date)
    end_d = date.fromisoformat(end_date)
    all_periods = [(start_d + timedelta(days=i)).isoformat() for i in range((end_d - start_d).days + 1)]

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.post(DATALAB_URL, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                averages: dict[str, float | None] = {}
                for item in data.get("results", []):
                    by_period = {p["period"]: p["ratio"] for p in item.get("data", [])}
                    ratios = [by_period.get(period, 0.0) for period in all_periods]
                    averages[item["title"]] = round(statistics.mean(ratios), 2)
                return averages
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = RuntimeError(f"HTTP {response.status_code}: {response.text}")
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"데이터랩 API 오류 {response.status_code}: {response.text}")
        except httpx.TransportError as exc:
            last_error = exc
            time.sleep(2 * attempt)

    raise RuntimeError(f"{words} 조회 재시도 실패: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="테스트용: 일부 단어만 처리")
    args = parser.parse_args()

    env = load_env()

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=6)
    start_date, end_date = start.isoformat(), end.isoformat()
    print(f"조회 기간: {start_date} ~ {end_date} (최근 7일)")

    naver_headers = {
        "X-Naver-Client-Id": env["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": env["NAVER_CLIENT_SECRET"],
        "Content-Type": "application/json",
    }

    with SSHTunnelForwarder(
        (env["SSH_HOST"], int(env["SSH_PORT"])),
        ssh_username=env["SSH_USER"],
        ssh_pkey=env["SSH_PEM_PATH"],
        remote_bind_address=(env["DB_HOST"], int(env["DB_PORT"])),
    ) as tunnel:
        conn = psycopg2.connect(
            host="127.0.0.1",
            port=tunnel.local_bind_port,
            dbname=env["DB_NAME"],
            user=env["DB_USER"],
            password=env["DB_PASSWORD"],
        )
        try:
            cur = conn.cursor()
            query = "SELECT id, word FROM mim_terms ORDER BY id"
            if args.limit:
                query += f" LIMIT {args.limit}"
            cur.execute(query)
            rows = cur.fetchall()  # [(id, word), ...]
            print(f"대상 행: {len(rows)}")

            # 같은 단어가 여러 id에 중복될 수 있으므로 단어 기준으로 1회만 조회
            unique_words = sorted({word for _, word in rows})
            word_to_avg: dict[str, float | None] = {}
            failed_words: list[str] = []

            with httpx.Client(timeout=10.0) as client:
                for i in range(0, len(unique_words), BATCH_SIZE):
                    batch = unique_words[i : i + BATCH_SIZE]
                    try:
                        word_to_avg.update(
                            fetch_batch_averages(client, naver_headers, batch, start_date, end_date)
                        )
                    except RuntimeError as exc:
                        print(f"  실패: {batch} -> {exc}")
                        failed_words.extend(batch)
                    print(f"  진행: {min(i + BATCH_SIZE, len(unique_words))}/{len(unique_words)}")
                    time.sleep(REQUEST_DELAY_SECONDS)

            updated = 0
            for row_id, word in rows:
                avg_ratio = word_to_avg.get(word)
                if avg_ratio is None:
                    continue
                cur.execute(
                    """
                    UPDATE mim_terms
                    SET avg_search_ratio_7d = %s, search_trend_updated_at = now()
                    WHERE id = %s
                    """,
                    (avg_ratio, row_id),
                )
                updated += 1
            conn.commit()

            print(f"완료: {updated}/{len(rows)}건 업데이트, 실패 단어: {failed_words}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
