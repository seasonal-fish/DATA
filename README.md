# Data

인터넷 유행어·밈 데이터 수집 및 가공 파이프라인 모음.

## 구조

```
Data/
├── mim/                        # 밈 단어 수집 및 트렌드 동기화
│   ├── get_mim_data.py         # careet.net 딕셔너리 크롤링 → DB 저장
│   └── sync_search_trend.py    # 네이버 데이터랩 검색 트렌드 → DB 반영
├── news/                       # 뉴스 기사 수집 및 요약
│   ├── crawl_urls.py           # URL 목록 → 본문 추출 → JSONL 저장
│   └── summarize_descriptions.py # 기사 본문 → OpenAI 요약
├── trending_word_crawler/      # 나무위키 유행어 수집 파이프라인
│   ├── run_all.sh              # 전체 파이프라인 실행
│   ├── step1_get_word_list.py  # 유행어 목록 수집
│   ├── step2_crawl_descriptions.py # 개별 단어 페이지 본문 크롤링
│   ├── step3_save_final.py     # 데이터 병합 및 S3 업로드
│   ├── step4_enrich_with_openai.py # S3 → OpenAI 감성 분석 → S3 저장
│   └── step5_load_enriched_to_db.py # S3 → DB 적재
├── tests/                      # 유닛 테스트
├── Dockerfile
└── requirements.txt
```

## 모듈별 설명

### mim/

**`get_mim_data.py`** — careet.net의 밈 딕셔너리를 전체 크롤링해 `public.mim_terms` 테이블에 적재합니다.

```bash
python mim/get_mim_data.py
```

- Selenium headless 브라우저로 로그인 후 1~69페이지 순회
- `word` + `definition` upsert (나머지 컬럼은 다른 프로세스가 채움)
- 필요 env: `CAREET_EMAIL`, `CAREET_PASSWORD`, DB 접속 정보

**`sync_search_trend.py`** — `mim_terms` 테이블의 단어들을 네이버 데이터랩 API로 조회해 최근 90일 일별 검색 비율을 업데이트합니다.

```bash
python mim/sync_search_trend.py
python mim/sync_search_trend.py --limit 5   # 테스트용
```

- 필요 env: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, DB 접속 정보

---

### news/

**`crawl_urls.py`** — URL 목록을 받아 기사 본문을 추출하고 JSONL로 저장합니다.

```bash
python news/crawl_urls.py https://example.com/article1
python news/crawl_urls.py --url-file urls.txt
```

**`summarize_descriptions.py`** — JSONL 기사 본문을 OpenAI API로 요약합니다.

- 필요 env: `OPENAI_API_KEY`

---

### trending_word_crawler/

나무위키 속어·유행어 페이지에서 단어를 수집해 OpenAI로 뜻·감성을 분석한 뒤 DB에 적재하는 5단계 파이프라인입니다.

```bash
cd trending_word_crawler
bash run_all.sh
```

| 단계 | 역할 | 입력 → 출력 |
|------|------|------------|
| step1 | 유행어 목록 수집 | 나무위키 → `word_list.json` |
| step2 | 단어별 본문 크롤링 | `word_list.json` → `words_with_body.json` |
| step3 | 병합 및 S3 업로드 | `words_with_body.json` → `yuhaengo_final.json` + S3 raw |
| step4 | OpenAI 감성 분석 | S3 raw → `yuhaengo_enriched.json` + S3 enriched |
| step5 | DB 적재 | S3 enriched → `public.trending_word_enriched` |

`WORD_LIMIT` env로 수집 단어 수를 제한해 테스트할 수 있습니다.

---

## 환경 설정

```bash
cp .env.example .env
# .env에 필요한 값 입력
```

주요 env 항목:

| 항목 | 설명 |
|------|------|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `CAREET_EMAIL` / `CAREET_PASSWORD` | careet.net 로그인 정보 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 네이버 데이터랩 API 키 |
| `DATABASE_URL` | PostgreSQL 접속 URL (프로덕션) |
| `SSH_*` / `DB_*` | SSH 터널 접속 정보 (로컬 개발) |
| `S3_BUCKET` | trending_word_crawler 결과 저장 버킷 |
| `WORD_LIMIT` | 수집 단어 수 제한 (0 = 전체) |

## 설치 및 실행

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # trending_word_crawler step1 전용
```

## 테스트

```bash
pytest
```

## 스케줄러

`scheduler.py`는 `trending_word_crawler` 파이프라인을 주기적으로 실행합니다. Docker 컨테이너의 기본 실행 파일입니다.

```bash
python scheduler.py
```

| env | 기본값 | 설명 |
|-----|--------|------|
| `PIPELINE_ENABLED` | `false` | `true`로 설정해야 스케줄러가 활성화됨 |
| `PIPELINE_SCHEDULE_CRON` | `0 3 * * *` | cron 표현식 (기본: 매일 새벽 3시) |
| `PIPELINE_TIMEZONE` | `Asia/Seoul` | 타임존 |

`PIPELINE_ENABLED=false`(기본)이면 즉시 종료되어 컨테이너를 다른 용도로 사용할 수 있습니다.
`true`로 설정하면 cron 스케줄에 맞춰 step1~5를 순차 실행하며, 중간 단계 실패 시 해당 실행을 중단하고 다음 스케줄에서 재시도합니다.

## 배포

GitHub Actions로 main 브랜치에 push 시 Docker 이미지를 빌드해 ECR에 푸시합니다.
크롤러 수동 실행은 GitHub Actions의 `workflow_dispatch`로 EC2에서 직접 실행할 수 있습니다.
