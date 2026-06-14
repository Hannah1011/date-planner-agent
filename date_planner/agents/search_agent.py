"""Search Agent: 선택 무드별 병렬 장소 검색 및 상세 정보 보강.

Tool Use + Routing + Parallelization 패턴.

검색 전략:
- 음식(food): food_preferences 지정 시 해당 음식, 없으면 무드 기반 맛집
- 카페(cafe): cafe_style 기반 카페
- 액티비티(activity): 선택된 무드별 액티비티
이 세 카테고리를 항상 병렬로 검색해 코스에 모두 포함되도록 한다.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from date_planner.agents.models import PlaceCandidate, UserRequest
from date_planner.config.constants import CafeStyle, Mood
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

    음식점과 카페 기본 후보에 더해 선택된 각 무드의 전용 쿼리를 검색한다.

    Args:
        request: 구조화된 사용자 요청.

    Returns:
        PlaceCandidate 리스트. 에러 시 빈 리스트.
    """
    queries = _build_queries(request)
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
                        raw_results.append((r, cat_type, mood_tag))
                    logger.debug("검색 완료: query=%s results=%d건", query, len(results))
                except Exception as e:
                    logger.error("검색 스레드 실패: query=%s error=%s", query, e)
    except Exception as e:
        logger.error("병렬 검색 실행 실패: %s", e)
        return []

    return _enrich_candidates(raw_results)


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

    # 음식 (항상 포함) — food_preferences가 있으면 그 음식으로, 없으면 일반 맛집
    if request.food_preferences:
        for pref in request.food_preferences[:2]:
            queries.append((f"{district} {pref}", "food", Mood.FOOD_EXPLORATION.value))
    else:
        queries.append((f"{district} 음식점 맛집", "food", Mood.FOOD_EXPLORATION.value))

    # 카페 (항상 포함)
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
    candidates_by_name: dict[str, PlaceCandidate] = {}

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
        if name in candidates_by_name:
            existing = candidates_by_name[name]
            if mood_tag and mood_tag not in existing.mood_tags:
                existing.mood_tags.append(mood_tag)
            continue

        try:
            details = get_place_details(name, place.get("address", ""))
            place_id = details.get("place_id", "")
            is_open = is_place_open_now(place_id) if place_id else True

            google_lat = details.get("lat", 0.0)
            google_lon = details.get("lon", 0.0)
            naver_lat = place.get("lat", 0.0)
            naver_lon = place.get("lon", 0.0)
            lat = google_lat if google_lat != 0.0 else naver_lat
            lon = google_lon if google_lon != 0.0 else naver_lon

            candidate = PlaceCandidate(
                    name=name,
                    address=place.get("address", ""),
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
            candidates_by_name[name] = candidate
        except Exception as e:
            logger.error("장소 상세 정보 보강 실패: name=%s error=%s", name, e)

    logger.info("후보 장소 수집 완료: %d개 (food/cafe/activity 혼합)", len(candidates))
    return candidates


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


def filter_open_places(candidates: list[PlaceCandidate]) -> list[PlaceCandidate]:
    """현재 영업 중인 장소만 필터링한다.

    Args:
        candidates: 전체 후보 장소 리스트.

    Returns:
        영업 중인 장소만 포함된 리스트.
    """
    open_places = [c for c in candidates if c.is_open]
    logger.debug("영업 중 필터: %d / %d개", len(open_places), len(candidates))
    return open_places


def get_model_name() -> str:
    """Search Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
