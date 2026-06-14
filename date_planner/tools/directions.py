"""Google Directions API 래퍼 (대중교통 이동 시간 계산)."""

import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def get_transit_duration(origin: str, destination: str) -> int:
    """두 장소 간 대중교통 이동 시간(분)을 반환한다.

    Args:
        origin: 출발지 주소 또는 장소명.
        destination: 도착지 주소 또는 장소명.

    Returns:
        이동 시간(분). 에러 시 -1.
    """
    api_key = os.getenv("GOOGLE_DIRECTIONS_API_KEY", "")
    if not api_key:
        logger.warning("Google Directions API 키 미설정 — -1 반환")
        return -1

    try:
        response = requests.get(
            _DIRECTIONS_URL,
            params={
                "origin": origin,
                "destination": destination,
                "mode": "transit",
                "language": "ko",
                "key": api_key,
            },
            timeout=5,
        )
        response.raise_for_status()
        return _parse_duration(response.json())
    except requests.RequestException as e:
        logger.error("Directions API 호출 실패: %s", e)
        return -1


def _parse_duration(data: dict) -> int:
    """Directions API 응답에서 총 이동 시간(분)을 추출한다.

    Args:
        data: API 응답 JSON.

    Returns:
        이동 시간(분). 파싱 실패 시 -1.
    """
    try:
        routes = data.get("routes", [])
        if not routes:
            logger.warning("Directions API 응답에 경로 없음")
            return -1
        legs = routes[0].get("legs", [])
        if not legs:
            return -1
        duration_seconds = legs[0].get("duration", {}).get("value", 0)
        return max(1, duration_seconds // 60)
    except (KeyError, IndexError, TypeError) as e:
        logger.error("이동 시간 파싱 실패: %s", e)
        return -1
