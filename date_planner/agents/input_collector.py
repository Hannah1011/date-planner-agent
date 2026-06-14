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

    Args:
        raw_input: district, date, time_slot, mood, food_preferences,
                   cafe_style, budget, activities 키를 포함하는 dict.

    Returns:
        파싱된 UserRequest 인스턴스.

    Raises:
        ValueError: 필수 입력값 검증 실패 시.
    """
    valid, error_msg = validate_user_input(raw_input)
    if not valid:
        logger.error("사용자 입력 검증 실패: %s", error_msg)
        raise ValueError(f"입력 검증 실패: {error_msg}")

    try:
        time_slot = TimeSlot(raw_input.get("time_slot", TimeSlot.ALL_DAY.value))
    except ValueError:
        logger.warning("알 수 없는 time_slot, ALL_DAY로 대체")
        time_slot = TimeSlot.ALL_DAY

    try:
        mood = Mood(raw_input.get("mood", Mood.FOOD_EXPLORATION.value))
    except ValueError:
        logger.warning("알 수 없는 mood, FOOD_EXPLORATION으로 대체")
        mood = Mood.FOOD_EXPLORATION

    try:
        cafe_style = CafeStyle(raw_input.get("cafe_style", CafeStyle.COZY.value))
    except ValueError:
        logger.warning("알 수 없는 cafe_style, COZY로 대체")
        cafe_style = CafeStyle.COZY

    return UserRequest(
        district=raw_input.get("district", ""),
        date=raw_input.get("date", ""),
        time_slot=time_slot,
        mood=mood,
        food_preferences=raw_input.get("food_preferences", []),
        cafe_style=cafe_style,
        budget=raw_input.get("budget", 0),
        activities=raw_input.get("activities", []),
    )


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
