import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv


# 스크립트가 trending_word_crawler/ 안에 있으므로 상위 Data/.env 를 명시적으로 로드
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_sentiment(label):
    if not label:
        return "중립"
    text = str(label).strip().lower()
    if text in {"긍정", "positive", "pos", "+", "plus"}:
        return "긍정"
    if text in {"부정", "negative", "neg", "-", "minus"}:
        return "부정"
    if text in {"중립", "neutral", "neu", "0"}:
        return "중립"
    return "중립"


def parse_json_from_text(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise ValueError("응답에서 JSON을 파싱할 수 없습니다.")


def call_openai_for_word(client, model, word_item, body_limit):
    body_text = (word_item.get("body_text") or "").strip()
    if len(body_text) > body_limit:
        body_text = body_text[:body_limit]

    prompt = (
        "아래는 최근 대중 사이에서 유행하는 단어 정보입니다.\\n"
        "이 단어를 광고·마케팅·브랜드 캠페인에 활용했을 때 일반 대중이 느끼는 반응을 기준으로 아래 요구사항에 맞게 JSON만 출력하세요.\\n"
        "요구사항:\\n"
        "1) meaning: 단어 뜻을 한국어 1~2문장으로 요약\\n"
        "2) sentiment: 아래 기준으로 긍정/부정/중립 중 하나를 선택\\n"
        "   - 긍정: 이 단어를 광고에 사용하면 대중이 호감·공감·즐거움 등 긍정적 반응을 보일 가능성이 높음\\n"
        "   - 부정: 이 단어를 광고에 사용하면 불쾌감·거부감·논란 등 부정적 반응을 유발할 가능성이 높음 (성적 농담·이중적 의미·혐오 표현 등으로 오해받을 소지가 있는 경우 포함)\\n"
        "   - 중립: 단어 자체의 이미지가 뚜렷하지 않아 긍정/부정 판단이 어렵거나, 맥락에 따라 크게 달라짐\\n"
        "3) confidence: 판단의 확신도를 0.0~1.0 숫자로\\n"
        "4) reason: 광고 활용 시 대중 반응을 그렇게 판단한 근거를 한국어 한 문장으로\\n"
        "출력 형식(JSON): "
        '{"meaning":"...","sentiment":"긍정|부정|중립","confidence":0.0,"reason":"..."}'
        "\\n\\n"
        f"word: {word_item.get('word', '')}\\n"
        f"section: {word_item.get('section', '')}\\n"
        f"display_text: {word_item.get('display_text', '')}\\n"
        f"body_text: {body_text}"
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )

    raw_text = response.output_text or ""
    parsed = parse_json_from_text(raw_text)

    sentiment = normalize_sentiment(parsed.get("sentiment"))
    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < 0.0:
        confidence = 0.0
    if confidence > 1.0:
        confidence = 1.0

    return {
        "meaning": str(parsed.get("meaning", "")).strip(),
        "sentiment": sentiment,
        "confidence": confidence,
        "reason": str(parsed.get("reason", "")).strip(),
    }


def enrich_words(input_path, output_path, model, body_limit, max_retries, retry_wait, limit):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 비어 있습니다.")

    data = load_json(input_path)
    words = data.get("words", [])

    if limit is not None and limit > 0:
        words = words[:limit]

    client = OpenAI(api_key=api_key)

    enriched_words = []
    total = len(words)

    for idx, item in enumerate(words, start=1):
        last_error = None
        result = None

        for attempt in range(1, max_retries + 1):
            try:
                result = call_openai_for_word(client, model, item, body_limit)
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(retry_wait)

        if result is None:
            result = {
                "meaning": "",
                "sentiment": "중립",
                "confidence": 0.0,
                "reason": f"API 실패: {last_error}",
            }

        slim = {
            "word": item.get("word", ""),
            "meaning": result["meaning"],
            "sentiment": result["sentiment"],
            "confidence": result["confidence"],
            "reason": result["reason"],
        }
        enriched_words.append(slim)

        print(f"[{idx}/{total}] {item.get('word', '')} 처리 완료 | 감성: {slim['sentiment']}")

    output = {
        "meta": {
            **data.get("meta", {}),
            "model": model,
            "enriched_count": len(enriched_words),
        },
        "words": enriched_words,
    }

    save_json(output_path, output)


def main():
    parser = argparse.ArgumentParser(
        description="yuhaengo_final_test.json을 OpenAI API로 뜻/감성 분석하여 저장합니다."
    )
    parser.add_argument(
        "--input",
        default="yuhaengo_final_test.json",
        help="입력 JSON 경로",
    )
    parser.add_argument(
        "--output",
        default="yuhaengo_enriched_test.json",
        help="출력 JSON 경로",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        help="사용할 OpenAI 모델명 (기본값: .env의 OPENAI_MODEL)",
    )
    parser.add_argument(
        "--body-limit",
        type=int,
        default=int(os.getenv("OPENAI_BODY_LIMIT", "4000")),
        help="각 단어당 body_text 최대 전달 길이",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
        help="API 실패 시 최대 재시도 횟수",
    )
    parser.add_argument(
        "--retry-wait",
        type=float,
        default=float(os.getenv("OPENAI_RETRY_WAIT", "1.5")),
        help="재시도 대기 시간(초)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("WORD_LIMIT", "0")),
        help="테스트용 처리 개수 제한(0이면 전체)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    limit = args.limit if args.limit > 0 else None

    enrich_words(
        input_path=input_path,
        output_path=output_path,
        model=args.model,
        body_limit=args.body_limit,
        max_retries=args.max_retries,
        retry_wait=args.retry_wait,
        limit=limit,
    )

    print(f"완료: {output_path}")


if __name__ == "__main__":
    main()