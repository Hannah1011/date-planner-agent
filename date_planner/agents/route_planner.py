"""Route Planner Agent: 대중교통 최적화 + 날씨 반영 + 예산 체크.

Planning + Guardrails 패턴. GPT-4o 사용.
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

_TIME_SLOT_PLACE_COUNT: dict[TimeSlot, int] = {
    TimeSlot.MORNING: 2,
    TimeSlot.LUNCH: 2,
    TimeSlot.AFTERNOON: 3,
    TimeSlot.EVENING: 3,
    TimeSlot.NIGHT: 2,
    TimeSlot.ALL_DAY: 5,
}

_PRICE_LEVEL_COST: dict[int, int] = {
    0: 10000,
    1: 15000,
    2: 25000,
    3: 50000,
    4: 80000,
}


def build_course(candidates: list[PlaceCandidate], request: UserRequest) -> DateCourse:
    """후보 장소로부터 대중교통 이동 시간을 고려한 데이트 코스를 구성한다.

    이동 시간이 MAX_TRANSIT_MINUTES를 초과하는 구간은 건너뛰고
    대체 장소를 선택한다. 결과 코스는 MIN~MAX 범위의 장소 수를 갖는다.

    Args:
        candidates: Search Agent가 수집한 후보 장소 리스트.
        request: 사용자 요청 조건.

    Returns:
        완성된 DateCourse 인스턴스.
    """
    if not candidates:
        logger.warning("후보 장소 없음 — 빈 코스 반환")
        return _empty_course()

    target_count = _TIME_SLOT_PLACE_COUNT.get(request.time_slot, MIN_COURSE_PLACES)
    selected = _select_places(candidates, target_count)
    stops = _build_stops(selected, request.district)
    weather_note = _get_weather_note(request.district, request.date)

    total_transit = sum(s.transit_minutes_from_prev for s in stops)
    total_cost = sum(s.estimated_cost for s in stops)

    if total_transit > RECOMMENDED_TOTAL_TRANSIT:
        logger.warning("총 이동 시간 권고 초과: %d분", total_transit)

    course = DateCourse(
        stops=stops,
        total_transit_minutes=total_transit,
        total_estimated_cost=total_cost,
        weather_note=weather_note,
        session_id=str(uuid.uuid4()),
    )
    logger.info("코스 구성 완료: %d개 장소, 이동 %d분, 비용 %d원", len(stops), total_transit, total_cost)
    return course


def _select_places(candidates: list[PlaceCandidate], target_count: int) -> list[PlaceCandidate]:
    """이동 시간 제약을 고려해 코스에 포함할 장소를 선택한다.

    첫 장소를 기준으로 다음 장소를 순서대로 추가하되,
    이전 장소에서 MAX_TRANSIT_MINUTES 초과 시 해당 장소를 건너뛴다.

    Args:
        candidates: 후보 장소 리스트 (rating 내림차순 정렬됨).
        target_count: 목표 장소 수.

    Returns:
        선택된 PlaceCandidate 리스트.
    """
    sorted_candidates = sorted(candidates, key=lambda c: c.rating, reverse=True)
    selected: list[PlaceCandidate] = []

    for candidate in sorted_candidates:
        if len(selected) >= min(target_count, MAX_COURSE_PLACES):
            break

        if not selected:
            selected.append(candidate)
            continue

        prev = selected[-1]
        transit = get_transit_duration(prev.address, candidate.address)

        if transit == -1:
            logger.warning("이동 시간 조회 실패: %s -> %s, 장소 포함", prev.name, candidate.name)
            selected.append(candidate)
        elif transit <= MAX_TRANSIT_MINUTES:
            selected.append(candidate)
        else:
            logger.debug("이동 시간 초과로 제외: %s -> %s (%d분)", prev.name, candidate.name, transit)

    logger.debug("선택된 장소: %d개", len(selected))
    return selected


def _build_stops(places: list[PlaceCandidate], origin_district: str) -> list[CourseStop]:
    """선택된 장소 목록을 CourseStop 리스트로 변환한다.

    Args:
        places: 선택된 PlaceCandidate 리스트.
        origin_district: 출발 기준 지역 (첫 번째 이동 계산용).

    Returns:
        CourseStop 리스트.
    """
    stops: list[CourseStop] = []
    for i, place in enumerate(places):
        if i == 0:
            transit_minutes = 0
        else:
            prev_address = places[i - 1].address
            transit_minutes = get_transit_duration(prev_address, place.address)
            if transit_minutes == -1:
                transit_minutes = 0

        estimated_cost = _PRICE_LEVEL_COST.get(place.price_level, 15000)
        stops.append(
            CourseStop(
                place=place,
                transit_minutes_from_prev=transit_minutes,
                estimated_cost=estimated_cost,
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
        note = f"{condition} {temp}°C"
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
    """코스 총 비용이 예산 이내인지 확인한다.

    Args:
        course: 완성된 DateCourse.
        budget: 사용자 예산 (원).

    Returns:
        예산 이내면 True.
    """
    within = course.total_estimated_cost <= budget
    if not within:
        logger.warning(
            "예산 초과: 예상 %d원 > 예산 %d원",
            course.total_estimated_cost,
            budget,
        )
    return within


def get_model_name() -> str:
    """Route Planner Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
