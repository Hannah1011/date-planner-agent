"""Memory Agent: 취향/피드백 저장 및 LLM 프롬프트 맥락 주입.

SQLite 기반 Memory Management 패턴.
"""

from pathlib import Path
from typing import Optional

from date_planner.agents.models import DateCourse
from date_planner.config.constants import Sentiment
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.memory.preference_store import (
    get_preference_summary,
    save_feedback,
    save_preference,
    save_visit,
)
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_AGENT_KEY = "memory"


def load_context(db_path: Optional[Path] = None) -> str:
    """DB에서 최근 취향 데이터를 로드해 LLM 프롬프트용 맥락 문자열을 반환한다.

    Args:
        db_path: SQLite DB 파일 경로. None이면 기본 경로 사용.

    Returns:
        취향 요약 텍스트. 데이터 없으면 빈 문자열.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    try:
        summary = get_preference_summary(**kwargs)
        if summary:
            logger.debug("취향 맥락 로드 완료 (%d자)", len(summary))
        else:
            logger.debug("저장된 취향 없음")
        return summary
    except Exception as e:
        logger.error("취향 맥락 로드 실패: %s", e)
        return ""


def save_accepted_course(
    course: DateCourse,
    reason: str = "",
    db_path: Optional[Path] = None,
) -> None:
    """승인된 코스의 방문지 및 긍정 취향 태그를 DB에 저장한다.

    Args:
        course: 사용자가 승인한 DateCourse.
        reason: 승인 이유 (사용자가 입력한 텍스트). 없으면 "코스 승인".
        db_path: SQLite DB 파일 경로. None이면 기본 경로 사용.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    preference_reason = reason.strip() if reason and reason.strip() else "코스 승인"
    for stop in course.stops:
        place = stop.place
        try:
            save_visit(
                place_name=place.name,
                category=place.category,
                district=place.district,
                rating=5,
                visited_at=_extract_date(course),
                notes=preference_reason,
                **kwargs,
            )
            save_preference(
                category=_infer_category(place.category),
                value=place.name,
                sentiment=Sentiment.POSITIVE.value,
                reason=preference_reason,
                **kwargs,
            )
        except Exception as e:
            logger.error("승인 코스 저장 실패: place=%s error=%s", place.name, e)

    logger.info("승인 코스 DB 저장 완료: %d개 장소", len(course.stops))


def save_rejected_course(
    course: DateCourse,
    reason: str,
    session_id: str,
    db_path: Optional[Path] = None,
) -> None:
    """거절된 코스 피드백을 DB에 저장한다.

    Args:
        course: 사용자가 거절한 DateCourse.
        reason: 거절 이유 텍스트.
        session_id: 세션 식별자.
        db_path: SQLite DB 파일 경로. None이면 기본 경로 사용.
    """
    kwargs = {"db_path": db_path} if db_path else {}
    try:
        save_feedback(
            session_id=session_id,
            course_summary=course.summary(),
            accepted=False,
            reason=reason,
            **kwargs,
        )
        logger.info("거절 피드백 저장 완료: session=%s", session_id)
    except Exception as e:
        logger.error("거절 피드백 저장 실패: %s", e)


def _extract_date(course: DateCourse) -> str:
    """코스 정보에서 방문 날짜를 추출한다. 없으면 오늘 날짜를 반환한다."""
    from datetime import date
    return date.today().isoformat()


def _infer_category(raw_category: str) -> str:
    """원시 카테고리 문자열에서 상위 카테고리를 추론한다.

    Args:
        raw_category: Google Places 또는 Naver 카테고리 문자열.

    Returns:
        음식점 / 카페 / 관광 / 액티비티 중 하나.
    """
    lower = raw_category.lower()
    if any(k in lower for k in ("음식", "식당", "레스토랑", "맛집", "한식", "양식", "이탈리안")):
        return "음식점"
    if any(k in lower for k in ("카페", "커피", "디저트", "베이커리")):
        return "카페"
    if any(k in lower for k in ("전시", "팝업", "체험", "액티비티")):
        return "액티비티"
    return "관광"


def get_model_name() -> str:
    """Memory Agent에 할당된 모델 이름을 반환한다."""
    return MODEL_CONFIG[_AGENT_KEY]
