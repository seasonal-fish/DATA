# crawling

수집 도구 스택과, 그 위에 구현한 3가지 수집기(네이버 데이터랩 트렌드, 언론사 RSS·네이버 뉴스, 나무위키/커뮤니티 정적 크롤러).

## 도구 스택 원칙

- **정적 페이지** → `httpx` + `BeautifulSoup` (`common/http_client.py`, `static_html/`, `news/press_rss.py`)
- **대량/구조화 수집** → `Scrapy` (`scrapy_project/`) — 현재는 settings/pipeline만 구성된 스캐폴드. 게시판 전체 아카이브처럼 페이지 수가 많고 구조가 일정한 작업이 생기면 `scrapy_project/crawler/spiders/`에 스파이더를 추가한다.
- **JS 렌더링이 꼭 필요할 때만** → `Playwright` (`common/js_render.py`)
- 위 세 경로 모두 `common/` 모듈(robots.txt 검사, 호스트별 레이트리밋, 재시도, 저장)을 공유한다.

## 설치

```bash
cd crawling
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # JS 렌더링 폴백을 쓸 경우에만
cp .env.example .env   # NAVER_CLIENT_ID/SECRET 등 채우기
```

## common/ — 공통 수집 모듈

- `config.py`: `.env` 기반 설정 (`NAVER_CLIENT_ID/SECRET`, `CRAWLER_USER_AGENT`, 기본 요청 간격, 데이터 저장 경로)
- `http_client.py`: `PoliteHTTPClient` — 모든 정적 크롤러/RSS 수집기가 이걸 통해서만 외부 요청을 보낸다. 매 요청 전 robots.txt를 확인하고(`RobotsDisallowedError`로 차단), 호스트별 최소 요청 간격을 지키고, 429/430/5xx는 재시도하며 `Retry-After` 헤더를 받으면 해당 호스트의 지연을 자동으로 늘린다.
- `robots.py`: `RobotsChecker` — `urllib.robotparser`가 아니라 Scrapy도 쓰는 `protego`를 사용한다. fmkorea/dcinside처럼 `Disallow: /*search_keyword=` 같은 와일드카드 문법을 쓰는 실제 robots.txt를 표준 라이브러리는 정확히 해석하지 못해서다(`tests/test_robots_wildcards.py` 참고).
- `rate_limiter.py`: 호스트별 최소 요청 간격을 강제. robots.txt의 `Crawl-delay`나 `Retry-After`를 만나면 자동으로 늘어난다.
- `js_render.py`: Playwright 폴백. robots.txt/레이트리밋 정책은 동일하게 적용된다.
- `storage.py`: 결과를 `data/<subdir>/<name>_<timestamp>.jsonl`로 저장.
- `models.py`: `NewsArticle`, `TrendResult`, `WikiDocument`, `CommunityPost` 데이터클래스.

## datalab/ — 네이버 데이터랩 검색어트렌드

```bash
python -m datalab.cli --keyword "키워드" --synonym "동의어" --start 2025-06-23 --end 2026-06-23
```

`NaverDataLabClient.search_trend()`는 공식 API 제약(키워드 그룹 최대 5개, 그룹당 키워드 최대 20개, `timeUnit`/`device`/`gender`/`ages` 값 검증)을 호출 전에 검사한다.

## news/ — 언론사 RSS + 네이버 뉴스

```bash
python -m news.cli --keyword "사건명" --since-days 365 --naver
```

