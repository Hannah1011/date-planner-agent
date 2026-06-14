"""Google Places API 래퍼 (2차 장소 상세 정보 수집)."""

import os

import requests

from date_planner.utils.logger import get_logger
from date_planner.utils.text_utils import strip_floor_info

logger = get_logger(__name__)

_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def get_place_details(place_name: str, address: str) -> dict:
    """장소명과 주소로 Google Places 상세 정보를 조회한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소.

    Returns:
        place_id, rating, price_level, opening_hours, reviews 를 포함한 dict.
        에러 시 빈 dict.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.warning("Google Places API 키 미설정 — 빈 결과 반환")
        return {}

    try:
        place_id = _find_place_id(place_name, address, api_key)
        if not place_id:
            logger.debug("Place ID 없음: %s — 별점/가격 정보 조회 건너뜀", place_name)
            return {}

        response = requests.get(
            _DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": "place_id,rating,price_level,opening_hours,reviews,geometry",
                "key": api_key,
                "language": "ko",
            },
            timeout=5,
        )
        response.raise_for_status()
        result = response.json().get("result", {})
        location = result.get("geometry", {}).get("location", {})
        return {
            "place_id": result.get("place_id", ""),
            "rating": result.get("rating", 0.0),
            "price_level": result.get("price_level", 0),
            "opening_hours": result.get("opening_hours", {}),
            "reviews": result.get("reviews", []),
            "lat": location.get("lat", 0.0),
            "lon": location.get("lng", 0.0),
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

    층/호 정보를 제거한 주소로 먼저 시도하고, 실패하면 장소명만으로 재시도한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소 (층/호 포함 가능).
        api_key: Google Places API 키.

    Returns:
        Place ID 문자열. 찾지 못하면 빈 문자열.
    """
    clean_address = strip_floor_info(address)

    # 1차: 이름 + 층 제거 주소
    place_id = _search_place(f"{place_name} {clean_address}", api_key)
    if place_id:
        return place_id

    # 2차 폴백: 이름만
    logger.debug("이름+주소 검색 실패, 이름만으로 재시도: %s", place_name)
    return _search_place(place_name, api_key)


def _search_place(query: str, api_key: str) -> str:
    """단일 텍스트 쿼리로 Google Place ID를 검색한다.

    Args:
        query: 검색할 텍스트 (장소명 또는 장소명+주소).
        api_key: Google Places API 키.

    Returns:
        Place ID 문자열. 없으면 빈 문자열.
    """
    try:
        response = requests.get(
            _FIND_PLACE_URL,
            params={
                "input": query,
                "inputtype": "textquery",
                "fields": "place_id",
                "key": api_key,
                "language": "ko",
            },
            timeout=5,
        )
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
        if not candidates:
            logger.debug("Place 검색 결과 없음: %s", query)
            return ""
        return candidates[0].get("place_id", "")
    except requests.RequestException as e:
        logger.error("Place ID 검색 실패: %s", e)
        return ""
