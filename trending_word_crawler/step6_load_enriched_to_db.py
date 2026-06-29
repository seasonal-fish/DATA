import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg import connect
from psycopg.sql import SQL, Identifier


_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def ensure_table(conn, schema: str, table: str):
    query = SQL(
        """
        CREATE SCHEMA IF NOT EXISTS {schema};
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            word TEXT PRIMARY KEY,
            meaning TEXT NOT NULL,
            sentiment TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL,
            reason TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    ).format(schema=Identifier(schema), table=Identifier(table))

    with conn.cursor() as cur:
        cur.execute(query)
    conn.commit()


def upsert_rows(conn, schema: str, table: str, rows, batch_size: int):
    statement = SQL(
        """
        INSERT INTO {schema}.{table} (
            word, meaning, sentiment, confidence, reason
        ) VALUES (
            %(word)s, %(meaning)s, %(sentiment)s, %(confidence)s, %(reason)s
        )
        ON CONFLICT (word) DO UPDATE SET
            meaning = EXCLUDED.meaning,
            sentiment = EXCLUDED.sentiment,
            confidence = EXCLUDED.confidence,
            reason = EXCLUDED.reason,
            updated_at = NOW();
        """
    ).format(schema=Identifier(schema), table=Identifier(table))

    with conn.cursor() as cur:
        for batch in chunked(rows, batch_size):
            cur.executemany(statement, batch)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="yuhaengo_enriched.json 결과를 DB에 적재합니다.")
    parser.add_argument("--input", default="yuhaengo_enriched.json", help="입력 JSON 경로")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경변수가 비어 있습니다.")

    schema = os.getenv("DB_SCHEMA", "public").strip() or "public"
    table = os.getenv("DB_TABLE", "trending_word_enriched").strip() or "trending_word_enriched"
    batch_size = int(os.getenv("DB_BATCH_SIZE", "100"))

    input_path = Path(args.input).resolve()
    data = load_json(input_path)
    rows = data.get("words", [])

    if not rows:
        print("적재할 rows가 없습니다.")
        return

    with connect(database_url) as conn:
        ensure_table(conn, schema, table)
        upsert_rows(conn, schema, table, rows, batch_size)

    print(f"DB 적재 완료: {len(rows)}건 -> {schema}.{table}")


if __name__ == "__main__":
    main()