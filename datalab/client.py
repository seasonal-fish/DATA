from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from common.config import settings
from common.logging_config import get_logger
from common.models import TrendPoint, TrendResult

logger = get_logger(__name__)

DATALAB_SEARCH_URL = "https://openapi.naver.com/v1/datalab/search"
MAX_KEYWORD_GROUPS = 5
MAX_KEYWORDS_PER_GROUP = 20
VALID_TIME_UNITS = {"date", "week", "month"}
VALID_DEVICES = {"pc", "mo"}
VALID_GENDERS = {"m", "f"}
VALID_AGES = {str(i) for i in range(1, 12)}


class NaverDataLabError(RuntimeError):
    """DataLab API가 200이 아닌 응답을 돌려줄 때 발생."""


class NaverDataLabClient:
    """네이버 데이터랩 검색어트렌드 API(POST /v1/datalab/search) 클라이언트.

    공식 REST API이므로 robots.txt/사이트 레이트리밋이 아니라 발급받은
    Client ID/Secret에 의한 API 자체 호출 한도를 따른다.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if client_id and client_secret:
            self._client_id, self._client_secret = client_id, client_secret
        else:
            self._client_id, self._client_secret = settings.require_naver_credentials()
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NaverDataLabClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    )
    def _post(self, payload: dict) -> dict:
        response = self._client.post(
            DATALAB_SEARCH_URL,
            json=payload,
            headers={
                "X-Naver-Client-Id": self._client_id,
                "X-Naver-Client-Secret": self._client_secret,
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()  # tenacity가 재시도하도록 예외를 던진다
        if response.status_code != 200:
            raise NaverDataLabError(f"DataLab API 오류 {response.status_code}: {response.text}")
        return response.json()

    def search_trend(
        self,
        keyword_groups: list[dict],
        start_date: str,
        end_date: str,
        time_unit: str = "date",
        device: str | None = None,
        gender: str | None = None,
        ages: list[str] | None = None,
    ) -> list[TrendResult]:
        """검색어 그룹별 트렌드를 조회한다.

        keyword_groups 예시: [{"groupName": "키워드A", "keywords": ["키워드A", "동의어"]}]
        """
        self._validate(keyword_groups, time_unit, device, gender, ages)

        payload: dict = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups,
        }
        if device:
            payload["device"] = device
        if gender:
            payload["gender"] = gender
        if ages:
            payload["ages"] = ages

        logger.info("DataLab 트렌드 조회: %s ~ %s, %d개 그룹", start_date, end_date, len(keyword_groups))
        data = self._post(payload)

        results: list[TrendResult] = []
        for item in data.get("results", []):
            points = [TrendPoint(period=p["period"], ratio=p["ratio"]) for p in item.get("data", [])]
            results.append(
                TrendResult(
                    keyword_group=item["title"],
                    keywords=item.get("keywords", []),
                    start_date=data["startDate"],
                    end_date=data["endDate"],
                    time_unit=data["timeUnit"],
                    points=points,
                )
            )
        return results

    @staticmethod
    def _validate(
        keyword_groups: list[dict],
        time_unit: str,
        device: str | None,
        gender: str | None,
        ages: list[str] | None,
    ) -> None:
        if not keyword_groups:
            raise ValueError("keyword_groups는 최소 1개 이상이어야 합니다.")
        if len(keyword_groups) > MAX_KEYWORD_GROUPS:
            raise ValueError(f"keywordGroups는 최대 {MAX_KEYWORD_GROUPS}개까지 허용됩니다.")
        for group in keyword_groups:
            if "groupName" not in group or "keywords" not in group:
                raise ValueError("각 keyword group은 groupName, keywords 필드를 가져야 합니다.")
            if not (1 <= len(group["keywords"]) <= MAX_KEYWORDS_PER_GROUP):
                raise ValueError(
                    f"keywords는 그룹당 1~{MAX_KEYWORDS_PER_GROUP}개여야 합니다: {group['groupName']}"
                )
        if time_unit not in VALID_TIME_UNITS:
            raise ValueError(f"time_unit은 {VALID_TIME_UNITS} 중 하나여야 합니다.")
        if device and device not in VALID_DEVICES:
            raise ValueError(f"device는 {VALID_DEVICES} 중 하나여야 합니다.")
        if gender and gender not in VALID_GENDERS:
            raise ValueError(f"gender는 {VALID_GENDERS} 중 하나여야 합니다.")
        if ages and not set(ages) <= VALID_AGES:
            raise ValueError(f"ages는 {sorted(VALID_AGES)} 중에서 선택해야 합니다.")
