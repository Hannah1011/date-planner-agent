"""네이버 검색 API 래퍼 (1차 장소 목록 수집).

USE_MOCK=true 환경 변수가 설정된 경우 고정 Mock 응답을 반환한다.
"""

import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_API_URL = "https://openapi.naver.com/v1/search/local.json"
_MOCK_PLACES = [
    {
        "name": "연남동 파스타집",
        "address": "서울 마포구 연남동 123-4",
        "category": "음식점>이탈리안",
        "link": "https://example.com/pasta",
    },
    {
        "name": "상수 감성 카페",
        "address": "서울 마포구 상수동 56-7",
        "category": "카페>커피전문점",
        "link": "https://example.com/cafe",
    },
    {
        "name": "홍대 한강뷰 레스토랑",
        "address": "서울 마포구 서교동 89-1",
        "category": "음식점>양식",
        "link": "https://example.com/restaurant",
    },
    {
        "name": "연트럴파크 피크닉존",
        "address": "서울 마포구 연남동 공원로 2",
        "category": "관광>공원",
        "link": "https://example.com/park",
    },
    {
        "name": "망원시장 먹거리골목",
        "address": "서울 마포구 망원동 434",
        "category": "음식점>한식",
        "link": "https://example.com/market",
    },
]


def search_places(query: str, display: int = 5) -> list[dict]:
    """장소명 또는 키워드로 네이버 지역 검색을 수행한다.

    Args:
        query: 검색 쿼리 (예: "마포구 파스타맛집").
        display: 반환할 결과 수. 최대 5.

    Returns:
        장소 정보 dict 리스트. 각 항목은 name, address, category, link 키를 포함.
        에러 시 빈 리스트.
    """
    if _use_mock():
        logger.debug("네이버 검색 Mock 응답 반환: query=%s", query)
        return _MOCK_PLACES[:display]

    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("네이버 API 키 미설정 — 빈 결과 반환")
        return []

    try:
        response = requests.get(
            _API_URL,
            params={"query": query, "display": display},
            headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
            timeout=5,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        return [
            {
                "name": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "address": item.get("roadAddress") or item.get("address", ""),
                "category": item.get("category", ""),
                "link": item.get("link", ""),
            }
            for item in items
        ]
    except requests.RequestException as e:
        logger.error("네이버 검색 API 호출 실패: %s", e)
        return []


def _use_mock() -> bool:
    """USE_MOCK 환경 변수가 'true'로 설정되어 있으면 True를 반환한다."""
    return os.getenv("USE_MOCK", "true").lower() == "true"
