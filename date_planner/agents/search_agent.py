"""Search Agent: 선택 무드별 병렬 장소 검색 및 상세 정보 보강.

Tool Use + Routing + Parallelization 패턴.

검색 전략:
- 음식(food): 맛있는 거 탐방 선택 시 food_preferences 또는 무드 기반 맛집
- 카페(cafe): 느긋한 카페 투어 선택 시 cafe_style 기반 카페
- 액티비티(activity): 선택된 무드별 액티비티
선택하지 않은 음식·카페 무드의 상세 조건은 검색에 반영하지 않는다.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from date_planner.agents.models import PlaceCandidate, UserRequest
from date_planner.config.constants import CafeStyle, Mood, SEOUL_DISTRICTS
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.tools.google_places import get_place_details, is_place_open_now
from date_planner.tools.naver_search import search_places
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "search"
_MAX_WORKERS = 4

# 카페 스타일별 검색 쿼리
_CAFE_STYLE_QUERIES: dict[CafeStyle, str] = {
    CafeStyle.COZY: "감성 카페",
    CafeStyle.QUIET: "조용한 카페",
    CafeStyle.LUXURY: "루프탑 카페",
    CafeStyle.FRANCHISE: "카페",
}

# 무드별 검색어와 장소 타입. 복수 검색어로 결과 부족 가능성을 낮춘다.
_MOOD_QUERIES: dict[Mood, list[tuple[str, str]]] = {
    Mood.NATURE_HEALING: [("공원", "activity"), ("한강", "activity")],
    Mood.FOOD_EXPLORATION: [("맛집", "food"), ("레스토랑", "food")],
    Mood.NEW_ACTIVITY: [("팝업스토어", "activity"), ("전시회", "activity")],
    Mood.COZY_CAFE: [("디저트카페", "cafe"), ("베이커리카페", "cafe")],
    Mood.SHOPPING_STREET: [("편집샵", "activity"), ("쇼핑몰", "activity")],
}

_FOOD_CATEGORY_KEYWORDS = (
    "음식", "식당", "레스토랑", "맛집", "한식", "양식", "중식", "일식",
    "분식", "고기", "돈가스", "브런치", "술집",
)
_CAFE_CATEGORY_KEYWORDS = ("카페", "커피", "디저트", "베이커리", "티룸")


def search_candidates(request: UserRequest) -> list[PlaceCandidate]:
    """사용자 요청 조건에 맞는 장소 후보를 병렬 검색으로 수집한다.

    선택된 각 무드와 관련 상세 조건에 맞는 쿼리를 검색한다.

    Args:
        request: 구조화된 사용자 요청.

    Returns:
        PlaceCandidate 리스트. 에러 시 빈 리스트.
    """
    return _search_queries(_build_queries(request))


def search_replan_candidates(
    request: UserRequest,
    search_keywords: list[str],
) -> list[PlaceCandidate]:
    """피드백에서 추출한 키워드로 새로운 장소 후보를 검색한다."""
    keywords = search_keywords or _default_replan_keywords(request)
    queries = [
        (
            f"{request.district} {keyword}",
            _infer_keyword_type(keyword),
            _infer_keyword_mood(keyword, request),
        )
        for keyword in keywords[:5]
    ]
    return _search_queries(queries)


def _search_queries(queries: list[tuple[str, str, str]]) -> list[PlaceCandidate]:
    """검색 쿼리 목록을 병렬 실행하고 후보를 보강한다."""
    logger.debug("검색 쿼리: %s", queries)

    raw_results: list[tuple[dict, str, str]] = []
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(search_places, query, 5): (query, cat_type, mood_tag)
                for query, cat_type, mood_tag in queries
            }
            for future in as_completed(futures):
                query, cat_type, mood_tag = futures[future]
                try:
                    results = future.result()
                    for r in results:
                        if _matches_query_district(query, r.get("address", "")):
                            raw_results.append((r, cat_type, mood_tag))
                    logger.debug("검색 완료: query=%s results=%d건", query, len(results))
                except Exception as e:
                    logger.error("검색 스레드 실패: query=%s error=%s", query, e)
    except Exception as e:
        logger.error("병렬 검색 실행 실패: %s", e)
        return []

    return _enrich_candidates(raw_results)


def _matches_query_district(query: str, address: str) -> bool:
    """주소에 다른 서울 구가 명시된 결과를 후보에서 제외한다."""
    requested_district = next(
        (district for district in SEOUL_DISTRICTS if district in query),
        "",
    )
    if not requested_district or not address:
        return True

    address_district = next(
        (district for district in SEOUL_DISTRICTS if district in address),
        "",
    )
    if address_district and address_district != requested_district:
        logger.debug(
            "선택 지역 밖 검색 결과 제외: requested=%s address=%s",
            requested_district,
            address,
        )
        return False
    return True


def _default_replan_keywords(request: UserRequest) -> list[str]:
    """구체적인 대체 요구가 없을 때 선택 무드의 다른 후보를 찾는다."""
    return [
        keyword
        for mood in request.moods
        for keyword, _ in _MOOD_QUERIES.get(mood, [])
    ]


def _infer_keyword_type(keyword: str) -> str:
    if any(value in keyword for value in ("맛집", "음식", "식당", "레스토랑")):
        return "food"
    if any(value in keyword for value in ("카페", "디저트", "베이커리")):
        return "cafe"
    return "activity"


def _infer_keyword_mood(keyword: str, request: UserRequest) -> str:
    if any(value in keyword for value in ("산", "등산", "둘레길", "공원", "한강")):
        return Mood.NATURE_HEALING.value
    if _infer_keyword_type(keyword) == "food":
        return Mood.FOOD_EXPLORATION.value
    if _infer_keyword_type(keyword) == "cafe":
        return Mood.COZY_CAFE.value
    return request.moods[0].value if request.moods else Mood.NEW_ACTIVITY.value


def _build_queries(request: UserRequest) -> list[tuple[str, str, str]]:
    """(검색 쿼리, 카테고리 타입, 무드 태그) 튜플 리스트를 반환한다.

    카테고리 타입: "food" | "cafe" | "activity"

    Args:
        request: 사용자 요청.

    Returns:
        (쿼리 문자열, 카테고리 타입) 튜플 리스트.
    """
    district = request.district
    queries: list[tuple[str, str, str]] = []

    has_food_mood = Mood.FOOD_EXPLORATION in request.moods
    has_cafe_mood = Mood.COZY_CAFE in request.moods

    if has_food_mood:
        if request.food_preferences:
            for pref in request.food_preferences[:2]:
                queries.append((f"{district} {pref}", "food", Mood.FOOD_EXPLORATION.value))
        else:
            queries.append((f"{district} 음식점 맛집", "food", Mood.FOOD_EXPLORATION.value))
    elif has_cafe_mood and request.food_preferences:
        for pref in request.food_preferences[:2]:
            queries.append((f"{district} {pref} 카페", "cafe", Mood.COZY_CAFE.value))

    if has_cafe_mood:
        cafe_query = _CAFE_STYLE_QUERIES.get(request.cafe_style, "카페")
        queries.append((f"{district} {cafe_query}", "cafe", Mood.COZY_CAFE.value))

    # 선택 무드별 검색. 팝업/전시 및 쇼핑 후보도 각각 별도 검색한다.
    seen: set[tuple[str, str]] = set()
    for mood in request.moods:
        for keyword, cat_type in _MOOD_QUERIES.get(mood, []):
            key = (keyword, cat_type)
            if key not in seen:
                queries.append((f"{district} {keyword}", cat_type, mood.value))
                seen.add(key)

    return queries[:12]


def _enrich_candidates(raw_results: list[tuple[dict, str, str]]) -> list[PlaceCandidate]:
    """Naver 검색 결과를 Google Places 상세 정보로 보강한다.

    Args:
        raw_results: (Naver 결과 dict, 카테고리 타입) 튜플 리스트.

    Returns:
        PlaceCandidate 리스트.
    """
    candidates: list[PlaceCandidate] = []
    candidates_by_place: dict[tuple[str, str], PlaceCandidate] = {}

    for place, cat_type, mood_tag in raw_results:
        name = place.get("name", "")
        if not name:
            continue
        actual_type = _infer_result_type(place.get("category", ""))
        if cat_type == "activity" and actual_type in ("food", "cafe"):
            logger.debug("액티비티 검색에서 음식점/카페 결과 제외: %s", name)
            continue
        if cat_type in ("food", "cafe") and actual_type not in (cat_type, "unknown"):
            logger.debug("검색 의도와 다른 카테고리 결과 제외: %s (%s)", name, actual_type)
            continue
        address = place.get("address", "")
        place_key = (name, address)
        if place_key in candidates_by_place:
            existing = candidates_by_place[place_key]
            if mood_tag and mood_tag not in existing.mood_tags:
                existing.mood_tags.append(mood_tag)
            continue

        try:
            details = get_place_details(name, address)
            place_id = details.get("place_id", "")
            is_open = is_place_open_now(place_id) if place_id else True

            google_lat = details.get("lat", 0.0)
            google_lon = details.get("lon", 0.0)
            naver_lat = place.get("lat", 0.0)
            naver_lon = place.get("lon", 0.0)
            lat, lon = _choose_coordinates(
                name,
                naver_lat,
                naver_lon,
                google_lat,
                google_lon,
            )

            candidate = PlaceCandidate(
                    name=name,
                    address=address,
                    category=place.get("category", ""),
                    rating=0.0,
                    is_open=is_open,
                    price_level=0,
                    place_id=place_id,
                    reviews=[],
                    lat=lat,
                    lon=lon,
                    category_type=cat_type,
                    mood_tags=[mood_tag] if mood_tag else [],
            )
            candidates.append(candidate)
            candidates_by_place[place_key] = candidate
        except Exception as e:
            logger.error("장소 상세 정보 보강 실패: name=%s error=%s", name, e)

    logger.info("후보 장소 수집 완료: %d개 (food/cafe/activity 혼합)", len(candidates))
    return candidates


def _choose_coordinates(
    place_name: str,
    naver_lat: float,
    naver_lon: float,
    google_lat: float,
    google_lon: float,
) -> tuple[float, float]:
    """표시 주소와 같은 검색 결과에서 온 Naver 좌표를 우선한다.

    Google Places는 동일 이름의 다른 지점을 매칭할 수 있으므로 Naver 좌표가
    유효하지 않을 때만 좌표 폴백으로 사용한다.
    """
    naver_lat, naver_lon = _normalize_coordinates(naver_lat, naver_lon)
    google_lat, google_lon = _normalize_coordinates(google_lat, google_lon)

    if _is_valid_seoul_coordinate(naver_lat, naver_lon):
        if _is_valid_seoul_coordinate(google_lat, google_lon):
            lat_gap = abs(naver_lat - google_lat)
            lon_gap = abs(naver_lon - google_lon)
            if lat_gap > 0.002 or lon_gap > 0.002:
                logger.warning(
                    "Google 좌표 불일치로 Naver 좌표 사용: %s "
                    "(naver=%.6f,%.6f google=%.6f,%.6f)",
                    place_name,
                    naver_lat,
                    naver_lon,
                    google_lat,
                    google_lon,
                )
        return naver_lat, naver_lon

    if _is_valid_seoul_coordinate(google_lat, google_lon):
        return google_lat, google_lon
    return 0.0, 0.0


def _is_valid_seoul_coordinate(lat: float, lon: float) -> bool:
    """좌표가 서울 인근의 유효한 WGS84 범위인지 확인한다."""
    return 37.3 <= lat <= 37.75 and 126.7 <= lon <= 127.25


def _normalize_coordinates(lat, lon) -> tuple[float, float]:
    """외부 API 좌표를 비교 가능한 float 값으로 정규화한다."""
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return 0.0, 0.0


def _infer_result_type(category: str) -> str:
    """Naver 카테고리 문자열로 실제 장소 타입을 추론한다."""
    lower = category.lower()
    if any(keyword in lower for keyword in _CAFE_CATEGORY_KEYWORDS):
        return "cafe"
    if any(keyword in lower for keyword in _FOOD_CATEGORY_KEYWORDS):
        return "food"
    if category:
        return "activity"
    return "unknown"


def filter_open_places(
    candidates: list[PlaceCandidate],
    selected_date: str = "",
) -> list[PlaceCandidate]:
    """오늘 일정인 경우에만 현재 영업 중인 장소로 필터링한다.

    Args:
        candidates: 전체 후보 장소 리스트.
        selected_date: 사용자 선택 날짜. 미래 날짜면 현재 영업 상태를 적용하지 않는다.

    Returns:
        영업 중인 장소만 포함된 리스트.
    """
    if selected_date:
        try:
            if date.fromisoformat(selected_date) > date.today():
                return candidates
        except ValueError:
            logger.warning("영업 여부 필터 날짜 파싱 실패: %s", selected_date)

    open_places = [c for c in candidates if c.is_open]
    logger.debug("영업 중 필터: %d / %d개", len(open_places), len(candidates))
    return open_places


def get_model_name() -> str:
    """Search Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
