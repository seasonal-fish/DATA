from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

from common.config import settings


class HostRateLimiter:
    """호스트 단위로 마지막 요청 시각을 기억해 최소 간격을 강제하는 레이트 리미터.

    robots.txt의 Crawl-delay가 기본 지연시간보다 길면 그 값을 우선한다.
    """

    def __init__(self, default_delay_seconds: float | None = None) -> None:
        self._default_delay = default_delay_seconds or settings.default_request_delay_seconds
        self._lock = threading.Lock()
        self._last_request_at: dict[str, float] = {}
        self._host_delay: dict[str, float] = {}

    def set_host_delay(self, host: str, delay_seconds: float) -> None:
        with self._lock:
            self._host_delay[host] = max(delay_seconds, self._default_delay)

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        delay = self._host_delay.get(host, self._default_delay)
        with self._lock:
            last = self._last_request_at.get(host, 0.0)
            now = time.monotonic()
            sleep_for = max(0.0, delay - (now - last))
            self._last_request_at[host] = now + sleep_for

        if sleep_for > 0:
            time.sleep(sleep_for)


default_rate_limiter = HostRateLimiter()
