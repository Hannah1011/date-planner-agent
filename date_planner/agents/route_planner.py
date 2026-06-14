"""Route Planner Agent: 대중교통 최적화 + 날씨 반영.

Planning + Guardrails 패턴.

코스 구성 원칙:
- 음식점 1개 + 카페 1개 + 나머지는 액티비티로 채운다.
- 시간대별로 목표 장소 수가 다르다.
- 구간 이동 시간이 MAX_TRANSIT_MINUTES를 초과하면 해당 장소를 건너뛴다.
"""

import uuid

from date_planner.agents.models import CourseStop, DateCourse, PlaceCandidate, UserRequest
from date_planner.config.constants import (
    MAX_COURSE_PLACES,
    MAX_TRANSIT_MINUTES,
    MIN_COURSE_PLACES,
    RECOMMENDED_TOTAL_TRANSIT,
    TimeSlot,
)
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.tools.directions import get_transit_duration
from date_planner.tools.weather import get_weather
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "route_planner"

# 시간대별 목표 장소 수
_TIME_SLOT_PLACE_COUNT: dict[TimeSlot, int] = {
    TimeSlot.MORNING: 2,
    TimeSlot.LUNCH: 2,
    TimeSlot.AFTERNOON: 3,
    TimeSlot.EVENING: 3,
    TimeSlot.NIGHT: 2,
    TimeSlot.ALL_DAY: 5,
}

# 카테고리 분류 키워드
_FOOD_KEYWORDS = ("음식", "식당", "레스토랑", "맛집", "한식", "양식", "이탈리안",
                  "중식", "일식", "분식", "고기", "포차", "술집")
_CAFE_KEYWORDS = ("카페", "커피", "디저트", "베이커리", "브런치", "티룸")


def build_course(candidates: list[PlaceCandidate], request: UserRequest) -> DateCourse:
    """후보 장소로부터 데이트 코스를 구성한다.

    음식점 1개 + 카페 1개 + 나머지 액티비티 순서로 채우되,
    이동 시간 제약(MAX_TRANSIT_MINUTES)을 고려해 최종 선택한다.

    Args:
        candidates: Search Agent가 수집한 후보 장소 리스트.
        request: 사용자 요청 조건.

    Returns:
        완성된 DateCourse 인스턴스.
    """
    if not candidates:
        logger.warning("후보 장소 없음 — 빈 코스 반환")
        return _empty_course()

    target_count = max(_get_target_count(request.time_slots), len(request.moods))
    selected = _select_places(candidates, target_count, request.moods)
    stops = _build_stops(selected)
    weather_note = _get_weather_note(request.district, request.date)

    total_transit = sum(s.transit_minutes_from_prev for s in stops)
    if total_transit > RECOMMENDED_TOTAL_TRANSIT:
        logger.warning("총 이동 시간 권고 초과: %d분", total_transit)

    course = DateCourse(
        stops=stops,
        total_transit_minutes=total_transit,
        total_estimated_cost=0,
        weather_note=weather_note,
        session_id=str(uuid.uuid4()),
    )
    logger.info(
        "코스 구성 완료: %d개 장소 (food=%d, cafe=%d, activity=%d), 이동 %d분",
        len(stops),
        sum(1 for s in stops if _classify_place_type(s.place) == "food"),
        sum(1 for s in stops if _classify_place_type(s.place) == "cafe"),
        sum(1 for s in stops if _classify_place_type(s.place) == "activity"),
        total_transit,
    )
    return course


def _get_target_count(time_slots: list) -> int:
    """time_slots 리스트로부터 목표 장소 수를 계산한다.

    ALL_DAY 포함 시 최대(5개), 아니면 각 슬롯 합산 후 MAX_COURSE_PLACES로 제한.

    Args:
        time_slots: TimeSlot Enum 리스트.

    Returns:
        목표 장소 수.
    """
    if not time_slots:
        return MIN_COURSE_PLACES
    if TimeSlot.ALL_DAY in time_slots:
        return _TIME_SLOT_PLACE_COUNT[TimeSlot.ALL_DAY]
    total = sum(_TIME_SLOT_PLACE_COUNT.get(ts, MIN_COURSE_PLACES) for ts in time_slots)
    return min(total, MAX_COURSE_PLACES)


def _classify_place_type(candidate: PlaceCandidate) -> str:
    """장소의 카테고리 타입을 분류한다.

    Args:
        candidate: 장소 후보.

    Returns:
        "food" | "cafe" | "activity"
    """
    if candidate.category_type in ("food", "cafe", "activity"):
        return candidate.category_type
    cat = candidate.category.lower()
    if any(k in cat for k in _FOOD_KEYWORDS):
        return "food"
    if any(k in cat for k in _CAFE_KEYWORDS):
        return "cafe"
    return "activity"


