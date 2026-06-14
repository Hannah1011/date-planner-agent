"""데이트 코스 플래너 — CLI 실행 진입점.

사용법:
    python main.py              # 샘플 입력으로 코스 생성
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from date_planner.agents.feedback_replan import apply_feedback_to_candidates, process_feedback
from date_planner.agents.course_narrator import generate_course_description
from date_planner.utils.input_parser import build_search_query, parse_user_request
from date_planner.agents.memory_agent import load_context
from date_planner.agents.route_planner import build_course, is_within_budget
from date_planner.agents.search_agent import filter_open_places, search_candidates
from date_planner.config.constants import CafeStyle, Mood, TimeSlot
from date_planner.memory.preference_store import init_db
from date_planner.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_SAMPLE_INPUT = {
    "district": "마포구",
    "date": (date.today() + timedelta(days=1)).isoformat(),
    "time_slots": [TimeSlot.AFTERNOON.value],
    "moods": [Mood.FOOD_EXPLORATION.value],
    "food_preferences": ["파스타"],
    "cafe_style": CafeStyle.COZY.value,
    "activities": [],
}


def run(raw_input: dict) -> None:
    """데이트 코스 생성 파이프라인을 실행한다.

    Input Parser -> Memory -> Search -> Route Planner -> Course Narrator -> Feedback
    순서로 실행하며, 사용자 입력이 없는 CLI 모드에서는 자동 승인한다.

    Args:
        raw_input: 사용자 조건 dict.
    """
    # Step 1: 입력 검증 및 구조화
    _step(1, "Input Parser", "사용자 입력 파싱 및 유효성 검증")
    try:
        request = parse_user_request(raw_input)
        time_slots_str = ", ".join(ts.value for ts in request.time_slots)
        moods_str = ", ".join(m.value for m in request.moods)
        _step_ok(f"{request.district} / {request.date} / [{time_slots_str}] / [{moods_str}]")
    except ValueError as e:
        logger.error("입력 오류: %s", e)
        sys.exit(1)

    # Step 2: 취향 맥락 로드
    _step(2, "Memory Agent", "SQLite에서 최근 취향 맥락 로드")
    preference_context = load_context()
    if preference_context:
        _step_ok(f"{len(preference_context)}자 맥락 로드")
        print(f"\n{preference_context}")
    else:
        _step_ok("저장된 취향 없음 (첫 실행이거나 DB 비어있음)")

    # Step 3: 장소 검색
    _step(3, "Search Agent", "네이버 검색 → Google Places 병렬 조회")
    candidates = search_candidates(request)
    open_candidates = filter_open_places(candidates)
    _step_ok(f"후보 {len(candidates)}개 수집, 영업 중 {len(open_candidates)}개")

    if not open_candidates:
        print("\n영업 중인 장소를 찾지 못했습니다. 조건을 변경해 주세요.")
        return

    # Step 4 ~: 코스 구성 + HITL 루프
    replan_count = 0
    current_candidates = open_candidates

    while True:
        label = f"리플랜 {replan_count}회차" if replan_count > 0 else "첫 생성"
        _step(4 + replan_count, "Route Planner Agent", f"이동 시간 최적화 + 날씨 반영 ({label})")
        course = build_course(current_candidates, request)

        if not course.stops:
            logger.warning("생성된 코스 없음 — 종료")
            print("\n조건에 맞는 코스를 생성할 수 없습니다. 조건을 변경해 주세요.")
            break

        _step_ok(f"{len(course.stops)}개 장소, 이동 {course.total_transit_minutes}분, 예상 {course.total_estimated_cost:,}원")
        _print_course(course, replan_count)

        _step(5 + replan_count, "Course Narrator Agent", "저장 취향 기반 코스 인사이트 생성")
        description = generate_course_description(course, request, preference_context)
        _step_ok(description)

        # CLI 모드: 자동 승인 (UI 없음)
        _step(6 + replan_count, "Feedback & Replan Agent", "CLI 모드 — 자동 승인 처리")
        result = process_feedback(course, True, "", replan_count, request)
        if result.accepted:
            _step_ok("Memory Agent에 방문 기록 및 취향 태그 저장 완료")
            print("\n코스가 저장되었습니다.")
            break

        if result.suggest_new_conditions:
            print("\n리플랜 횟수를 초과했습니다. 날짜나 지역을 변경해 보세요.")
            break

        current_candidates = apply_feedback_to_candidates(current_candidates, result.reason)
        replan_count = result.replan_count


def _step(num: int, agent: str, detail: str) -> None:
    """에이전트 실행 단계를 콘솔에 출력한다."""
    bar = "─" * 50
    print(f"\n{bar}")
    print(f"  [Step {num}]  {agent}")
    print(f"           {detail}")
    print(bar)


def _step_ok(result: str) -> None:
    """단계 완료 결과를 콘솔에 출력한다."""
    print(f"  ✓ {result}")


def _print_course(course, replan_count: int) -> None:
    """코스 정보를 콘솔에 출력한다."""
    suffix = f" (리플랜 {replan_count}회)" if replan_count > 0 else ""
    print(f"\n{'=' * 50}")
    print(f"추천 데이트 코스{suffix}")
    print(f"{'=' * 50}")

    if course.weather_note:
        print(f"날씨: {course.weather_note}\n")

    for stop in course.stops:
        transit_str = f"  (이전 장소에서 {stop.transit_minutes_from_prev}분)" if stop.transit_minutes_from_prev else ""
        print(f"{stop.visit_order}. {stop.place.name}{transit_str}")
        print(f"   주소: {stop.place.address}")
        print(f"   카테고리: {stop.place.category} | 별점: {stop.place.rating}")
        print(f"   예상 비용: {stop.estimated_cost:,}원")

    print(f"\n총 이동 시간: {course.total_transit_minutes}분")
    print(f"총 예상 비용: {course.total_estimated_cost:,}원")
    print(f"{'=' * 50}")


def main() -> None:
    """메인 진입점."""
    try:
        init_db()
    except Exception as e:
        logger.error("DB 초기화 실패: %s", e)
        sys.exit(1)

    run(_SAMPLE_INPUT)


if __name__ == "__main__":
    main()
