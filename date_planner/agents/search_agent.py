"""Search Agent: 카테고리별 병렬 장소 검색 및 리뷰 분석.

Tool Use + Parallelization 패턴. GPT-4o 사용.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from date_planner.agents.models import PlaceCandidate, UserRequest
from date_planner.config.constants import Mood
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.tools.google_places import get_place_details, is_place_open_now
from date_planner.tools.naver_search import search_places
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "search"
_MAX_WORKERS = 3

_MOOD_CATEGORIES: dict[Mood, list[str]] = {
    Mood.NATURE_HEALING: ["공원", "산책로", "한강"],
    Mood.FOOD_EXPLORATION: ["음식점", "맛집", "카페"],
    Mood.NEW_ACTIVITY: ["전시", "팝업스토어", "체험"],
    Mood.COZY_CAFE: ["카페", "디저트", "베이커리"],
    Mood.SHOPPING_STREET: ["쇼핑", "편집샵", "거리"],
}


def search_candidates(request: UserRequest) -> list[PlaceCandidate]:
    """사용자 요청 조건에 맞는 장소 후보를 병렬 검색으로 수집한다.

    무드에 따른 카테고리별로 동시 검색을 수행한 후 결과를 통합한다.

    Args:
        request: 구조화된 사용자 요청.

    Returns:
        PlaceCandidate 리스트. 에러 시 빈 리스트.
    """
    categories = _MOOD_CATEGORIES.get(request.mood, ["맛집", "카페"])
    queries = [f"{request.district} {cat}" for cat in categories]

    raw_places: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(search_places, q, 3): q for q in queries}
            for future in as_completed(futures):
                query = futures[future]
                try:
                    results = future.result()
                    raw_places.extend(results)
                    logger.debug("검색 완료: query=%s results=%d건", query, len(results))
                except Exception as e:
                    logger.error("검색 스레드 실패: query=%s error=%s", query, e)
    except Exception as e:
        logger.error("병렬 검색 실행 실패: %s", e)
        return []

    return _enrich_candidates(raw_places, request.date)


def _enrich_candidates(raw_places: list[dict], date: str) -> list[PlaceCandidate]:
    """Naver 검색 결과를 Google Places 상세 정보로 보강한다.

    Args:
        raw_places: Naver 검색 결과 dict 리스트.
        date: 방문 예정 날짜 (영업 여부 확인용).

    Returns:
        PlaceCandidate 리스트.
    """
    candidates: list[PlaceCandidate] = []
    seen_names: set[str] = set()

    for place in raw_places:
        name = place.get("name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        try:
            details = get_place_details(name, place.get("address", ""))
            place_id = details.get("place_id", "")
            is_open = is_place_open_now(place_id) if place_id else True

            # 좌표: Google Places 우선, 없으면 Naver mapx/mapy 폴백
            google_lat = details.get("lat", 0.0)
            google_lon = details.get("lon", 0.0)
            naver_lat = place.get("lat", 0.0)
            naver_lon = place.get("lon", 0.0)
            lat = google_lat if google_lat != 0.0 else naver_lat
            lon = google_lon if google_lon != 0.0 else naver_lon

            candidates.append(
                PlaceCandidate(
                    name=name,
                    address=place.get("address", ""),
                    category=place.get("category", ""),
                    rating=float(details.get("rating", 0.0)),
                    is_open=is_open,
                    price_level=int(details.get("price_level", 0)),
                    place_id=place_id,
                    reviews=details.get("reviews", []),
                    lat=lat,
                    lon=lon,
                )
            )
        except Exception as e:
            logger.error("장소 상세 정보 보강 실패: name=%s error=%s", name, e)

    logger.info("후보 장소 수집 완료: %d개", len(candidates))
    return candidates


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
