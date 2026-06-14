"""Google Directions API 래퍼 (대중교통 이동 시간 계산)."""

import os

import requests

from date_planner.utils.logger import get_logger
from date_planner.utils.text_utils import strip_floor_info

logger = get_logger(__name__)

_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def get_transit_duration(origin: str, destination: str) -> int:
    """두 장소 간 이동 시간(분)을 반환한다.

    대중교통(transit) 경로를 먼저 시도하고, 경로가 없으면 도보(walking)로 재시도한다.
    주소의 층/호 정보는 API 호출 전에 제거한다.

    Args:
        origin: 출발지 주소.
        destination: 도착지 주소.

    Returns:
        이동 시간(분). 에러 또는 경로 없음 시 -1.
    """
    api_key = os.getenv("GOOGLE_DIRECTIONS_API_KEY", "")
    if not api_key:
        logger.warning("Google Directions API 키 미설정 — -1 반환")
        return -1

    clean_origin = strip_floor_info(origin)
    clean_dest = strip_floor_info(destination)

    # 대중교통 먼저 시도
    result = _request_directions(clean_origin, clean_dest, "transit", api_key)
    if result != -1:
        return result

    # 단거리/경로 없음 → 도보로 재시도
    logger.debug("transit 경로 없음, walking 모드로 재시도: %s → %s", clean_origin, clean_dest)
    return _request_directions(clean_origin, clean_dest, "walking", api_key)


def _request_directions(origin: str, destination: str, mode: str, api_key: str) -> int:
    """Directions API를 호출해 이동 시간(분)을 반환한다.

    Args:
        origin: 출발지 주소.
        destination: 도착지 주소.
        mode: 이동 수단 ("transit" 또는 "walking").
        api_key: Google Directions API 키.

    Returns:
        이동 시간(분). 에러 또는 경로 없음 시 -1.
    """
    try:
        response = requests.get(
            _DIRECTIONS_URL,
            params={
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "language": "ko",
                "key": api_key,
            },
            timeout=5,
        )
        response.raise_for_status()
        return _parse_duration(response.json(), mode)
    except requests.RequestException as e:
        logger.error("Directions API 호출 실패 (mode=%s): %s", mode, e)
        return -1


def _parse_duration(data: dict, mode: str) -> int:
    """Directions API 응답에서 총 이동 시간(분)을 추출한다.

    Args:
        data: API 응답 JSON.
        mode: 이동 수단 (로깅 용도).

    Returns:
        이동 시간(분). 파싱 실패 또는 경로 없음 시 -1.
    """
    try:
        status = data.get("status", "UNKNOWN")
        routes = data.get("routes", [])
        if not routes:
            logger.warning("Directions 경로 없음 (mode=%s, status=%s)", mode, status)
            return -1
        legs = routes[0].get("legs", [])
        if not legs:
            return -1
        duration_seconds = legs[0].get("duration", {}).get("value", 0)
        return max(1, duration_seconds // 60)
    except (KeyError, IndexError, TypeError) as e:
        logger.error("이동 시간 파싱 실패: %s", e)
        return -1
