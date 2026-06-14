"""서울 구 단위 지도 선택기 (Folium + GeoJSON).

구 클릭 시 구 이름을 반환한다.
Folium 렌더링 실패 시 selectbox fallback을 제공한다.
"""

import json
from pathlib import Path
from typing import Optional

import streamlit as st

from date_planner.config.constants import SEOUL_DISTRICTS
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_GEOJSON_PATH = Path(__file__).resolve().parents[2] / "date_planner" / "data" / "seoul_districts.geojson"
_DEFAULT_MAP_CENTER = [37.5665, 126.9780]
_DEFAULT_ZOOM = 11


def render_district_selector() -> Optional[str]:
    """서울 구 선택 UI를 렌더링하고 선택된 구 이름을 반환한다.

    GeoJSON 파일이 존재하면 Folium 지도로 렌더링하고,
    없으면 selectbox fallback을 표시한다.

    Returns:
        선택된 구 이름 문자열, 미선택 시 None.
    """
    if _GEOJSON_PATH.exists():
        return _render_folium_map()
    else:
        logger.warning("GeoJSON 파일 없음 — selectbox fallback 사용: %s", _GEOJSON_PATH)
        return _render_selectbox_fallback()


def _render_folium_map() -> Optional[str]:
    """Folium Choropleth 지도로 구 선택 UI를 렌더링한다.

    Returns:
        선택된 구 이름, 실패 또는 미선택 시 None.
    """
    try:
        import folium
        from streamlit_folium import st_folium

        with open(_GEOJSON_PATH, encoding="utf-8") as f:
            geojson_data = json.load(f)

        m = folium.Map(location=_DEFAULT_MAP_CENTER, zoom_start=_DEFAULT_ZOOM, tiles="CartoDB positron")

        folium.GeoJson(
            geojson_data,
            name="서울 구 경계",
            style_function=lambda _: {
                "fillColor": "#3186cc",
                "color": "white",
                "weight": 1.5,
                "fillOpacity": 0.4,
            },
            highlight_function=lambda _: {
                "fillColor": "#e63946",
                "color": "white",
                "weight": 2,
                "fillOpacity": 0.7,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["name"],
                aliases=["구 이름:"],
                localize=True,
            ),
        ).add_to(m)

        map_data = st_folium(m, width=700, height=450, returned_objects=["last_clicked"])

        if map_data and map_data.get("last_clicked"):
            clicked_lat = map_data["last_clicked"].get("lat")
            clicked_lng = map_data["last_clicked"].get("lng")
            district = _find_district_by_coords(geojson_data, clicked_lat, clicked_lng)
            if district:
                return district

        return None

    except Exception as e:
        logger.error("Folium 지도 렌더링 실패: %s — selectbox fallback 사용", e)
        return _render_selectbox_fallback()


def _render_selectbox_fallback() -> Optional[str]:
    """selectbox로 구 선택 fallback UI를 렌더링한다.

    Returns:
        선택된 구 이름, 또는 미선택(첫 번째 placeholder) 시 None.
    """
    options = ["구를 선택해 주세요"] + SEOUL_DISTRICTS
    selected = st.selectbox("지역 (서울 구)", options=options, index=0)
    if selected == "구를 선택해 주세요":
        return None
    return selected


def _find_district_by_coords(
    geojson_data: dict,
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[str]:
    """GeoJSON 데이터에서 위경도 좌표에 해당하는 구 이름을 찾는다.

    shapely 없이 GeoJSON feature의 properties에서 구 이름을 직접 추출한다.
    정확한 포함 여부 계산 대신, 클릭 좌표와 가장 가까운 구 centroid를 반환한다.

    Args:
        geojson_data: 서울 GeoJSON dict.
        lat: 클릭 위도.
        lng: 클릭 경도.

    Returns:
        구 이름 문자열, 찾지 못하면 None.
    """
    if lat is None or lng is None:
        return None

    try:
        best_name = None
        best_dist = float("inf")

        for feature in geojson_data.get("features", []):
            props = feature.get("properties", {})
            name = props.get("name", "")
            if not name:
                continue

            centroid = _calc_centroid(feature.get("geometry", {}))
            if centroid is None:
                continue

            dist = (centroid[0] - lat) ** 2 + (centroid[1] - lng) ** 2
            if dist < best_dist:
                best_dist = dist
                best_name = name

        return best_name
    except Exception as e:
        logger.error("구 좌표 매핑 실패: %s", e)
        return None


def _calc_centroid(geometry: dict) -> Optional[tuple[float, float]]:
    """GeoJSON geometry에서 단순 중심 좌표를 계산한다.

    Args:
        geometry: GeoJSON geometry dict (Polygon 또는 MultiPolygon).

    Returns:
        (lat, lng) 튜플, 실패 시 None.
    """
    try:
        geo_type = geometry.get("type", "")
        coordinates = geometry.get("coordinates", [])

        if geo_type == "Polygon":
            ring = coordinates[0]
        elif geo_type == "MultiPolygon":
            ring = coordinates[0][0]
        else:
            return None

        lngs = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return (sum(lats) / len(lats), sum(lngs) / len(lngs))
    except (IndexError, ZeroDivisionError):
        return None