def _select_places(
    candidates: list[PlaceCandidate],
    target_count: int,
    required_moods: list,
) -> list[PlaceCandidate]:
    """선택 무드별 장소를 우선 확보하고 나머지 코스 장소를 선택한다.

    이동 시간 제약을 체크하고, 초과 시 해당 장소를 건너뛴다.

    Args:
        candidates: 후보 장소 리스트.
        target_count: 목표 장소 수.

    Returns:
        선택된 PlaceCandidate 리스트.
    """
    target = min(target_count, MAX_COURSE_PLACES)

    # 타입별 풀 구성
    pools: dict[str, list[PlaceCandidate]] = {"food": [], "cafe": [], "activity": []}
    for c in candidates:
        t = _classify_place_type(c)
        pools[t].append(c)

    ordered_picks: list[PlaceCandidate] = []
    used: set[str] = set()

    # 선택된 각 무드에 해당하는 검색 후보를 최소 한 개씩 우선 확보한다.
    for mood in required_moods:
        match = next(
            (c for c in candidates if mood.value in c.mood_tags and c.name not in used),
            None,
        )
        if match:
            ordered_picks.append(match)
            used.add(match.name)
        else:
            logger.warning("선택 무드 후보 없음: %s", mood.value)

    # 기본 데이트 구성인 음식점과 카페도 각각 최대 한 곳만 포함한다.
    for place_type in ("food", "cafe"):
        if any(_classify_place_type(c) == place_type for c in ordered_picks):
            continue
        match = next((c for c in pools[place_type] if c.name not in used), None)
        if match and len(ordered_picks) < target:
            ordered_picks.append(match)
            used.add(match.name)

    # 남은 슬롯은 액티비티를 우선하고 전체 후보로 보충한다.
    for candidate in pools["activity"]:
        if len(ordered_picks) >= target:
            break
        if candidate.name not in used:
            ordered_picks.append(candidate)
            used.add(candidate.name)
    if len(ordered_picks) < target:
        for candidate in candidates:
            if len(ordered_picks) >= target:
                break
            if candidate.name in used:
                continue
            place_type = _classify_place_type(candidate)
            if place_type in ("food", "cafe") and any(
                _classify_place_type(c) == place_type for c in ordered_picks
            ):
                continue
            ordered_picks.append(candidate)
            used.add(candidate.name)

    # 무드 필수 장소는 이동 시간이 길어도 포함하고, 보충 장소만 이동 시간을 제한한다.
    final: list[PlaceCandidate] = []
    required_names = {
        candidate.name
        for candidate in ordered_picks
        if any(mood.value in candidate.mood_tags for mood in required_moods)
    }
    for candidate in ordered_picks:
        if len(final) >= target:
            break
        if not final:
            final.append(candidate)
            continue

        transit = get_transit_duration(final[-1].address, candidate.address)
        if transit == -1:
            logger.warning("이동 시간 조회 실패: %s -> %s, 장소 포함", final[-1].name, candidate.name)
            final.append(candidate)
        elif transit <= MAX_TRANSIT_MINUTES or candidate.name in required_names:
            if transit > MAX_TRANSIT_MINUTES:
                logger.warning("무드 필수 장소 이동 시간 초과 허용: %s (%d분)", candidate.name, transit)
            final.append(candidate)
        else:
            logger.debug("이동 시간 초과로 제외: %s -> %s (%d분)", final[-1].name, candidate.name, transit)

    logger.debug("선택된 장소: %d개 (목표 %d개)", len(final), target)
    return final


def _build_stops(places: list[PlaceCandidate]) -> list[CourseStop]:
    """선택된 장소 목록을 CourseStop 리스트로 변환한다.

    Args:
        places: 선택된 PlaceCandidate 리스트.

    Returns:
        CourseStop 리스트.
    """
    stops: list[CourseStop] = []
    for i, place in enumerate(places):
        if i == 0:
            transit_minutes = 0
        else:
            transit_minutes = get_transit_duration(places[i - 1].address, place.address)
            if transit_minutes == -1:
                transit_minutes = 0

        stops.append(
            CourseStop(
                place=place,
                transit_minutes_from_prev=transit_minutes,
                estimated_cost=0,
                visit_order=i + 1,
            )
        )
    return stops


def _get_weather_note(district: str, date: str) -> str:
    """날씨 정보를 가져와 코스에 포함할 안내 문구를 생성한다.

    Args:
        district: 구 이름.
        date: 날짜 문자열.

    Returns:
        날씨 안내 문자열. 데이터 없으면 빈 문자열.
    """
    try:
        weather = get_weather(district, date)
        if not weather:
            return ""
        condition = weather.get("condition", "")
        temp = weather.get("temperature", "")
        pop = weather.get("precipitation_probability", 0)
        note = f"{district} {condition} {temp}°C"
        if pop >= 30:
            note += f" (강수 확률 {pop}% — 우산 챙기세요)"
        return note
    except Exception as e:
        logger.error("날씨 정보 생성 실패: %s", e)
        return ""


def _empty_course() -> DateCourse:
    """후보 없을 때 반환할 빈 DateCourse를 생성한다."""
    return DateCourse(
        stops=[],
        total_transit_minutes=0,
        total_estimated_cost=0,
        weather_note="",
        session_id=str(uuid.uuid4()),
    )


def is_within_budget(course: DateCourse, budget: int) -> bool:
    """레거시 호환 함수. 현재 코스는 비용을 계산하지 않는다."""
    return True


def get_model_name() -> str:
    """Route Planner Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
