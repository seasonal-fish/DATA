"""
Step 2: word_list.json에서 각 단어 URL을 읽어
                개별 페이지 본문 텍스트를 추출하고 words_with_body.json으로 저장

추출 내용:
    - body_text : 해당 단어 페이지 본문 텍스트(텍스트만)

주의: 나무위키는 rate limit이 있으므로 천천히 크롤링 (2초 간격)
- 중간 저장: checkpoint.json (재시작 가능)
- 429 발생 시 지수 백오프 (최대 15분 대기)
- 예상 소요 시간: 1160개 × 2초 = ~38분
"""
import json
import re
import time
import os
import subprocess
from bs4 import BeautifulSoup

REQUEST_DELAY = 2.0   # 요청 간 기본 간격 (초)
CHECKPOINT_FILE = "checkpoint.json"
OUTPUT_FILE = "words_with_body.json"


def fetch_page_curl(url, timeout=20):
    """curl로 단일 페이지 가져오기"""
    try:
        result = subprocess.run([
            'curl', '-s', '-L',
            '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '-H', 'Accept: text/html,application/xhtml+xml',
            '-H', 'Accept-Language: ko-KR,ko;q=0.9',
            '-H', 'Cache-Control: no-cache',
            '--max-time', str(timeout),
            '-w', '\n%{http_code}',
            url
        ], capture_output=True, timeout=timeout + 5)

        output = result.stdout.decode('utf-8', errors='replace')
        if '\n' in output:
            *body_parts, status_code = output.rsplit('\n', 1)
            body = '\n'.join(body_parts)
            status = int(status_code.strip()) if status_code.strip().isdigit() else 0
        else:
            body = output
            status = 0

        return body, status
    except subprocess.TimeoutExpired:
        return '', 408
    except Exception as e:
        return '', 0


def extract_section_text(soup, section_id):
    """섹션 앵커(s-1, s-2 ...)의 본문 텍스트를 반환"""
    anchor = soup.find(id=section_id)
    if not anchor:
        return ""
    heading = anchor.parent
    if not heading:
        return ""
    d1 = heading.parent
    if not d1:
        return ""
    d2 = d1.parent
    if not d2:
        return ""
    content_div = d2.find_next_sibling()
    if not content_div:
        return ""
    text = content_div.get_text(separator=' ', strip=True)
    return re.sub(r'\s+', ' ', text).strip()


def extract_body_text(html: str) -> str:
    """나무위키 단어 페이지 HTML에서 본문 텍스트만 추출"""
    soup = BeautifulSoup(html, 'html.parser')

    section_texts = []
    section_ids = {
        tag.get('id') for tag in soup.find_all(id=True)
        if re.match(r'^s-\d+(?:\.\d+)?$', tag.get('id', ''))
    }

    def section_key(section_id):
        nums = section_id[2:].split('.')
        return tuple(int(n) for n in nums)

    for section_id in sorted(section_ids, key=section_key):
        text = extract_section_text(soup, section_id)
        if text and len(text) > 5:
            section_texts.append(text)

    if section_texts:
        merged = '\n\n'.join(section_texts)
    else:
        for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        merged = soup.get_text(separator=' ', strip=True)

    merged = re.sub(r'\s+', ' ', merged).strip()
    return merged[:12000]


def load_checkpoint():
    """체크포인트에서 완료된 URL 목록 로드"""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_checkpoint(done_map):
    """체크포인트 저장"""
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(done_map, f, ensure_ascii=False)


def crawl_all():
    # 단어 목록 로드
    with open("word_list.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    all_words = []
    for section, words in data['main_words'].items():
        for w in words:
            all_words.append({**w, 'section': section})

    # 체크포인트 로드 (재시작 지원)
    done_map = load_checkpoint()
    pending = [w for w in all_words if w['url'] not in done_map]

    print(f"총 {len(all_words)}개 단어")
    print(f"이미 완료: {len(done_map)}개")
    print(f"남은 단어: {len(pending)}개")
    print(f"요청 간격: {REQUEST_DELAY}초")
    print(f"예상 소요 시간: {len(pending) * REQUEST_DELAY / 60:.1f}분\n")

    wait_until = 0  # 429 발생 시 대기 시작 시각
    backoff = 60    # 초기 백오프 (초)

    for i, word_data in enumerate(pending):
        url = word_data['url']
        word = word_data['word']

        # 429 백오프 대기
        if wait_until > time.time():
            remaining = wait_until - time.time()
            print(f"  Rate limit 대기 중... {remaining:.0f}초 남음")
            time.sleep(remaining)
            backoff = min(backoff * 2, 900)  # 최대 15분

        # 페이지 요청
        html, status = fetch_page_curl(url)

        if status == 200:
            body_text = extract_body_text(html)
            done_map[url] = {
                **word_data,
                'body_text': body_text,
                'status': 'ok'
            }
            backoff = 60  # 성공 시 백오프 리셋

            if (i + 1) % 20 == 0:
                remaining_count = len(pending) - i - 1
                print(f"  [{i+1}/{len(pending)}] {word} | 본문: {bool(body_text)} "
                      f"| 남은: {remaining_count}개 (~{remaining_count * REQUEST_DELAY / 60:.1f}분)")
                save_checkpoint(done_map)  # 20개마다 중간 저장

        elif status == 429:
            print(f"  [{i+1}] 429 Rate Limit - {backoff}초 대기 후 재시도")
            wait_until = time.time() + backoff
            time.sleep(backoff)
            # 현재 항목 재처리를 위해 i를 되돌릴 수 없으므로 실패로 기록
            done_map[url] = {**word_data, 'body_text': '', 'status': f'rate_limited'}
            backoff = min(backoff * 2, 900)

        else:
            done_map[url] = {**word_data, 'body_text': '', 'status': f'http_{status}'}

        # 요청 간 딜레이
        time.sleep(REQUEST_DELAY)

    # 최종 저장
    save_checkpoint(done_map)

    current_urls = {w['url'] for w in all_words}
    results = [v for k, v in done_map.items() if k in current_urls]
    section_order = ['숫자', '라틴문자', 'ㄱ', 'ㄴ', 'ㄷ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅅ',
                     'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ', '기타']
    results.sort(key=lambda x: (
        section_order.index(x.get('section', '')) if x.get('section') in section_order else 99,
        x.get('word', '')
    ))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r.get('status') == 'ok')
    text_count = sum(1 for r in results if r.get('body_text'))
    print(f"\n=== 완료 ===")
    print(f"  성공: {ok}/{len(results)}")
    print(f"  본문 있음: {text_count}/{len(results)}")
    print(f"  {OUTPUT_FILE} 저장 완료!")


if __name__ == "__main__":
    crawl_all()
