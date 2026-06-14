"""Streamlit 메인 UI.

흐름:
  1. 지도에서 구 선택
  2. 날짜/시간대(복수)/무드/음식취향 입력
  3. 코스 생성 버튼 -> Agent 파이프라인 실행
  4. 에이전트 실행 로그 + 코스 출력 + 지도
  5. 승인(이유 입력)/거절 HITL 체크포인트
  6. 거절 시 이유 입력 -> 피드백 분석 및 새 장소 검색 -> 리플랜
  7. 하단: 취향 관리 (추가/수정/삭제)
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import os
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote_plus

import streamlit as st
from dotenv import load_dotenv

from date_planner.agents.course_narrator import generate_course_description
from date_planner.agents.feedback_replan import (
    analyze_feedback,
    apply_feedback_to_candidates,
    process_feedback,
)
from date_planner.agents.memory_agent import load_context
from date_planner.agents.route_planner import build_course
from date_planner.agents.search_agent import (
    filter_open_places,
    search_candidates,
    search_replan_candidates,
)
from date_planner.config.constants import CafeStyle, Mood, TimeSlot
from date_planner.memory.preference_store import (
    delete_preference,
    init_db,
    load_preferences_with_id,
    save_preference,
    update_preference,
)
from date_planner.tools.naver_search import search_place_suggestions
from date_planner.ui.map_selector import render_district_selector
from date_planner.utils.input_parser import parse_user_request
from date_planner.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_TIME_SLOT_LABELS = {
    TimeSlot.MORNING: "오전 (10:00~12:00)",
    TimeSlot.LUNCH: "점심 (12:00~14:00)",
    TimeSlot.AFTERNOON: "오후 (14:00~17:00)",
    TimeSlot.EVENING: "저녁 (18:00~21:00)",
    TimeSlot.NIGHT: "밤 (21:00~)",
    TimeSlot.ALL_DAY: "하루 전체",
}

_TIME_SLOT_END_HOUR = {
    TimeSlot.MORNING: 12,
    TimeSlot.LUNCH: 14,
    TimeSlot.AFTERNOON: 17,
    TimeSlot.EVENING: 21,
    TimeSlot.NIGHT: 24,
    TimeSlot.ALL_DAY: 14,
}

_ALL_TIME_SLOTS = [
    TimeSlot.MORNING,
    TimeSlot.LUNCH,
    TimeSlot.AFTERNOON,
    TimeSlot.EVENING,
    TimeSlot.NIGHT,
    TimeSlot.ALL_DAY,
]

_MOOD_LABELS = {
    Mood.NATURE_HEALING: "자연 & 힐링",
    Mood.FOOD_EXPLORATION: "맛있는 거 탐방",
    Mood.NEW_ACTIVITY: "새로운 액티비티",
    Mood.COZY_CAFE: "느긋한 카페 투어",
    Mood.SHOPPING_STREET: "쇼핑 & 거리 탐방",
}

_CAFE_STYLE_LABELS = {
    CafeStyle.COZY: "감성",
    CafeStyle.QUIET: "조용한 분위기",
    CafeStyle.LUXURY: "루프탑",
    CafeStyle.FRANCHISE: "대형 프랜차이즈",
}

_PREF_CATEGORIES = ["음식점", "카페", "액티비티", "관광", "무드", "지역", "기타"]


def main() -> None:
    """Streamlit 앱 진입점."""
    st.set_page_config(page_title="데이트 코스 플래너", layout="wide")
    _init_session_state()
    init_db()

    st.title("데이트 코스 플래너")
    st.caption("날짜, 지역, 무드를 설정하면 맞춤 데이트 코스를 추천해 드립니다.")

    with st.container(border=True):
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("지역 선택")
            district = render_district_selector()

        with col2:
            st.subheader("날짜 & 조건")
            today = date.today()
            week_end = _get_week_end(today)
            default_date = min(today + timedelta(days=1), week_end)
            selected_date = st.date_input(
                "날짜",
                value=default_date,
                min_value=today,
                max_value=week_end,
            )
            st.caption(f"오늘부터 이번 주 토요일({week_end.isoformat()})까지만 선택할 수 있습니다.")

            available_slots = _get_available_time_slots(selected_date)
            available_labels = [_TIME_SLOT_LABELS[ts] for ts in available_slots]

            st.caption("시간대 (복수 선택 가능)")
            if available_labels:
                selected_ts_labels = st.multiselect(
                    "시간대",
                    options=available_labels,
                    default=[available_labels[0]],
                    label_visibility="collapsed",
                )
                time_slots = [
                    ts for ts in available_slots
                    if _TIME_SLOT_LABELS[ts] in selected_ts_labels
                ]
                if not time_slots:
                    time_slots = available_slots[:1]
            else:
                st.warning("오늘 선택 가능한 시간대가 모두 지났습니다. 다른 날짜를 선택해 주세요.")
                time_slots = []

            st.caption("무드 (복수 선택 가능)")
            mood_options = list(_MOOD_LABELS.keys())
            mood_labels = [_MOOD_LABELS[m] for m in mood_options]
            selected_mood_labels = st.multiselect(
                "무드",
                options=mood_labels,
                default=[_MOOD_LABELS[Mood.FOOD_EXPLORATION]],
                label_visibility="collapsed",
            )
            moods = [m for m in mood_options if _MOOD_LABELS[m] in selected_mood_labels]
            if not moods:
                moods = [Mood.FOOD_EXPLORATION]

            accepts_food_input = any(
                mood in moods for mood in (Mood.FOOD_EXPLORATION, Mood.COZY_CAFE)
            )
            food_prefs = st.text_input(
                "먹고 싶은 것 (쉼표로 구분, 비우면 무드 기반 추천)",
                placeholder="파스타, 초밥",
                disabled=not accepts_food_input,
            )
            if not accepts_food_input:
                food_prefs = ""
                st.caption("맛있는 거 탐방 또는 느긋한 카페 투어 무드를 선택하면 입력할 수 있습니다.")

            accepts_cafe_style = Mood.COZY_CAFE in moods
            cafe_style = _select_enum(
                "카페 스타일",
                _CAFE_STYLE_LABELS,
                CafeStyle.COZY,
                disabled=not accepts_cafe_style,
            )
            if not accepts_cafe_style:
                cafe_style = CafeStyle.COZY
                st.caption("느긋한 카페 투어 무드를 선택하면 카페 스타일을 고를 수 있습니다.")

        submitted = st.button("코스 생성", type="primary")

    if submitted:
        if not district:
            st.warning("지역을 선택해 주세요.")
            return
        if not time_slots:
            st.warning("선택 가능한 시간대가 없습니다. 다른 날짜를 선택해 주세요.")
            return
        _generate_course(district, selected_date, time_slots, moods, food_prefs, cafe_style)

    # 에이전트 실행 로그 (항상 표시, 세션 지속)
    _render_agent_log()

    if st.session_state.get("course"):
        _render_course()
        _render_hitl()

    # 하단: 취향 관리
    st.divider()
    _render_preference_manager()


def _get_week_end(current_date: date) -> date:
    """현재 주의 토요일 날짜를 반환한다."""
    days_until_saturday = (5 - current_date.weekday()) % 7
    return current_date + timedelta(days=days_until_saturday)


def _get_available_time_slots(
    selected_date: date,
    current_time: Optional[datetime] = None,
) -> list:
    """선택한 날짜에서 선택 가능한 시간대를 반환한다.

    오늘이면 현재 시각 이후 슬롯만, 미래면 전체 슬롯 반환.
    """
    now = current_time or datetime.now()
    if selected_date > now.date():
        return list(_ALL_TIME_SLOTS)
    if selected_date < now.date():
        return []
    return [
        time_slot
        for time_slot in _ALL_TIME_SLOTS
        if time_slot != TimeSlot.ALL_DAY or now.hour < 10
        if _TIME_SLOT_END_HOUR[time_slot] > now.hour
    ]


def _generate_course(
    district: str,
    selected_date,
    time_slots: list,
    moods: list,
    food_prefs: str,
    cafe_style: CafeStyle,
) -> None:
    """코스 생성 파이프라인을 실행하고 session_state에 결과를 저장한다."""
    food_list = [f.strip() for f in food_prefs.split(",") if f.strip()]

    raw_input = {
        "district": district,
        "date": selected_date.isoformat(),
        "time_slots": [ts.value for ts in time_slots],
        "moods": [m.value for m in moods],
        "food_preferences": food_list,
        "cafe_style": cafe_style.value,
    }

    try:
        request = parse_user_request(raw_input)
    except ValueError as e:
        st.error(f"입력 오류: {e}")
        return

    agent_log = []

    try:
        with st.status("에이전트 파이프라인 실행 중...", expanded=True) as status:
            # Step 1: Memory Agent
            st.write("**[1/4] Memory Agent** — 취향 맥락 로드 중...")
            context = load_context()
            if context:
                result1 = f"취향 맥락 {len(context)}자 로드 완료"
                st.caption(f"  {result1}")
            else:
                result1 = "저장된 취향 없음 (코스 승인 시 학습됩니다)"
                st.caption(f"  {result1}")
            agent_log.append(("Memory Agent", "취향 맥락 로드", result1))

            # Step 2: Search Agent
            st.write("**[2/4] Search Agent** — 선택 무드별 장소를 병렬 검색 중...")
            detail_conditions = []
            if food_list:
                detail_conditions.append(f"먹고 싶은 것: {', '.join(food_list)}")
            if Mood.COZY_CAFE in moods:
                detail_conditions.append(f"카페 스타일: {_CAFE_STYLE_LABELS[cafe_style]}")
            detail_text = f" / 상세 조건: {' / '.join(detail_conditions)}" if detail_conditions else ""
            st.caption(f"  선택 무드별 전용 검색어{detail_text}")
            candidates = search_candidates(request)
            open_candidates = filter_open_places(candidates, request.date)
            food_cnt = sum(1 for c in open_candidates if c.category_type == "food")
            cafe_cnt = sum(1 for c in open_candidates if c.category_type == "cafe")
            act_cnt = sum(1 for c in open_candidates if c.category_type == "activity")
            result2 = f"후보 {len(open_candidates)}개 수집 (음식 {food_cnt}개 / 카페 {cafe_cnt}개 / 액티비티 {act_cnt}개)"
            mood_counts = {
                mood: sum(1 for c in open_candidates if mood.value in c.mood_tags)
                for mood in moods
            }
            mood_result = " / ".join(f"{_MOOD_LABELS[m]} {count}개" for m, count in mood_counts.items())
            if mood_result:
                result2 += f" / 무드별: {mood_result}"
            st.caption(f"  {result2}")
            agent_log.append(("Search Agent", f"Naver+Google 장소 검색 ({district})", result2))

            # Step 3: Route Planner Agent
            st.write("**[3/4] Route Planner Agent** — 무드별 장소 보장 + 이동 시간 최적화 중...")
            course = build_course(open_candidates, request)
            if course.stops:
                included_moods = {
                    mood.value
                    for mood in moods
                    if any(mood.value in stop.place.mood_tags for stop in course.stops)
                }
                result3 = (
                    f"{len(course.stops)}개 장소 확정 / "
                    f"무드 반영 {len(included_moods)}/{len(moods)} / "
                    f"이동 {course.total_transit_minutes}분"
                )
                if course.weather_note:
                    result3 += f" / 날씨: {course.weather_note}"
            else:
                result3 = "코스 구성 실패 (후보 부족)"
            st.caption(f"  {result3}")
            agent_log.append(("Route Planner Agent", "최적 동선 구성 + 날씨 체크", result3))

            # Step 4: Course Narrator Agent (GPT-4o-mini)
            if course.stops:
                st.write("**[4/4] Course Narrator Agent** — 취향 기반 코스 인사이트 생성 중...")
                description = generate_course_description(course, request, context)
                st.session_state["course_description"] = description
                result4 = "코스 설명 생성 완료"
                st.caption(f"  {result4}")
                agent_log.append(("Course Narrator Agent", "저장 취향 기반 코스 인사이트 생성", result4))
                status.update(
                    label=f"코스 완성! {len(course.stops)}개 장소 / 이동 {course.total_transit_minutes}분",
                    state="complete",
                )
            else:
                status.update(label="조건에 맞는 장소를 찾지 못했습니다.", state="error")

    except Exception as e:
        logger.error("코스 생성 실패: %s", e)
        st.error("코스 생성 중 오류가 발생했습니다. 다시 시도해 주세요.")
        return

    st.session_state["agent_log"] = agent_log

    if not course.stops:
        st.warning("조건에 맞는 장소를 찾지 못했습니다. 조건을 바꿔 보세요.")
        return

    st.session_state["course"] = course
    st.session_state["request"] = request
    st.session_state["candidates"] = open_candidates
    st.session_state["replan_count"] = st.session_state.get("replan_count", 0)
    st.session_state.pop("show_approval_form", None)
    st.session_state.pop("show_reject_form", None)


def _render_agent_log() -> None:
    """세션에 저장된 에이전트 실행 로그를 표시한다."""
    log = st.session_state.get("agent_log", [])
    if not log:
        return

    with st.expander("에이전트 실행 로그", expanded=False):
        for i, (agent, detail, result) in enumerate(log, 1):
            cols = st.columns([2, 3, 4])
            cols[0].caption(f"**{agent}**")
            cols[1].caption(detail)
            cols[2].caption(f"→ {result}")
        if not any(agent == "Feedback & Replan Agent" for agent, _, _ in log):
            st.caption("Feedback & Replan Agent는 코스를 거절했을 때만 실행됩니다.")


def _render_course() -> None:
    """저장된 코스를 화면에 출력하고 지도에 핀과 경로선을 표시한다."""
    course = st.session_state["course"]

    st.divider()
    st.subheader("추천 코스")

    description = st.session_state.get("course_description", "")
    if description:
        st.info(description)

    if course.weather_note:
        st.info(f"날씨: {course.weather_note}")

    request = st.session_state.get("request")
    if request:
        missing_moods = [
            mood for mood in request.moods
            if not any(mood.value in stop.place.mood_tags for stop in course.stops)
        ]
        if missing_moods:
            labels = ", ".join(_MOOD_LABELS[mood] for mood in missing_moods)
            st.warning(f"검색 결과가 없어 코스에 포함하지 못한 무드: {labels}")

    _render_course_map(course)

    st.markdown("---")
    for stop in course.stops:
        with st.container(border=True):
            col_num, col_info = st.columns([1, 8])
            with col_num:
                st.markdown(f"### {stop.visit_order}")
            with col_info:
                st.markdown(f"**{stop.place.name}**")
                st.caption(stop.place.address)
                st.markdown(f"[Google Map 지도 보기]({_google_maps_search_url(stop.place.name, stop.place.address)})")
                if stop.transit_minutes_from_prev:
                    st.caption(f"이전 장소에서 {stop.transit_minutes_from_prev}분")

    st.metric("총 이동 시간", f"{course.total_transit_minutes}분")

    if course.total_transit_minutes == 0 and len(course.stops) > 1:
        st.caption(
            "이동 시간이 0분으로 표시됩니다. "
            "Google Directions API REQUEST_DENIED 상태입니다. "
            "Google Cloud Console에서 Directions API 활성화 및 결제 계정 연결을 확인하세요."
        )


def _render_course_map(course) -> None:
    """코스 장소를 Folium 지도에 번호 핀과 경로선으로 표시한다."""
    try:
        import folium
        from streamlit_folium import st_folium

        stops_with_coords = [
            s for s in course.stops
            if s.place.lat != 0.0 and s.place.lon != 0.0
        ]

        if stops_with_coords:
            center_lat = sum(s.place.lat for s in stops_with_coords) / len(stops_with_coords)
            center_lon = sum(s.place.lon for s in stops_with_coords) / len(stops_with_coords)
            zoom = 14
        else:
            center_lat, center_lon = 37.5665, 126.9780
            zoom = 13

        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="CartoDB positron")

        line_coords = []
        for stop in stops_with_coords:
            lat, lon = stop.place.lat, stop.place.lon
            bg_color = "#e74c3c" if stop.visit_order == 1 else "#3498db"

            folium.Marker(
                location=[lat, lon],
                icon=folium.DivIcon(
                    html=(
                        f'<div style="font-size:13px;color:white;background:{bg_color};'
                        f'border-radius:50%;width:28px;height:28px;line-height:28px;'
                        f'text-align:center;font-weight:bold;box-shadow:0 2px 4px rgba(0,0,0,0.3)">'
                        f'{stop.visit_order}</div>'
                    ),
                    icon_size=(28, 28),
                    icon_anchor=(14, 14),
                ),
                popup=folium.Popup(
                    f"<b>{stop.visit_order}. {stop.place.name}</b>"
                    f"<br><small>{stop.place.address}</small>"
                    f"<br>카테고리: {stop.place.category}",
                    max_width=220,
                ),
                tooltip=f"{stop.visit_order}. {stop.place.name}",
            ).add_to(m)
            line_coords.append([lat, lon])

        if len(line_coords) > 1:
            folium.PolyLine(line_coords, color="#3498db", weight=3, opacity=0.7, dash_array="8").add_to(m)

        if not stops_with_coords:
            st.caption("지도 좌표를 가져오지 못한 장소는 핀 표시가 생략됩니다.")

        st_folium(m, width="100%", height=420, returned_objects=[])

    except Exception as e:
        logger.warning("코스 지도 렌더링 생략: %s", e)


def _render_hitl() -> None:
    """승인/거절 HITL 체크포인트를 렌더링한다."""
    st.divider()
    st.subheader("이 코스가 마음에 드시나요?")
    course = st.session_state["course"]
    request = st.session_state["request"]
    replan_count = st.session_state.get("replan_count", 0)

    col_yes, col_no = st.columns(2)

    with col_yes:
        if st.button("승인", type="primary", use_container_width=True):
            st.session_state["show_approval_form"] = True
            st.session_state.pop("show_reject_form", None)

    with col_no:
        if st.button("거절 & 리플랜", use_container_width=True):
            st.session_state["show_reject_form"] = True
            st.session_state.pop("show_approval_form", None)

    # 승인 폼
    if st.session_state.get("show_approval_form"):
        st.text_area(
            "어떤 점이 좋으셨나요? (선택 사항)",
            key="approval_reason",
            placeholder="예: 카페 분위기가 좋았어요, 이동 거리가 편했어요",
        )
        if st.button("코스 저장", type="primary"):
            approval_reason = st.session_state.get("approval_reason", "")
            result = process_feedback(course, True, approval_reason, replan_count, request)
            if result.accepted:
                st.success("코스가 저장되었습니다. 즐거운 데이트 되세요!")
                _clear_course_state()
                st.rerun()

    # 거절 폼
    if st.session_state.get("show_reject_form"):
        reason = st.text_area("거절 이유를 입력해 주세요", key="reject_reason")
        if st.button("리플랜 요청"):
            if not reason.strip():
                st.warning("이유를 입력해야 리플랜이 가능합니다.")
                return

            result = process_feedback(course, False, reason, replan_count, request)

            if result.suggest_new_conditions:
                st.warning(f"리플랜을 {replan_count}회 시도했습니다. 날짜나 지역을 변경해 보세요.")
                _clear_course_state()
                return

            candidates = st.session_state.get("candidates", [])
            before_names = {c.name for c in candidates}
            current_course_names = {stop.place.name for stop in course.stops}
            analysis = analyze_feedback(reason, course)
            filtered = apply_feedback_to_candidates(
                candidates,
                reason,
                excluded_place_names=current_course_names,
                analysis=analysis,
            )
            fresh_candidates = apply_feedback_to_candidates(
                filter_open_places(
                    search_replan_candidates(request, analysis.search_keywords),
                    request.date,
                ),
                reason,
                excluded_place_names=current_course_names,
                analysis=analysis,
            )
            combined_by_name = {candidate.name: candidate for candidate in fresh_candidates}
            for candidate in filtered:
                combined_by_name.setdefault(candidate.name, candidate)
            replanning_candidates = list(combined_by_name.values())
            after_names = {c.name for c in filtered}
            excluded = before_names - after_names

            # 리플랜 로그 업데이트
            agent_log = st.session_state.get("agent_log", [])
            feedback_result = analysis.summary
            if excluded:
                feedback_result += f" / 기존 장소 {len(excluded)}개 제외"
            feedback_result += f" / 새 후보 {len(fresh_candidates)}개 검색"
            agent_log.append((
                "Feedback & Replan Agent",
                f"거절 이유 분석: '{reason[:40]}...' " if len(reason) > 40 else f"거절 이유 분석: '{reason}'",
                feedback_result,
            ))

            with st.status("리플랜 중...", expanded=True) as status:
                st.write("**Feedback & Replan Agent** — 거절 이유 반영 중...")
                st.caption(f"  {analysis.summary}")
                if analysis.search_keywords:
                    st.caption(f"  새 검색어: {', '.join(analysis.search_keywords)}")
                st.caption(f"  기존 코스 장소 제외 후 새 후보 {len(fresh_candidates)}개 수집")

                st.write("**Route Planner Agent** — 조건 반영 후 코스 재구성 중...")
                try:
                    new_course = build_course(replanning_candidates, request)
                    replan_result = (
                        f"{len(new_course.stops)}개 장소 / "
                        f"이동 {new_course.total_transit_minutes}분"
                    )
                    st.caption(f"  {replan_result}")
                    agent_log.append(("Route Planner Agent", "리플랜 코스 구성", replan_result))
                    status.update(label="리플랜 완료!", state="complete")
                except Exception as e:
                    logger.error("리플랜 실패: %s", e)
                    st.error("리플랜 중 오류가 발생했습니다.")
                    return

                if new_course.stops:
                    st.write("**Course Narrator Agent** — 피드백 반영 설명 생성 중...")
                    context = load_context()
                    description = generate_course_description(
                        new_course,
                        request,
                        context,
                        feedback_reason=reason,
                    )
                    st.session_state["course_description"] = description
                    agent_log.append((
                        "Course Narrator Agent",
                        "리플랜 피드백 반영 코스 인사이트 생성",
                        "피드백 반영 설명 생성 완료",
                    ))

            st.session_state["agent_log"] = agent_log
            st.session_state["course"] = new_course
            st.session_state["candidates"] = replanning_candidates
            st.session_state["replan_count"] = result.replan_count
            st.session_state.pop("show_reject_form", None)
            st.rerun()


def _render_preference_manager() -> None:
    """하단: 취향 데이터 조회 + 추가/수정/삭제 UI."""
    st.subheader("취향 관리")
    st.caption("코스 승인 시 자동으로 학습되며, 직접 추가/수정/삭제할 수 있습니다.")

    notice = st.session_state.pop("preference_notice", None)
    if notice:
        notice_type, message = notice
        if notice_type == "success":
            st.success(message)
        else:
            st.error(message)

    prefs = load_preferences_with_id()
    pos_prefs = [p for p in prefs if p["sentiment"] == "positive"]
    neg_prefs = [p for p in prefs if p["sentiment"] == "negative"]

    editing_id = st.session_state.get("editing_pref_id")

    # 수정 폼 (인라인)
    if editing_id:
        editing_pref = next((p for p in prefs if p["id"] == editing_id), None)
        if editing_pref:
            st.markdown("**수정 중:**")
            with st.form("edit_pref_form"):
                new_value = st.text_input("장소명 / 항목", value=editing_pref["value"])
                new_cat = st.selectbox(
                    "카테고리",
                    options=_PREF_CATEGORIES,
                    index=_PREF_CATEGORIES.index(editing_pref["category"])
                    if editing_pref["category"] in _PREF_CATEGORIES else 0,
                )
                new_sentiment = st.radio(
                    "느낌",
                    ["좋아요", "별로예요"],
                    index=0 if editing_pref["sentiment"] == "positive" else 1,
                    horizontal=True,
                )
                new_reason = st.text_input("이유", value=editing_pref.get("reason", ""))
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.form_submit_button("저장", type="primary"):
                        update_preference(
                            editing_id,
                            new_cat,
                            new_value,
                            "positive" if new_sentiment == "좋아요" else "negative",
                            new_reason,
                        )
                        st.session_state.pop("editing_pref_id", None)
                        st.rerun()
                with col_cancel:
                    if st.form_submit_button("취소"):
                        st.session_state.pop("editing_pref_id", None)
                        st.rerun()

    # 두 컬럼: 좋아하는 것 / 별로인 것
    col_pos, col_neg = st.columns(2)

    with col_pos:
        st.markdown("**좋아하는 것**")
        if not pos_prefs:
            st.caption("없음")
        for p in pos_prefs:
            reason_str = f" — {p['reason']}" if p.get("reason") else ""
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"- {p['category']}: **{p['value']}**{reason_str}")
            if c2.button("수정", key=f"edit_{p['id']}"):
                st.session_state["editing_pref_id"] = p["id"]
                st.rerun()
            if c3.button("삭제", key=f"del_{p['id']}"):
                deleted = delete_preference(p["id"])
                st.session_state["preference_notice"] = (
                    ("success", f"DB 반영 완료: '{p['value']}' 취향을 삭제했습니다.")
                    if deleted
                    else ("error", f"'{p['value']}' 취향을 삭제하지 못했습니다.")
                )
                st.rerun()

    with col_neg:
        st.markdown("**별로인 것**")
        if not neg_prefs:
            st.caption("없음")
        for p in neg_prefs:
            reason_str = f" — {p['reason']}" if p.get("reason") else ""
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"- {p['category']}: **{p['value']}**{reason_str}")
            if c2.button("수정", key=f"edit_{p['id']}"):
                st.session_state["editing_pref_id"] = p["id"]
                st.rerun()
            if c3.button("삭제", key=f"del_{p['id']}"):
                deleted = delete_preference(p["id"])
                st.session_state["preference_notice"] = (
                    ("success", f"DB 반영 완료: '{p['value']}' 취향을 삭제했습니다.")
                    if deleted
                    else ("error", f"'{p['value']}' 취향을 삭제하지 못했습니다.")
                )
                st.rerun()

    # 새 취향 추가
    st.markdown("---")
    with st.expander("새 취향 추가"):
        new_place_query = st.text_input(
            "장소명 검색",
            placeholder="예: 연남동 파스타집",
            key="new_pref_query",
        )
        if st.button("장소 검색", key="search_pref_place"):
            if new_place_query.strip():
                st.session_state["preference_place_suggestions"] = search_place_suggestions(
                    new_place_query.strip()
                )
                st.session_state.pop("selected_preference_place", None)
            else:
                st.warning("검색할 장소명을 입력해 주세요.")

        suggestions = st.session_state.get("preference_place_suggestions", [])
        selected_place = st.session_state.get("selected_preference_place")
        if suggestions:
            st.markdown("**검색 결과에서 장소를 선택하세요.**")
            with st.container(height=300):
                for idx, suggestion in enumerate(suggestions):
                    if st.button(
                        suggestion["name"],
                        key=f"select_pref_place_{idx}_{suggestion.get('place_id', '')}",
                        use_container_width=True,
                    ):
                        st.session_state["selected_preference_place"] = suggestion
                        st.rerun()
                    st.caption(
                        suggestion["address"] or "주소 정보 없음"
                    )
                    st.divider()
        elif new_place_query:
            st.caption("검색 결과가 없습니다. 다른 키워드로 검색해 주세요.")

        if selected_place:
            st.success(f"선택한 장소: {selected_place['name']}")
            st.caption(selected_place["address"])

        with st.form("add_pref_form"):
            new_cat = st.selectbox("카테고리", options=_PREF_CATEGORIES)
            new_sent = st.radio("느낌", ["좋아요", "별로예요"], horizontal=True)
            new_reason = st.text_input("이유 (선택)", placeholder="예: 분위기가 좋아서")
            if st.form_submit_button("추가"):
                if selected_place:
                    save_preference(
                        category=new_cat,
                        value=selected_place["name"],
                        sentiment="positive" if new_sent == "좋아요" else "negative",
                        reason=new_reason.strip(),
                    )
                    st.session_state.pop("preference_place_suggestions", None)
                    st.session_state.pop("selected_preference_place", None)
                    st.success(f"'{selected_place['name']}' 취향이 추가되었습니다.")
                    st.rerun()
                else:
                    st.warning("검색 결과에서 장소를 선택해 주세요.")


def _clear_course_state() -> None:
    """코스 관련 session_state를 초기화한다."""
    for key in ("course", "candidates", "course_description",
                "show_approval_form", "show_reject_form",
                "approval_reason", "reject_reason"):
        st.session_state.pop(key, None)
    st.session_state["replan_count"] = 0


def _google_maps_search_url(place_name: str, address: str) -> str:
    """장소명과 주소를 사용하는 Google Maps 검색 URL을 반환한다."""
    query = quote_plus(" ".join(part for part in (place_name, address) if part))
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def _select_enum(label: str, label_map: dict, default, disabled: bool = False) -> object:
    """Enum 값을 selectbox로 선택한다."""
    options = list(label_map.keys())
    labels = [label_map[o] for o in options]
    default_idx = options.index(default) if default in options else 0
    selected_label = st.selectbox(label, options=labels, index=default_idx, disabled=disabled)
    for enum_val, lbl in label_map.items():
        if lbl == selected_label:
            return enum_val
    return default


def _init_session_state() -> None:
    """session_state 초기값을 설정한다."""
    defaults = {
        "course": None,
        "request": None,
        "candidates": [],
        "replan_count": 0,
        "show_reject_form": False,
        "show_approval_form": False,
        "agent_log": [],
        "editing_pref_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


if __name__ == "__main__":
    main()
