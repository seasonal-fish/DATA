"""JS 렌더링이 꼭 필요한 페이지에서만 쓰는 Playwright 기반 폴백 렌더러.

httpx+BeautifulSoup(static_html/, news/)로 충분한 정적 페이지에는 쓰지 않는다.
브라우저를 띄우는 비용이 훨씬 크고, 사이트 입장에서도 일반 HTTP 클라이언트보다
부담이 큰 요청이기 때문이다. robots.txt/레이트리밋 정책은 PoliteHTTPClient와
동일하게 공통 모듈(common.robots, common.rate_limiter)을 그대로 재사용한다.
"""

from __future__ import annotations

from playwright.sync_api import Browser, sync_playwright

from common.config import settings
from common.http_client import RobotsDisallowedError
from common.logging_config import get_logger
from common.rate_limiter import default_rate_limiter
from common.robots import default_robots_checker

logger = get_logger(__name__)


class JsRenderer:
    def __init__(self, headless: bool = True, obey_robots: bool = True) -> None:
        self._obey_robots = obey_robots
        self._playwright = sync_playwright().start()
        self._browser: Browser = self._playwright.chromium.launch(headless=headless)
        self._context = self._browser.new_context(user_agent=settings.user_agent)

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._playwright.stop()

    def __enter__(self) -> "JsRenderer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def render_html(
        self,
        url: str,
        wait_selector: str | None = None,
        timeout_ms: int = 15000,
    ) -> str:
        """url을 렌더링한 뒤 최종 DOM의 HTML을 문자열로 반환한다."""
        if self._obey_robots and not default_robots_checker.can_fetch(url):
            raise RobotsDisallowedError(f"robots.txt에 의해 비허용: {url}")

        default_rate_limiter.wait(url)
        logger.debug("Playwright GET %s", url)

        page = self._context.new_page()
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return page.content()
        finally:
            page.close()
