"""Google Places API 래퍼 (2차 장소 상세 정보 수집).

USE_MOCK=true 환경 변수가 설정된 경우 고정 Mock 응답을 반환한다.
"""

import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

_MOCK_DETAILS = {
    "place_id": "mock_place_id_001",
    "rating": 4.2,
    "price_level": 2,
    "opening_hours": {
        "open_now": True,
        "periods": [
            {"open": {"day": 1, "time": "1000"}, "close": {"day": 1, "time": "2200"}},
            {"open": {"day": 2, "time": "1000"}, "close": {"day": 2, "time": "2200"}},
            {"open": {"day": 3, "time": "1000"}, "close": {"day": 3, "time": "2200"}},
            {"open": {"day": 4, "time": "1000"}, "close": {"day": 4, "time": "2200"}},
            {"open": {"day": 5, "time": "1000"}, "close": {"day": 5, "time": "2200"}},
            {"open": {"day": 6, "time": "1100"}, "close": {"day": 6, "time": "2300"}},
            {"open": {"day": 0, "time": "1100"}, "close": {"day": 0, "time": "2100"}},
        ],
        "weekday_text": [
            "월요일: 오전 10:00 – 오후 10:00",
            "화요일: 오전 10:00 – 오후 10:00",
            "수요일: 오전 10:00 – 오후 10:00",
            "목요일: 오전 10:00 – 오후 10:00",
            "금요일: 오전 10:00 – 오후 10:00",
            "토요일: 오전 11:00 – 오후 11:00",
            "일요일: 오전 11:00 – 오후 9:00",
        ],
    },
    "reviews": [
        {"rating": 5, "text": "분위기도 좋고 음식도 맛있어요!"},
        {"rating": 4, "text": "주말에 웨이팅이 있지만 기다릴 만해요."},
    ],
}


def get_place_details(place_name: str, address: str) -> dict:
    """장소명과 주소로 Google Places 상세 정보를 조회한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소.

    Returns:
        place_id, rating, price_level, opening_hours, reviews 를 포함한 dict.
        에러 시 빈 dict.
    """
    if _use_mock():
        logger.debug("Google Places 상세 정보 Mock 반환: %s", place_name)
        return dict(_MOCK_DETAILS)

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.warning("Google Places API 키 미설정 — 빈 결과 반환")
        return {}

    try:
        place_id = _find_place_id(place_name, address, api_key)
        if not place_id:
            return {}

        response = requests.get(
            _DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": "place_id,rating,price_level,opening_hours,reviews",
                "key": api_key,
                "language": "ko",
            },
            timeout=5,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        return {
            "place_id": result.get("place_id", ""),
            "rating": result.get("rating", 0.0),
            "price_level": result.get("price_level", 0),
            "opening_hours": result.get("opening_hours", {}),
            "reviews": result.get("reviews", []),
        }
    except requests.RequestException as e:
        logger.error("Google Places 상세 조회 실패: %s", e)
        return {}


def is_place_open_now(place_id: str) -> bool:
    """현재 영업 중인지 여부를 반환한다.

    Args:
        place_id: Google Place ID.

    Returns:
        영업 중이면 True, 아니면 False. 에러 시 True(보수적 기본값).
    """
    if _use_mock():
        logger.debug("is_place_open_now Mock 반환: True")
        return True

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.warning("Google Places API 키 미설정 — 기본값 True 반환")
        return True

    try:
        response = requests.get(
            _DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": "opening_hours",
                "key": api_key,
            },
            timeout=5,
        )
        response.raise_for_status()
        opening_hours = response.json().get("result", {}).get("opening_hours", {})
        return bool(opening_hours.get("open_now", True))
    except requests.RequestException as e:
        logger.error("영업 여부 조회 실패: %s — 기본값 True 반환", e)
        return True


def _find_place_id(place_name: str, address: str, api_key: str) -> str:
    """장소명과 주소로 Google Place ID를 검색한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소.
        api_key: Google Places API 키.

    Returns:
        Place ID 문자열. 찾지 못하면 빈 문자열.
    """
    try:
        response = requests.get(
            _FIND_PLACE_URL,
            params={
                "input": f"{place_name} {address}",
                "inputtype": "textquery",
                "fields": "place_id",
                "key": api_key,
                "language": "ko",
            },
            timeout=5,
        )
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
        return candidates[0].get("place_id", "") if candidates else ""
    except requests.RequestException as e:
        logger.error("Place ID 검색 실패: %s", e)
        return ""


def _use_mock() -> bool:
    """USE_MOCK 환경 변수가 'true'로 설정되어 있으면 True를 반환한다."""
    return os.getenv("USE_MOCK", "true").lower() == "true"
