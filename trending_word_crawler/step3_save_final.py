"""
Step 3: 수집된 모든 데이터를 병합하여
        최종 JSON과 CSV로 저장

출력 파일:
  - yuhaengo_final.json  : 전체 구조화 데이터
  - yuhaengo_final.csv   : 스프레드시트용
  - yuhaengo_stats.json  : 통계 요약
"""
import json
import csv
import re
import os


def clean_text(text):
    """텍스트 정리"""
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


def merge_and_save():
    print("=== 데이터 병합 시작 ===\n")

    # 1. 메인 단어 + 본문 로드
    words_data = load_json("words_with_body.json") or load_json("words_with_desc.json")
    if not words_data:
        print("ERROR: words_with_body.json 없음. step2를 먼저 실행하세요.")
        return

    # 2. 병합
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

    # 3. 최종 JSON 저장
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

    # 4. CSV 저장
    csv_fields = ['word', 'section', 'source', 'body_text', 'display_text', 'url']
    with open("yuhaengo_final.csv", "w", encoding="utf-8-sig", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for entry in all_entries:
            writer.writerow({k: entry.get(k, '') for k in csv_fields})
    print("yuhaengo_final.csv 저장 완료!")

    # 5. 통계 저장
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

    # 6. 미리보기 출력
    print("\n=== 샘플 출력 (본문 있는 항목) ===")
    samples = [e for e in all_entries if e['body_text']][:10]
    for e in samples:
        print(f"\n단어: {e['word']}")
        print(f"섹션: {e['section']}")
        print(f"본문: {e['body_text'][:150]}...")

    return all_entries


if __name__ == "__main__":
    merge_and_save()