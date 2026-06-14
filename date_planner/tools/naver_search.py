"""네이버 검색 API 래퍼 (1차 장소 목록 수집)."""

from html import unescape
import os

import requests

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_API_URL = "https://openapi.naver.com/v1/search/local.json"


def search_places(query: str, display: int = 5) -> list[dict]:
    """장소명 또는 키워드로 네이버 지역 검색을 수행한다.

    Args:
        query: 검색 쿼리 (예: "마포구 파스타맛집").
        display: 반환할 결과 수. 최대 5.

    Returns:
        장소 정보 dict 리스트. 각 항목은 name, address, category, link 키를 포함.
        에러 시 빈 리스트.
    """
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
        results = []
        for item in items:
            # mapx/mapy는 WGS84 좌표를 1e7 배 한 정수값
            try:
                lat = int(item.get("mapy", 0)) / 1e7
                lon = int(item.get("mapx", 0)) / 1e7
            except (ValueError, TypeError):
                lat, lon = 0.0, 0.0
            results.append({
                "name": unescape(item.get("title", "").replace("<b>", "").replace("</b>", "")),
                "address": item.get("roadAddress") or item.get("address", ""),
                "category": item.get("category", ""),
                "link": item.get("link", ""),
                "lat": lat,
                "lon": lon,
            })
        return results
    except requests.RequestException as e:
        logger.error("네이버 검색 API 호출 실패: %s", e)
        return []


def search_place_suggestions(query: str, limit: int = 20) -> list[dict]:
    """장소명 일부나 지역 키워드로 관련성 높은 장소 추천을 반환한다."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    queries = [cleaned_query]
    if " " not in cleaned_query and not cleaned_query.endswith("역"):
        queries.append(f"{cleaned_query}역")

    by_name: dict[str, dict] = {}
    for search_query in queries:
        for item in search_places(search_query, display=5):
            name = item.get("name", "")
            if name and name not in by_name:
                by_name[name] = {
                    "name": name,
                    "address": item.get("address", ""),
                }

    suggestions = list(by_name.values())
    suggestions.sort(
        key=lambda item: (
            cleaned_query not in item["name"],
            cleaned_query not in item["address"],
            item["name"],
        )
    )
    return suggestions[:limit]
