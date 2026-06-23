"""나무위키 정적 HTML 크롤러 (httpx + BeautifulSoup).

namu.wiki는 페이지마다 CSS 클래스가 빌드 시점에 해시되어 바뀌므로
class 이름에 의존한 파싱은 깨지기 쉽다. 대신 다음 두 가지 안정적인
특징만 사용한다.

1. 헤딩 태그 이름(h1~h6)은 해시되지 않는다 -> 문서 순서대로 h-태그를 모으면
   목차 구조를 그대로 복원할 수 있다.
2. 각 섹션 헤딩 안의 `<span id="섹션제목">섹션제목...</span>` 처럼
   id 속성 값 자체가 섹션 제목 텍스트와 같다(각주 anchor는 `s-1`, `rfn-1`,
   `fn-1` 형태라 구분 가능).

robots.txt(namu.wiki)는 `/w/`, `/history/`, `/backlink/`를 명시적으로 허용하므로
문서 본문(/w/<title>) 수집은 robots.txt 상 허용된 경로다. 그 외 경로는 기본적으로
전부 비허용이므로 이 모듈은 /w/ 문서 조회 용도로만 사용해야 한다.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup, Comment, NavigableString

from common.http_client import PoliteHTTPClient, RobotsDisallowedError
from common.logging_config import get_logger
from common.models import WikiDocument

logger = get_logger(__name__)

BASE_URL = "https://namu.wiki"
_ANCHOR_ID_PATTERN = re.compile(r"^(s|rfn|fn)-\d+$")
_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]


def _is_real_text(node) -> bool:
    """주석(Comment) 등을 제외한 실제 텍스트 노드인지 확인한다.

    Comment는 NavigableString의 서브클래스라 isinstance(node, str) 검사만으로는
    `<!--v-if-->` 같은 Vue 템플릿 주석까지 본문 텍스트로 섞여 들어온다.
    """
    return isinstance(node, NavigableString) and not isinstance(node, Comment)


class NamuWikiCrawler:
    def __init__(self, client: PoliteHTTPClient | None = None) -> None:
        self._client = client or PoliteHTTPClient()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "NamuWikiCrawler":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def fetch_document(self, title: str) -> WikiDocument | None:
        url = f"{BASE_URL}/w/{quote(title)}"
        try:
            response = self._client.get(url)
        except RobotsDisallowedError as exc:
            logger.warning("나무위키 문서 수집 건너뜀(robots.txt): %s", exc)
            return None

        if response.status_code == 404:
            logger.warning("문서를 찾을 수 없음: %s", title)
            return None
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        sections = self._extract_sections(soup)
        text = "\n\n".join(f"# {heading}\n{body}" for heading, body in sections if body)

        return WikiDocument(
            title=title,
            url=url,
            sections=[heading for heading, _ in sections],
            text=text,
        )

    def fetch_documents(self, titles: list[str]) -> list[WikiDocument]:
        results = []
        for title in titles:
            doc = self.fetch_document(title)
            if doc is not None:
                results.append(doc)
        return results

    @staticmethod
    def _heading_title(heading_tag) -> str:
        title_span = heading_tag.find(
            lambda tag: tag.name == "span"
            and tag.get("id")
            and not _ANCHOR_ID_PATTERN.match(tag["id"])
        )
        if title_span is None:
            return heading_tag.get_text(strip=True)

        direct_children = [c for c in title_span.children if _is_real_text(c)]
        direct_text = "".join(direct_children).strip()
        return direct_text or title_span.get_text(strip=True)

    def _extract_sections(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        headings = soup.find_all(_HEADING_TAGS)
        if not headings:
            return []

        nodes = list(soup.descendants)
        position = {id(node): idx for idx, node in enumerate(nodes)}

        sections: list[tuple[str, str]] = []
        for i, heading in enumerate(headings):
            start = position[id(heading)]
            end = position[id(headings[i + 1])] if i + 1 < len(headings) else len(nodes)
            title = self._heading_title(heading)
            body_text = " ".join(
                str(node).strip() for node in nodes[start + 1 : end] if _is_real_text(node) and str(node).strip()
            )
            sections.append((title, body_text))
        return sections
