"""Google Directions API 래퍼 (대중교통 이동 시간 계산).

USE_MOCK=true 환경 변수가 설정된 경우 결정론적 Mock 값을 반환한다.
"""

import hashlib
import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_MOCK_MIN_MINUTES = 15
_MOCK_MAX_MINUTES = 45


def get_transit_duration(origin: str, destination: str) -> int:
    """두 장소 간 대중교통 이동 시간(분)을 반환한다.

    Args:
        origin: 출발지 주소 또는 장소명.
        destination: 도착지 주소 또는 장소명.

    Returns:
        이동 시간(분). 에러 시 -1.
    """
    if _use_mock():
        minutes = _deterministic_mock_minutes(origin, destination)
        logger.debug("대중교통 이동 시간 Mock 반환: %s -> %s = %d분", origin, destination, minutes)
        return minutes

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


def _deterministic_mock_minutes(origin: str, destination: str) -> int:
    """출발지와 목적지 문자열로부터 결정론적 Mock 이동 시간을 계산한다.

    동일한 입력에 대해 항상 같은 값을 반환하도록 해시를 사용한다.

    Args:
        origin: 출발지 문자열.
        destination: 도착지 문자열.

    Returns:
        MOCK_MIN_MINUTES ~ MOCK_MAX_MINUTES 범위 내 정수(분).
    """
    key = f"{origin}|{destination}"
    hash_int = int(hashlib.md5(key.encode()).hexdigest(), 16)
    span = _MOCK_MAX_MINUTES - _MOCK_MIN_MINUTES
    return _MOCK_MIN_MINUTES + (hash_int % (span + 1))


def _use_mock() -> bool:
    """USE_MOCK 환경 변수가 'true'로 설정되어 있으면 True를 반환한다."""
    return os.getenv("USE_MOCK", "true").lower() == "true"
