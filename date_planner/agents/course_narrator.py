"""Course Narrator Agent: 코스 선택 이유와 추천 포인트 생성.

GPT-4o-mini를 사용해 왜 이 장소들을 골랐는지 자연어로 설명한다.
API 호출 실패 시 템플릿 기반 설명으로 폴백한다.
"""

import os

from date_planner.agents.models import DateCourse, UserRequest
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "course_narrator"

_MOOD_KR = {
    "NATURE_HEALING": "자연 & 힐링",
    "FOOD_EXPLORATION": "맛집 탐방",
    "NEW_ACTIVITY": "새로운 액티비티",
    "COZY_CAFE": "카페 투어",
    "SHOPPING_STREET": "쇼핑 & 거리 탐방",
}

_TIME_SLOT_KR = {
    "MORNING": "오전",
    "LUNCH": "점심",
    "AFTERNOON": "오후",
    "EVENING": "저녁",
    "NIGHT": "밤",
    "ALL_DAY": "하루 종일",
}


def generate_course_description(
    course: DateCourse,
    request: UserRequest,
    preference_context: str = "",
    feedback_reason: str = "",
) -> str:
    """커플의 취향을 분석하고 코스 구성 이유를 자연어로 생성한다.

    GPT-4o-mini를 먼저 시도하고, 실패 시 템플릿 기반으로 폴백한다.

    Args:
        course: 완성된 DateCourse.
        request: 사용자 요청 조건.
        preference_context: Memory Agent가 로드한 저장 취향 요약.

    Returns:
        코스 설명 문자열.
    """
    description = _generate_with_gpt(course, request, preference_context, feedback_reason)
    if description:
        return description
    return _generate_from_template(course, request, preference_context, feedback_reason)


def _generate_with_gpt(
    course: DateCourse,
    request: UserRequest,
    preference_context: str,
    feedback_reason: str,
) -> str:
    """GPT-4o-mini로 코스 설명을 생성한다.

    Args:
        course: 완성된 DateCourse.
        request: 사용자 요청 조건.
        preference_context: Memory Agent가 로드한 저장 취향 요약.

    Returns:
        생성된 설명 문자열. 실패 시 빈 문자열.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        moods_kr = [_MOOD_KR.get(m.value, m.value) for m in request.moods]
        time_kr = " & ".join(_TIME_SLOT_KR.get(ts.value, ts.value) for ts in request.time_slots)
        stops_text = "\n".join(
            f"  {s.visit_order}. {s.place.name} ({s.place.category})"
            for s in course.stops
        )

        prompt = (
            "데이트 코스 추천 인사이트를 완결된 3-4문장으로 작성해주세요.\n"
            "이번 요청에서 사용자가 직접 선택한 내용과 DB에 저장된 과거 취향을 반드시 "
            "서로 다른 문장으로 구분하세요.\n"
            "첫 문장에서는 '이번 요청에서는'으로 시작해 먹고 싶은 음식과 선택 무드를 설명하세요.\n"
            "두 번째 문장에서는 저장 취향이 있으면 '저장된 취향 기록을 보면'으로 시작해 설명하고, "
            "없으면 저장된 취향이 없다고 말하세요.\n"
            "이어서 '그래서 이번 코스는'으로 시작해 장소 선택 이유와 순서를 설명하세요.\n"
            "이번 요청 내용을 저장된 과거 취향이라고 표현하지 말고, 없는 취향을 지어내지 마세요.\n\n"
            "리플랜 피드백이 있으면 첫 문장에서 피드백을 반영해 다른 장소를 추천한다는 점을 "
            "명확히 설명하세요.\n\n"
            "장소명과 카테고리에 없는 메뉴, 분위기, 체험 내용을 추측하거나 지어내지 마세요.\n"
            "코스에 음식점이 여러 곳 있더라도 각각에서 모두 식사하라고 권하지 마세요.\n\n"
            f"저장된 취향 정보:\n{preference_context or '없음'}\n\n"
            f"조건: {request.district} / {time_kr} / 무드: {', '.join(moods_kr)}\n"
            f"먹고 싶은 것: {', '.join(request.food_preferences) or '지정 없음'}\n"
            f"리플랜 피드백: {feedback_reason or '없음'}\n"
            f"코스:\n{stops_text}\n\n"
            f"추천 인사이트:"
        )

        response = client.chat.completions.create(
            model=MODEL_CONFIG[_AGENT_KEY],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            logger.warning("GPT 코스 설명이 길이 제한으로 잘림 — 템플릿으로 폴백")
            return ""
        return choice.message.content.strip()
    except Exception as e:
        logger.warning("GPT 코스 설명 생성 실패 — 템플릿으로 폴백: %s", e)
        return ""


def _generate_from_template(
    course: DateCourse,
    request: UserRequest,
    preference_context: str = "",
    feedback_reason: str = "",
) -> str:
    """템플릿 기반으로 코스 설명을 생성한다.

    Args:
        course: 완성된 DateCourse.
        request: 사용자 요청 조건.
        preference_context: Memory Agent가 로드한 저장 취향 요약.

    Returns:
        템플릿 기반 설명 문자열.
    """
    moods_kr = [_MOOD_KR.get(m.value, m.value) for m in request.moods]
    requested_moods = ", ".join(moods_kr)
    if request.food_preferences:
        requested_foods = ", ".join(request.food_preferences)
        request_summary = (
            f"이번 요청에서 드시고 싶은 음식은 {requested_foods}이고, "
            f"선택한 무드는 {requested_moods}예요."
        )
    else:
        request_summary = (
            f"이번 요청에서는 특정 음식을 지정하지 않았고, 선택한 무드는 {requested_moods}예요."
        )
    parts: list[str] = []
    if feedback_reason:
        parts.append(f"말씀해주신 피드백을 반영해 이전과 다른 장소를 추천드려요.")
    parts.append(request_summary)

    saved_preferences = _extract_preference_values(preference_context)
    if saved_preferences:
        parts.append(f"저장된 취향 기록을 보면 {', '.join(saved_preferences)}도 선호하셨어요.")
    else:
        parts.append("아직 저장된 취향 기록은 없어 이번 요청 조건을 중심으로 추천했어요.")

    if course.stops:
        route = " → ".join(s.place.name for s in course.stops)
        parts.append(
            f"그래서 이번 코스는 {route} 순서로 방문하며 선택한 무드를 고르게 "
            "즐길 수 있도록 구성했습니다."
        )
    else:
        parts.append(f"그래서 이번 코스는 {request.district}에서 선택한 무드를 중심으로 구성했습니다.")

    if course.weather_note:
        parts.append(f"오늘 날씨: {course.weather_note}.")

    return " ".join(parts)


def _extract_preference_values(preference_context: str) -> list[str]:
    """Memory Agent 취향 요약에서 선호 항목 값만 추출한다."""
    values: list[str] = []
    in_positive_section = False
    for line in preference_context.splitlines():
        stripped = line.strip()
        if stripped == "- 선호:":
            in_positive_section = True
            continue
        if stripped == "- 비선호:":
            in_positive_section = False
            continue
        if not in_positive_section or not stripped.startswith("*") or ":" not in stripped:
            continue
        value = stripped.split(":", 1)[1].strip().split(" (", 1)[0]
        if value:
            values.append(value)
    return values[:5]
