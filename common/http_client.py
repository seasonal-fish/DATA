from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from common.config import settings
from common.logging_config import get_logger
from common.rate_limiter import HostRateLimiter, default_rate_limiter
from common.robots import RobotsChecker, default_robots_checker

logger = get_logger(__name__)


class RobotsDisallowedError(RuntimeError):
    """robots.txt가 해당 URL의 수집을 허용하지 않을 때 발생."""


class PoliteHTTPClient:
    """robots.txt 검사 + 호스트별 레이트 리밋 + 재시도를 갖춘 httpx 래퍼.

    모든 정적 HTML 크롤러(나무위키, 디시인사이드, FM코리아 등)와 RSS 수집기가
    이 클라이언트를 통해서만 외부 사이트에 접근한다.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        timeout: float = 15.0,
        obey_robots: bool = True,
        robots_checker: RobotsChecker | None = None,
        rate_limiter: HostRateLimiter | None = None,
    ) -> None:
        self._user_agent = user_agent or settings.user_agent
        self._obey_robots = obey_robots
        self._robots = robots_checker or default_robots_checker
        self._rate_limiter = rate_limiter or default_rate_limiter
        self._client = httpx.Client(
            headers={"User-Agent": self._user_agent},
            timeout=timeout,
            follow_redirects=True,
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def get(self, url: str, **kwargs) -> httpx.Response:
        if self._obey_robots and not self._robots.can_fetch(url):
            raise RobotsDisallowedError(f"robots.txt에 의해 비허용: {url}")

        self._rate_limiter.wait(url)
        logger.debug("GET %s", url)
        response = self._client.get(url, **kwargs)

        # 429/430 등 사이트 자체 레이트리밋(WAF)에 걸린 경우 Retry-After를 읽어
        # 해당 호스트의 다음 요청 간격을 늘려둔다. 다음 재시도(tenacity)나
        # 이후의 다른 요청들이 이 늘어난 간격을 그대로 적용받는다.
        if response.status_code in (429, 430):
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                host = httpx.URL(url).host
                logger.warning("%s가 %s초간 차단 신호(Retry-After)를 보냄 — 호스트 지연을 늘립니다.", host, retry_after)
                self._rate_limiter.set_host_delay(host, float(retry_after))

        if response.status_code >= 500 or response.status_code in (429, 430):
            response.raise_for_status()
        return response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteHTTPClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
