"""Google Places API 래퍼 (2차 장소 상세 정보 수집)."""

import os

import requests

from date_planner.utils.logger import get_logger
from date_planner.utils.text_utils import strip_floor_info

logger = get_logger(__name__)

_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_DENIED_API_KEYS: set[str] = set()


def get_place_details(place_name: str, address: str) -> dict:
    """장소명과 주소로 Google Places 상세 정보를 조회한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소.

    Returns:
        place_id, opening_hours, 좌표를 포함한 dict. 에러 시 빈 dict.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        logger.warning("Google Places API 키 미설정 — 빈 결과 반환")
        return {}
    if api_key in _DENIED_API_KEYS:
        return {}

    try:
        place_id = _find_place_id(place_name, address, api_key)
        if not place_id:
            logger.debug("Place ID 없음: %s — 장소 상세 조회 건너뜀", place_name)
            return {}

        response = requests.get(
            _DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": "place_id,opening_hours,geometry",
                "key": api_key,
                "language": "ko",
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        if _handle_api_error(data, api_key, "상세 조회"):
            return {}
        result = data.get("result", {})
        location = result.get("geometry", {}).get("location", {})
        return {
            "place_id": result.get("place_id", ""),
            "opening_hours": result.get("opening_hours", {}),
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
    if api_key in _DENIED_API_KEYS:
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
        data = response.json()
        if _handle_api_error(data, api_key, "영업 여부 조회"):
            return True
        opening_hours = data.get("result", {}).get("opening_hours", {})
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
    if api_key in _DENIED_API_KEYS:
        return ""

    try:
        response = requests.get(
            _FIND_PLACE_URL,
            params={
                "input": query,
                "inputtype": "textquery",
                "fields": "place_id",
                "key": api_key,
                "language": "ko",
                "locationbias": "circle:20000@37.5665,126.9780",
            },
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        status = data.get("status", "")
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0].get("place_id", "")
        if _handle_api_error(data, api_key, "Place 검색"):
            return ""
        if status and status not in ("OK", "ZERO_RESULTS"):
            logger.warning("Place 검색 API 오류: query=%s status=%s", query, status)
        else:
            logger.debug("Place 검색 결과 없음: query=%s status=%s", query, status)
        return ""
    except requests.RequestException as e:
        logger.error("Place ID 검색 실패: %s", e)
        return ""


def _handle_api_error(data: dict, api_key: str, operation: str) -> bool:
    """Google Places 권한 오류를 기록하고 반복 호출을 차단한다."""
    status = data.get("status", "")
    if status != "REQUEST_DENIED":
        return False

    if api_key not in _DENIED_API_KEYS:
        error_message = data.get("error_message", "상세 오류 메시지 없음")
        logger.warning(
            "Google Places API REQUEST_DENIED: %s. "
            "Places API (Legacy) 활성화, 결제 계정, API 키 제한사항을 확인하세요. "
            "이번 실행에서는 Google Places 상세 보강을 건너뜁니다. error=%s",
            operation,
            error_message,
        )
        _DENIED_API_KEYS.add(api_key)
    return True
