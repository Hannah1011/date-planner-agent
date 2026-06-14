"""Feedback & Replan Agent: HITL 체크포인트, 리플랜 루프, Reflection.

Goal Setting & Monitoring + HITL + 부분적 Reflection 패턴.
"""

from dataclasses import dataclass
import json
import os
from typing import Optional

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


@dataclass
class FeedbackAnalysis:
    """거절 이유에서 추출한 리플랜 방향."""

    summary: str
    exclude_keywords: list[str]
    search_keywords: list[str]


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
        _handle_accepted(course, reason)
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
    excluded_place_names: Optional[set[str]] = None,
    analysis: Optional[FeedbackAnalysis] = None,
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

    analysis = analysis or _analyze_feedback_with_rules(reason)
    dislike_keywords = analysis.exclude_keywords
    excluded_place_names = excluded_place_names or set()

    filtered = [
        c for c in candidates
        if c.name not in excluded_place_names
        and not any(kw in c.name or kw in c.category for kw in dislike_keywords)
    ]
    logger.info(
        "Reflection 필터 적용: 제외 키워드=%s, %d -> %d개",
        dislike_keywords,
        len(candidates),
        len(filtered),
    )
    return filtered


def analyze_feedback(reason: str, course: Optional[DateCourse] = None) -> FeedbackAnalysis:
    """LLM으로 거절 이유를 분석하고 새 검색 방향을 생성한다."""
    if not reason.strip():
        return FeedbackAnalysis("", [], [])

    llm_analysis = _analyze_feedback_with_gpt(reason, course)
    if llm_analysis:
        return llm_analysis
    return _analyze_feedback_with_rules(reason)


def _analyze_feedback_with_gpt(
    reason: str,
    course: Optional[DateCourse],
) -> Optional[FeedbackAnalysis]:
    """거절 이유를 구조화된 JSON으로 분석한다."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    try:
        from openai import OpenAI

        current_course = ", ".join(stop.place.name for stop in course.stops) if course else "정보 없음"
        response = OpenAI(api_key=api_key).chat.completions.create(
            model=MODEL_CONFIG[_AGENT_KEY],
            messages=[{
                "role": "user",
                "content": (
                    "데이트 코스 거절 이유를 분석해 JSON만 반환하세요.\n"
                    "exclude_keywords: 사용자가 피하고 싶은 장소/카테고리 키워드\n"
                    "search_keywords: 새로 검색해야 할 구체적인 장소/활동 키워드\n"
                    "summary: 반영할 변경 방향을 한국어 한 문장으로 요약\n"
                    "예: '공원도 좋지만 이번에는 산을 가고 싶어'라면 "
                    '{"exclude_keywords":["공원"],"search_keywords":["산","등산"],'
                    '"summary":"공원 대신 산이나 등산 코스를 찾습니다."}\n'
                    f"현재 거절된 코스 장소: {current_course}\n"
                    f"거절 이유: {reason}"
                ),
            }],
            response_format={"type": "json_object"},
            max_tokens=250,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        return FeedbackAnalysis(
            summary=str(data.get("summary", "")).strip(),
            exclude_keywords=_clean_keywords(data.get("exclude_keywords", [])),
            search_keywords=_clean_keywords(data.get("search_keywords", [])),
        )
    except Exception as e:
        logger.warning("피드백 LLM 분석 실패 — 규칙 기반 분석으로 폴백: %s", e)
        return None


def _analyze_feedback_with_rules(reason: str) -> FeedbackAnalysis:
    """자주 쓰는 대체 표현을 규칙 기반으로 분석한다."""
    exclude_keywords = _extract_dislike_keywords(reason)
    search_keywords: list[str] = []

    alternatives = {
        "산": ["산", "등산", "둘레길"],
        "전시": ["전시회", "미술관"],
        "팝업": ["팝업스토어"],
        "쇼핑": ["편집샵", "쇼핑몰"],
        "카페": ["카페"],
        "맛집": ["맛집"],
        "공원": ["공원"],
    }
    for marker, keywords in alternatives.items():
        if marker in reason and not any(marker in keyword for keyword in exclude_keywords):
            search_keywords.extend(keywords)

    if "공원" in reason and any(marker in reason for marker in ("대신", "이번에는", "말고")):
        exclude_keywords.append("공원")

    exclude_keywords = list(dict.fromkeys(exclude_keywords))
    search_keywords = [
        keyword
        for keyword in dict.fromkeys(search_keywords)
        if not any(excluded in keyword for excluded in exclude_keywords)
    ]
    if search_keywords:
        summary = f"피드백을 반영해 {', '.join(search_keywords[:3])} 관련 장소를 새로 찾습니다."
    else:
        summary = "피드백을 반영해 기존 코스와 다른 장소를 새로 찾습니다."
    return FeedbackAnalysis(summary, exclude_keywords, search_keywords)


def _clean_keywords(values) -> list[str]:
    """LLM JSON의 키워드 리스트를 정리한다."""
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))[:5]


def _handle_accepted(course: DateCourse, reason: str = "") -> None:
    """승인된 코스를 Memory Agent에 저장한다."""
    try:
        save_accepted_course(course, reason=reason)
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
        "time_slots": original_request.time_slots,
        "moods": original_request.moods,
        "food_preferences": original_request.food_preferences,
        "cafe_style": original_request.cafe_style,
        "activities": original_request.activities,
        "exclude_reason": reason,
    }
    return context


def get_model_name() -> str:
    """Feedback & Replan Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
