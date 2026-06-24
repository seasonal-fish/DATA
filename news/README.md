# crawl_urls.py

뉴스 등 URL의 기사 본문을 추출해 JSONL로 저장하는 스크립트.

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용법

URL을 입력하는 방법은 세 가지이며, 섞어서 동시에 줄 수도 있다(자동으로 중복 제거됨).

**1. URL을 직접 입력 (가장 기본)**

```bash
python crawl_urls.py https://example.com/article1 https://example.com/article2
```

**2. 텍스트 파일로 입력 (한 줄에 URL 하나) — 새로 들어오는 URL은 이 방식을 권장**

```bash
python crawl_urls.py --url-file urls.txt
```

`urls.txt` 예시 (`#`로 시작하는 줄과 빈 줄은 무시됨):

```
# 2026-06-24 신규 수집 대상
https://example.com/article1
https://example.com/article2
```

**3. 예전 `adguard_db_v3.json` 형식 호환 입력 (레거시)**

```bash
python crawl_urls.py --legacy-json adguard_db_v3.json
```

`sensitive_issues.records[].urls`에 들어있는 URL을 모두 뽑아서 처리한다. **입력 데이터가 이 JSON 구조를 따르지 않게 되면 더 이상 쓸 수 없으므로, 새로 들어오는 URL은 2번(`--url-file`) 방식을 기본으로 쓴다.** 어떤 형태로 URL이 들어오든(엑셀, 메모, 다른 JSON 구조 등) 줄바꿈으로 구분된 URL 목록으로만 변환하면 그대로 처리할 수 있다.

## 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--output` | `output/url_content_<UTC타임스탬프>.jsonl` | 결과 저장 경로 |
| `--delay` | `1.0` | 요청 사이 대기 시간(초) |
| `--timeout` | `15.0` | 요청 타임아웃(초) |

## 출력

`output/`에 JSONL로 저장된다(한 줄에 결과 하나, `git`에는 커밋되지 않음 — `.gitignore` 참고). 매 URL을 처리할 때마다 즉시 한 줄씩 써서 저장하므로, 중간에 실행이 멈춰도 그 시점까지 처리된 결과는 파일에 남아있다.

성공 시:

```json
{"url": "...", "status": "ok", "title": "...", "date": "...", "text": "..."}
```

실패 시(요청 실패 또는 본문 추출 실패):

```json
{"url": "...", "status": "error", "error": "..."}
```

## crawl_urls.py 사용

- 새 URL 묶음이 들어오면, 형식에 맞는 새 파서를 만들기보다 **URL만 한 줄씩 뽑아 텍스트 파일로 만들고 `--url-file`로 실행**하는 것을 기본으로 한다. JSON이든 엑셀이든 어떤 형태로 들어오든 URL 목록 추출까지만 하면 이 스크립트는 그대로 재사용된다.
- `--legacy-json`은 기존 `adguard_db_v3.json` 구조를 위한 호환 코드이며, 더 이상 그 구조로 데이터가 들어오지 않는다면 `crawl_urls.py`의 `read_legacy_json` 함수와 함께 제거해도 된다.
- robots.txt 준수나 호스트별 요청 속도 제한 같은 정책은 적용되어 있지 않다(이미 선별된 개별 기사 URL을 대상으로 한다고 가정). 대량/사이트 크롤링이 필요해지면 `BE/crawling/common/http_client.py`의 `PoliteHTTPClient`(robots.txt 검사 + 레이트리밋 + 재시도 포함)를 쓰는 쪽으로 옮기는 걸 고려한다.
- 본문 추출은 [`trafilatura`](https://github.com/adbar/trafilatura)가 처리한다 — 특정 사이트 구조에 맞춘 파서가 아니라 범용 기사 본문 추출기이므로, 사이트마다 다른 URL을 다룰 때 적합하다. 특정 사이트 전용 수집이 필요하면 `BE/crawling/static_html/`의 사이트별 파서 패턴을 참고한다.
