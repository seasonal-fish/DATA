from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsArticle:
    source: str  # 언론사명 또는 "naver_news_api"
    title: str
    link: str
    published_at: datetime | None
    summary: str = ""
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TrendPoint:
    period: str  # YYYY-MM-DD
    ratio: float


@dataclass
class TrendResult:
    keyword_group: str
    keywords: list[str]
    start_date: str
    end_date: str
    time_unit: str
    points: list[TrendPoint]


@dataclass
class WikiDocument:
    title: str
    url: str
    sections: list[str]  # 섹션 제목 목록(목차)
    text: str
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CommunityPost:
    community: str  # 예: "dcinside", "fmkorea"
    board: str  # 갤러리 ID / 게시판 이름
    title: str
    url: str
    posted_at: datetime | None
    views: int | None = None
    likes: int | None = None
    collected_at: datetime = field(default_factory=datetime.utcnow)
