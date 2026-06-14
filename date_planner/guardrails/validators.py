"""입력 검증 및 코스 제약 검사 함수 모음.

모든 함수는 예외를 발생시키지 않고 bool 또는 tuple을 반환한다.
"""

from datetime import date

from date_planner.config.constants import (
    MAX_COURSE_PLACES,
    MAX_REPLAN_ATTEMPTS,
    MAX_TRANSIT_MINUTES,
    MIN_COURSE_PLACES,
    SEOUL_DISTRICTS,
)
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)


def validate_district(district: str) -> bool:
    """입력 지역이 서울 25개 구 중 하나인지 검증한다.

    Args:
        district: 구 이름 문자열.

    Returns:
        유효하면 True, 아니면 False.
    """
    valid = district in SEOUL_DISTRICTS
    if not valid:
        logger.warning("유효하지 않은 구 이름: %s", district)
    return valid


def validate_date(date_str: str) -> bool:
    """날짜가 오늘 이후인지 검증한다.

    Args:
        date_str: YYYY-MM-DD 형식의 날짜 문자열.

    Returns:
        오늘 이후면 True, 과거이거나 파싱 불가면 False.
    """
    try:
        target = date.fromisoformat(date_str)
        valid = target >= date.today()
        if not valid:
            logger.warning("과거 날짜 입력: %s", date_str)
        return valid
    except ValueError:
        logger.warning("날짜 파싱 실패: %s", date_str)
        return False


def validate_budget(budget: int) -> bool:
    """예산이 0 초과인지 검증한다.

    Args:
        budget: 1인 기준 예산 (원).

    Returns:
        0 초과면 True, 아니면 False.
    """
    valid = isinstance(budget, int) and budget > 0
    if not valid:
        logger.warning("유효하지 않은 예산: %s", budget)
    return valid


def validate_transit_time(minutes: int) -> bool:
    """장소 간 이동 시간이 제한 내인지 검증한다.

    Args:
        minutes: 대중교통 이동 시간(분).

    Returns:
        MAX_TRANSIT_MINUTES 이하면 True, 초과하면 False.
    """
    valid = isinstance(minutes, int) and 0 <= minutes <= MAX_TRANSIT_MINUTES
    if not valid:
        logger.warning("이동 시간 초과: %d분 (최대 %d분)", minutes, MAX_TRANSIT_MINUTES)
    return valid


def validate_course_size(places: list) -> bool:
    """코스 장소 수가 허용 범위 내인지 검증한다.

    Args:
        places: 코스를 구성하는 장소 리스트.

    Returns:
        MIN_COURSE_PLACES 이상 MAX_COURSE_PLACES 이하면 True.
    """
    count = len(places)
    valid = MIN_COURSE_PLACES <= count <= MAX_COURSE_PLACES
    if not valid:
        logger.warning(
            "코스 장소 수 범위 초과: %d개 (허용 %d~%d개)",
            count,
            MIN_COURSE_PLACES,
            MAX_COURSE_PLACES,
        )
    return valid


def check_replan_limit(attempts: int) -> bool:
    """리플랜 횟수가 제한 미만인지 확인한다.

    Args:
        attempts: 현재까지 리플랜 횟수.

    Returns:
        MAX_REPLAN_ATTEMPTS 미만이면 True, 초과하면 False.
    """
    allowed = attempts < MAX_REPLAN_ATTEMPTS
    if not allowed:
        logger.warning("리플랜 횟수 초과: %d회 (최대 %d회)", attempts, MAX_REPLAN_ATTEMPTS)
    return allowed


def validate_user_input(input_dict: dict) -> tuple[bool, str]:
    """사용자 입력 dict 전체를 통합 검증한다.

    검증 항목: district, date, budget (각각 선택적으로 포함될 수 있음).

    Args:
        input_dict: district, date, budget 키를 포함할 수 있는 dict.

    Returns:
        (유효 여부, 오류 메시지) 튜플.
        유효하면 (True, ""), 아니면 (False, 오류 메시지).
    """
    errors: list[str] = []

    district = input_dict.get("district", "")
    if district and not validate_district(district):
        errors.append(f"'{district}'은(는) 서울 25개 구에 해당하지 않습니다.")

    date_str = input_dict.get("date", "")
    if date_str and not validate_date(date_str):
        errors.append(f"'{date_str}'은(는) 유효하지 않거나 과거 날짜입니다.")

    budget = input_dict.get("budget")
    if budget is not None and not validate_budget(budget):
        errors.append(f"예산 '{budget}'은(는) 0보다 커야 합니다.")

    if errors:
        return False, " | ".join(errors)
    return True, ""
