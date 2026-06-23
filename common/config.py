from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CRAWLING_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    naver_client_id: str = field(default_factory=lambda: os.getenv("NAVER_CLIENT_ID", ""))
    naver_client_secret: str = field(default_factory=lambda: os.getenv("NAVER_CLIENT_SECRET", ""))
    user_agent: str = field(
        default_factory=lambda: os.getenv(
            "CRAWLER_USER_AGENT", "ProjectCrawler/1.0 (+mailto:contact@example.com)"
        )
    )
    default_request_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("DEFAULT_REQUEST_DELAY_SECONDS", "2.0"))
    )
    data_dir: Path = field(
        default_factory=lambda: (CRAWLING_ROOT / os.getenv("DATA_DIR", "./data")).resolve()
    )

    def require_naver_credentials(self) -> tuple[str, str]:
        if not self.naver_client_id or not self.naver_client_secret:
            raise RuntimeError(
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET이 설정되어 있지 않습니다. "
                ".env 파일을 확인하세요 (.env.example 참고)."
            )
        return self.naver_client_id, self.naver_client_secret


settings = Settings()
