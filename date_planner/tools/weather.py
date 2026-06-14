"""OpenWeatherMap API 래퍼 (날씨 정보 조회)."""

import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# OpenWeatherMap은 관측소 기반이라 서울 내 구 단위 구분이 불가능하다.
# 서울 시청 좌표를 기준으로 단일 쿼리를 수행한다.
_SEOUL_LAT = 37.5665
_SEOUL_LON = 126.9780


def get_weather(district: str, date: str) -> dict:
    """특정 구의 날씨 정보를 조회한다.

    Args:
        district: 서울 구 이름 (예: "마포구").
        date: 조회 날짜 (YYYY-MM-DD 형식).

    Returns:
        condition, temperature, precipitation_probability 를 포함한 dict.
        에러 시 빈 dict.
    """
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
