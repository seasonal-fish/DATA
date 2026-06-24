"""adguard_db_v3.json의 sensitive_issues 레코드를 url_contents(기사 본문) 기반으로
재요약해 new_description을 갱신한다.

사용 예:
  python summarize_descriptions.py adguard_db_v3.json
  python summarize_descriptions.py adguard_db_v3.json --output result.json
  python summarize_descriptions.py adguard_db_v3.json --dry-run
  python summarize_descriptions.py adguard_db_v3.json --only-issue-id KR-001

OPENAI_API_KEY는 .env 파일에 넣어두면 자동으로 읽힌다 (.env.example 참고).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_MODEL = "gpt-4o-mini"
MAX_CHARS_PER_ARTICLE = 4000  # 기사 본문이 길 때 토큰 비용을 줄이기 위한 절단 길이

SYSTEM_PROMPT = (
    "너는 한국 뉴스 이슈를 정리하는 에디터다. 주어진 이슈 제목과 관련 기사 본문들을 바탕으로 "
    "사실 위주로 간결한 한국어 요약을 작성한다. 추측이나 의견은 배제하고 기사에 나온 사실만 "
    "시간 순으로 정리한다. 3~5문장, 350자 이내로 작성하고 요약문 외의 다른 말은 덧붙이지 않는다."
)


def build_user_prompt(record: dict) -> str:
    lines = [f"이슈 제목: {record.get('title', '')}"]
    if record.get("description"):
        lines.append(f"기존 설명: {record['description']}")

    for i, url_content in enumerate(record.get("url_contents", []), 1):
        if url_content.get("status") != "ok":
            continue
        text = (url_content.get("text") or "")[:MAX_CHARS_PER_ARTICLE]
        lines.append(
            f"\n[기사 {i}] {url_content.get('title', '')} ({url_content.get('date', '')})\n{text}"
        )

    lines.append("\n위 내용을 바탕으로 new_description을 작성해줘.")
    return "\n".join(lines)


def summarize_record(client: OpenAI, record: dict, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(record)},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="url_contents 기반으로 new_description을 재작성")
    parser.add_argument("input", type=Path, help="adguard_db_v3.json 경로")
    parser.add_argument("--output", type=Path, help="결과를 저장할 경로 (기본: 입력 파일을 덮어씀)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI 모델 (기본: {DEFAULT_MODEL})")
    parser.add_argument("--dry-run", action="store_true", help="API를 호출하지 않고 대상 레코드 수만 출력")
    parser.add_argument("--only-issue-id", help="지정한 issue_id 하나만 처리 (디버그용)")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    records = data.get("sensitive_issues", {}).get("records", [])
    if args.only_issue_id:
        records = [r for r in records if r.get("issue_id") == args.only_issue_id]

    targets = [r for r in records if r.get("url_contents")]
    print(f"대상 레코드: {len(targets)}/{len(records)}")
    if args.dry_run:
        return

    output_path = args.output or args.input
    client = OpenAI()

    ok = fail = 0
    for i, record in enumerate(targets, 1):
        try:
            record["new_description"] = summarize_record(client, record, args.model)
            ok += 1
            print(f"[{i}/{len(targets)}] ok: {record.get('issue_id')}")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(targets)}] error: {record.get('issue_id')} -> {e}")

        # 매 레코드 처리 후 즉시 저장 — 중간에 멈춰도 그 시점까지 결과는 파일에 남는다.
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Done. ok={ok} fail={fail} total={len(targets)} -> {output_path}")


if __name__ == "__main__":
    main()
