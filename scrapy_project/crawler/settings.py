# Scrapy settings for crawler project — 대량/구조화 수집(예: 한 사이트의 게시판 전체를
# 페이지네이션하며 훑는 작업)이 필요할 때 이 프로젝트에 스파이더를 추가해서 쓴다.
# 정적 페이지 한두 개를 가볍게 긁을 때는 httpx+BeautifulSoup(static_html/, news/)을 쓰고,
# JS 렌더링이 필요할 때만 common/js_render.py(Playwright)를 쓴다.

import sys
from pathlib import Path

# crawling/ 루트를 sys.path에 추가해 common/ 패키지(robots, rate_limiter, storage 등)를
# 스파이더/파이프라인에서 그대로 재사용할 수 있게 한다.
CRAWLING_ROOT = Path(__file__).resolve().parents[2]
if str(CRAWLING_ROOT) not in sys.path:
    sys.path.insert(0, str(CRAWLING_ROOT))

from common.config import settings as project_settings  # noqa: E402

BOT_NAME = "crawler"

SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

# common/.env의 CRAWLER_USER_AGENT를 그대로 사용해 모든 수집기가 동일한 정체성을 갖게 한다.
USER_AGENT = project_settings.user_agent

# robots.txt를 반드시 지킨다.
ROBOTSTXT_OBEY = True

# 동시성을 낮게, 자동으로 서버 응답 속도에 맞춰 지연을 조절한다.
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = project_settings.default_request_delay_seconds

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = project_settings.default_request_delay_seconds
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# 429/503 등을 받으면 재시도하며 점점 더 느리게 요청한다.
RETRY_ENABLED = True
RETRY_TIMES = 3

ITEM_PIPELINES = {
    "crawler.pipelines.JsonlExportPipeline": 300,
}

FEED_EXPORT_ENCODING = "utf-8"
