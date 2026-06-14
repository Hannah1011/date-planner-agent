"""OpenWeatherMap API 래퍼 (날씨 정보 조회).

USE_MOCK=true 환경 변수가 설정된 경우 고정 Mock 응답을 반환한다.
"""

import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# 서울 각 구의 대표 좌표 (위도, 경도)
_DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "강남구": (37.5172, 127.0473),
    "강동구": (37.5301, 127.1238),
    "강북구": (37.6396, 127.0255),
    "강서구": (37.5509, 126.8496),
    "관악구": (37.4784, 126.9516),
    "광진구": (37.5385, 127.0823),
    "구로구": (37.4954, 126.8874),
    "금천구": (37.4570, 126.8954),
    "노원구": (37.6542, 127.0568),
    "도봉구": (37.6688, 127.0471),
    "동대문구": (37.5744, 127.0395),
    "동작구": (37.5124, 126.9393),
    "마포구": (37.5663, 126.9014),
    "서대문구": (37.5791, 126.9368),
    "서초구": (37.4837, 127.0324),
    "성동구": (37.5636, 127.0369),
    "성북구": (37.5894, 127.0167),
    "송파구": (37.5145, 127.1059),
    "양천구": (37.5170, 126.8665),
    "영등포구": (37.5264, 126.8963),
    "용산구": (37.5311, 126.9810),
    "은평구": (37.6027, 126.9291),
    "종로구": (37.5735, 126.9790),
    "중구": (37.5641, 126.9979),
    "중랑구": (37.6063, 127.0927),
}

_MOCK_WEATHER = {
    "condition": "맑음",
    "temperature": 22.0,
    "precipitation_probability": 10,
}


def get_weather(district: str, date: str) -> dict:
    """특정 구의 날씨 정보를 조회한다.

    Args:
        district: 서울 구 이름 (예: "마포구").
        date: 조회 날짜 (YYYY-MM-DD 형식).

    Returns:
        condition, temperature, precipitation_probability 를 포함한 dict.
        에러 시 빈 dict.
    """
    if _use_mock():
        logger.debug("날씨 Mock 반환: district=%s date=%s", district, date)
        return dict(_MOCK_WEATHER)

    api_key = os.getenv("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        logger.warning("OpenWeatherMap API 키 미설정 — 빈 결과 반환")
        return {}

    coords = _DISTRICT_COORDS.get(district)
    if not coords:
        logger.warning("알 수 없는 구 이름: %s — 빈 결과 반환", district)
        return {}

    lat, lon = coords
    try:
        response = requests.get(
            _FORECAST_URL,
            params={
                "lat": lat,
                "lon": lon,
                "appid": api_key,
                "units": "metric",
                "lang": "kr",
                "cnt": 8,
            },
            timeout=5,
        )
        response.raise_for_status()
        return _parse_forecast(response.json(), date)
    except requests.RequestException as e:
        logger.error("날씨 API 호출 실패: %s", e)
        return {}


def _parse_forecast(data: dict, target_date: str) -> dict:
    """OpenWeatherMap API 응답에서 대상 날짜의 날씨를 추출한다.

    Args:
        data: API 응답 JSON.
        target_date: 조회 날짜 (YYYY-MM-DD).

    Returns:
        condition, temperature, precipitation_probability 를 포함한 dict.
        해당 날짜 데이터가 없으면 빈 dict.
    """
    for item in data.get("list", []):
        if item.get("dt_txt", "").startswith(target_date):
            weather_list = item.get("weather", [{}])
            description = weather_list[0].get("description", "") if weather_list else ""
            temp = item.get("main", {}).get("temp", 0.0)
            pop = int(item.get("pop", 0) * 100)
            return {
                "condition": description,
                "temperature": round(temp, 1),
                "precipitation_probability": pop,
            }
    logger.warning("날씨 데이터에서 날짜를 찾지 못함: %s", target_date)
    return {}


def _use_mock() -> bool:
    """USE_MOCK 환경 변수가 'true'로 설정되어 있으면 True를 반환한다."""
    return os.getenv("USE_MOCK", "true").lower() == "true"
