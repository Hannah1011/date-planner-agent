"""Feedback & Replan Agent: HITL 체크포인트, 리플랜 루프, Reflection.

Goal Setting & Monitoring + HITL + Reflection 패턴. GPT-4o 사용.
"""

from dataclasses import dataclass

from date_planner.agents.models import DateCourse, PlaceCandidate, UserRequest
from date_planner.agents.memory_agent import save_accepted_course, save_rejected_course
from date_planner.config.constants import MAX_REPLAN_ATTEMPTS
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.guardrails.validators import check_replan_limit
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "feedback_replan"


@dataclass
class FeedbackResult:
    """피드백 처리 결과."""

    accepted: bool
    reason: str
    suggest_new_conditions: bool
    replan_count: int


def process_feedback(
    course: DateCourse,
    accepted: bool,
    reason: str,
    replan_count: int,
    request: UserRequest,
) -> FeedbackResult:
    """사용자 피드백을 처리하고 다음 행동을 결정한다.

    승인 시: Memory Agent에 저장 후 종료.
    거절 시: 이유 분석 후 리플랜 또는 조건 변경 제안.

    Args:
        course: 현재 제안된 DateCourse.
        accepted: 사용자 승인 여부.
        reason: 거절 이유 텍스트 (승인 시 빈 문자열).
        replan_count: 현재까지 리플랜 횟수.
        request: 원본 사용자 요청.

    Returns:
        FeedbackResult 인스턴스.
    """
    if accepted:
        _handle_accepted(course)
        return FeedbackResult(
            accepted=True,
            reason="",
            suggest_new_conditions=False,
            replan_count=replan_count,
        )

    if not reason:
        logger.warning("거절 이유 없이 리플랜 요청 — 이유 입력 유도")
        return FeedbackResult(
            accepted=False,
            reason="",
            suggest_new_conditions=False,
            replan_count=replan_count,
        )

    save_rejected_course(course, reason, course.session_id)

    if not check_replan_limit(replan_count):
        logger.warning("리플랜 횟수 초과: %d회 — 조건 변경 제안", replan_count)
        return FeedbackResult(
            accepted=False,
            reason=reason,
            suggest_new_conditions=True,
            replan_count=replan_count,
        )

    logger.info("리플랜 진행: %d회차, 이유=%s", replan_count + 1, reason)
    return FeedbackResult(
        accepted=False,
        reason=reason,
        suggest_new_conditions=False,
        replan_count=replan_count + 1,
    )


def apply_feedback_to_candidates(
    candidates: list[PlaceCandidate],
    reason: str,
) -> list[PlaceCandidate]:
    """거절 이유를 분석해 후보 장소 리스트에서 문제 장소를 제외한다.

    Reflection 패턴: 이유 텍스트에서 키워드를 추출해 필터링에 반영한다.

    Args:
        candidates: 현재 후보 장소 리스트.
        reason: 거절 이유 텍스트.

    Returns:
        필터링된 PlaceCandidate 리스트.
    """
    if not reason:
        return candidates

    dislike_keywords = _extract_dislike_keywords(reason)
    if not dislike_keywords:
        return candidates

    filtered = [
        c for c in candidates
        if not any(kw in c.name or kw in c.category for kw in dislike_keywords)
    ]
    logger.info(
        "Reflection 필터 적용: 제외 키워드=%s, %d -> %d개",
        dislike_keywords,
        len(candidates),
        len(filtered),
    )
    return filtered


def _handle_accepted(course: DateCourse) -> None:
    """승인된 코스를 Memory Agent에 저장한다."""
    try:
        save_accepted_course(course)
        logger.info("승인 코스 저장 완료: session=%s", course.session_id)
    except Exception as e:
        logger.error("승인 코스 저장 중 오류: %s", e)


def _extract_dislike_keywords(reason: str) -> list[str]:
    """거절 이유에서 필터링에 사용할 키워드를 추출한다.

    Args:
        reason: 거절 이유 텍스트.

    Returns:
        필터 키워드 리스트.
    """
    keywords: list[str] = []
    dislike_markers = ["싫어", "별로", "안 좋아", "싫음", "노 땡겨", "별로야"]
    for marker in dislike_markers:
        idx = reason.find(marker)
        if idx > 0:
            subject = reason[:idx].split()[-1] if reason[:idx].split() else ""
            if subject:
                keywords.append(subject)
    return keywords


def build_replan_context(reason: str, original_request: UserRequest) -> dict:
    """리플랜 시 Search Agent에 전달할 보강된 컨텍스트를 생성한다.

    Args:
        reason: 거절 이유 텍스트.
        original_request: 원본 UserRequest.

    Returns:
        보강된 검색 조건 dict.
    """
    context = {
        "district": original_request.district,
        "date": original_request.date,
        "time_slot": original_request.time_slot,
        "mood": original_request.mood,
        "food_preferences": original_request.food_preferences,
        "cafe_style": original_request.cafe_style,
        "budget": original_request.budget,
        "activities": original_request.activities,
        "exclude_reason": reason,
    }
    return context


def get_model_name() -> str:
    """Feedback & Replan Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
