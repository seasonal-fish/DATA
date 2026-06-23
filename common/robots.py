from __future__ import annotations

import threading
from urllib.parse import urljoin, urlparse

import httpx
from protego import Protego

from common.config import settings
from common.logging_config import get_logger
from common.rate_limiter import default_rate_limiter

logger = get_logger(__name__)


class RobotsChecker:
    """런타임에 각 호스트의 robots.txt를 받아와 파싱하고 캐시한다.

    urllib.robotparser는 구글 확장 문법(`*`, `$` 와일드카드)을 해석하지 못해
    실제 서비스의 robots.txt(예: fmkorea, dcinside)를 정확히 따르지 못한다.
    Scrapy가 내부적으로 쓰는 protego를 사용해 동일한 수준으로 와일드카드를 해석한다.
    """

    def __init__(self, user_agent: str | None = None, timeout: float = 10.0) -> None:
        self._user_agent = user_agent or settings.user_agent
        self._timeout = timeout
        self._lock = threading.Lock()
        self._cache: dict[str, Protego] = {}

    def _origin(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_parser(self, url: str) -> Protego:
        origin = self._origin(url)
        with self._lock:
            cached = self._cache.get(origin)
        if cached is not None:
            return cached

        robots_url = urljoin(origin + "/", "robots.txt")
        try:
            response = httpx.get(
                robots_url,
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout,
                follow_redirects=True,
            )
            body = response.text if response.status_code == 200 else ""
        except httpx.HTTPError as exc:
            logger.warning("robots.txt 조회 실패(%s): %s — 보수적으로 전체 비허용 처리", robots_url, exc)
            body = "User-agent: *\nDisallow: /\n"

        parser = Protego.parse(body)
        with self._lock:
            self._cache[origin] = parser

        delay = parser.crawl_delay(self._user_agent)
        if delay:
            default_rate_limiter.set_host_delay(urlparse(origin).netloc, float(delay))

        return parser

    def can_fetch(self, url: str) -> bool:
        parser = self._get_parser(url)
        allowed = parser.can_fetch(url, self._user_agent)
        if not allowed:
            logger.info("robots.txt에 의해 차단된 URL: %s", url)
        return allowed


default_robots_checker = RobotsChecker()