- `press_rss.py`: `feeds_config.yaml`에 등록된 언론사 RSS를 `httpx`로 받아 `feedparser.parse()`로 파싱한다. 등록된 피드는 curl로 200 응답 + 실제 RSS/XML 본문인지 직접 확인한 것만 넣었다(한겨레/연합뉴스/경향신문/동아닷컴/노컷뉴스/시사IN). **미디어오늘은 robots.txt가 `/rss/`를 막아서 자동으로 스킵된다** — 직접 확인해서 목록에서 뺐다.
- `naver_news_api.py`: **네이버는 2020년에 뉴스 RSS를 공식 종료했고 2025년 초 완전히 막았다.** 현재 "네이버 뉴스"를 RSS로 안정적으로 수집할 방법이 없어서, 같은 Client ID/Secret을 쓰는 공식 [뉴스 검색 오픈API](https://openapi.naver.com/v1/search/news.json)로 대체했다(사용자 확인 완료).

## static_html/ — 나무위키 · 커뮤니티 정적 크롤러

```bash
python -m static_html.cli namuwiki --title "문서명"
python -m static_html.cli dcinside --gallery programming --since-days 10
python -m static_html.cli fmkorea --board humor --since-days 365
```

- `namuwiki.py`: namu.wiki는 CSS 클래스가 빌드마다 해시되어 바뀌므로 클래스명에 의존하지 않는다. 대신 (1) 헤딩 태그 이름(h1~h6)과 (2) 섹션 헤딩 안의 `<span id="섹션제목">`(id 값 자체가 제목 텍스트)이라는 두 가지 안정적인 특징으로 목차/본문을 복원한다. robots.txt는 `/w/`(문서), `/history/`, `/backlink/`를 명시적으로 허용한다 — 이 크롤러는 `/w/`만 사용한다.
- `dcinside.py`: 갤러리 목록(`td.gall_num/gall_tit/gall_writer/gall_date/gall_count/gall_recommend`)에서 글 요약을 수집하고, 필요할 때만 `fetch_post_body()`로 본문을 가져온다. robots.txt가 갤러리/게시물 단위로 개별 차단하는 목록을 **하드코딩하지 않고** 요청 시점에 동적으로 받아 판단한다(차단된 갤러리 호출 시 0건 + 경고 로그로 자동 스킵, 직접 확인함).
- `fmkorea.py`: **robots.txt(`User-agent: *`)는 `/`, `/best`, `/best2`, `/humor` 목록 페이지만 허용하고 개별 게시물(숫자 경로)은 비허용이다.** 따라서 이 크롤러는 목록에 보이는 제목/글쓴이/시각/조회수/추천수까지만 수집하고 본문은 가져오지 않는다(시도해도 `RobotsDisallowedError`). 허용된 게시판 외 값은 생성 시점에 `ValueError`로 막아둔다. 추가로 자체 WAF가 짧은 시간에 여러 요청을 보내면 HTTP 430 + `Retry-After`로 일시 차단하는 것을 확인했다 — `PoliteHTTPClient`가 이 헤더를 읽어 해당 호스트의 요청 간격을 자동으로 늘린다.

### 네이트판(pann.nate.com)은 수집 대상에서 제외했다

robots.txt가 `User-agent: * / Disallow: /`로 일반 크롤러를 전부 막고, Googlebot·Twitterbot 등 이름이 명시된 특정 봇에게만 제한적으로 허용한다. 우리 크롤러가 그 봇들을 사칭해 접근하는 것은 robots.txt를 지키는 게 아니라 우회하는 것이므로 구현하지 않았다. (요청 시 "1,2,4" 중 네이트판이 포함되어 있었으나, 조사 결과를 공유하고 디시인사이드+FM코리아로 진행함.)

## scrapy_project/ — 대량/구조화 수집 스캐폴드

```bash
cd scrapy_project
scrapy list   # 등록된 스파이더 확인
scrapy crawl <spider_name>
```

`ROBOTSTXT_OBEY=True`, `AUTOTHROTTLE_ENABLED=True`, `common/.env`의 `CRAWLER_USER_AGENT`를 그대로 사용하도록 `settings.py`에서 `common/` 모듈을 import해 재사용한다. 결과는 `crawler.pipelines.JsonlExportPipeline`이 `data/scrapy/`에 스트리밍으로 저장한다. 아직 구체적인 대량 수집 대상이 없어 스파이더는 비워둠 — 필요해지면 `spiders/__init__.py`의 안내를 참고해 추가한다.

## 테스트

```bash
pytest
```

`tests/test_robots_wildcards.py`는 `protego`가 fmkorea/네이트판류 robots.txt의 와일드카드(`*`, `$`) 문법을 표준 `urllib.robotparser`와 달리 올바르게 해석하는지 확인한다.
