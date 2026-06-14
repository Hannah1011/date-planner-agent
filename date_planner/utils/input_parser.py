"""Input Collector Agent: 사용자 온보딩 질문 수행 및 조건 구조화.

Prompt Chaining + HITL 패턴. GPT-4o-mini 사용.
"""

from date_planner.agents.models import UserRequest
from date_planner.config.constants import CafeStyle, Mood, TimeSlot
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.guardrails.validators import validate_user_input
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "input_collector"


def parse_user_request(raw_input: dict) -> UserRequest:
    """사용자 raw 입력 dict를 검증하고 UserRequest 구조체로 변환한다.

    "time_slots" (리스트)와 레거시 "time_slot" (단일값) 모두 지원한다.
    "moods" (리스트)와 레거시 "mood" (단일값) 모두 지원한다.

    Args:
        raw_input: district, date, time_slots, moods, food_preferences,
                   cafe_style, activities 키를 포함하는 dict.

    Returns:
        파싱된 UserRequest 인스턴스.

    Raises:
        ValueError: 필수 입력값 검증 실패 시.
    """
    valid, error_msg = validate_user_input(raw_input)
    if not valid:
        logger.error("사용자 입력 검증 실패: %s", error_msg)
        raise ValueError(f"입력 검증 실패: {error_msg}")

    time_slots = _parse_time_slots(raw_input)
    moods = _parse_moods(raw_input)

    try:
        cafe_style = CafeStyle(raw_input.get("cafe_style", CafeStyle.COZY.value))
    except ValueError:
        logger.warning("알 수 없는 cafe_style, COZY로 대체")
        cafe_style = CafeStyle.COZY

    return UserRequest(
        district=raw_input.get("district", ""),
        date=raw_input.get("date", ""),
        time_slots=time_slots,
        moods=moods,
        food_preferences=raw_input.get("food_preferences", []),
        cafe_style=cafe_style,
        activities=raw_input.get("activities", []),
    )


def _parse_time_slots(raw_input: dict) -> list[TimeSlot]:
    """raw_input에서 time_slots 리스트를 파싱한다.

    "time_slots" 키(리스트)와 레거시 "time_slot" 키(단일값) 모두 지원한다.

    Args:
        raw_input: 사용자 입력 dict.

    Returns:
        TimeSlot Enum 리스트. 비어있으면 [ALL_DAY] 기본값 반환.
    """
    raw = raw_input.get("time_slots", None)

    if raw is None:
        single = raw_input.get("time_slot", TimeSlot.ALL_DAY.value)
        raw = [single] if single else []

    if isinstance(raw, str):
        raw = [raw]

    slots: list[TimeSlot] = []
    for s in raw:
        try:
            slots.append(TimeSlot(s))
        except ValueError:
            logger.warning("알 수 없는 time_slot 값 무시: %s", s)

    if not slots:
        logger.warning("유효한 time_slot 없음 — ALL_DAY 기본값 사용")
        slots = [TimeSlot.ALL_DAY]

    return slots


def _parse_moods(raw_input: dict) -> list[Mood]:
    """raw_input에서 moods 리스트를 파싱한다.

    "moods" 키(리스트)와 레거시 "mood" 키(단일값) 모두 지원한다.

    Args:
        raw_input: 사용자 입력 dict.

    Returns:
        Mood Enum 리스트. 비어있으면 [FOOD_EXPLORATION] 기본값 반환.
    """
    raw_moods = raw_input.get("moods", None)

    # 레거시 "mood" 단일값 지원
    if raw_moods is None:
        mood_raw = raw_input.get("mood", Mood.FOOD_EXPLORATION.value)
        raw_moods = [mood_raw]

    if isinstance(raw_moods, str):
        raw_moods = [raw_moods]

    moods: list[Mood] = []
    for m in raw_moods:
        try:
            moods.append(Mood(m))
        except ValueError:
            logger.warning("알 수 없는 mood 값 무시: %s", m)

    if not moods:
        logger.warning("유효한 mood 없음 — FOOD_EXPLORATION 기본값 사용")
        moods = [Mood.FOOD_EXPLORATION]

    return moods


def build_search_query(request: UserRequest) -> str:
    """UserRequest로부터 네이버 검색에 사용할 쿼리 문자열을 생성한다.

    Args:
        request: 구조화된 사용자 요청.

    Returns:
        검색 쿼리 문자열.
    """
    parts = [request.district]
    if request.food_preferences:
        parts.append(request.food_preferences[0])
    else:
        parts.append("맛집")
    return " ".join(parts)


def get_model_name() -> str:
    """Input Collector Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
