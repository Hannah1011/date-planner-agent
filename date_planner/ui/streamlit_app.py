"""Streamlit 메인 UI.

흐름:
  1. 지도에서 구 선택
  2. 날짜/시간대/무드/음식취향/예산 입력
  3. 코스 생성 버튼 -> Agent 파이프라인 실행
  4. 코스 출력 + 지도 마커 표시
  5. 승인/거절 HITL 체크포인트
  6. 거절 시 이유 입력 -> 리플랜
"""

import os
from datetime import date, timedelta
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

from date_planner.agents.feedback_replan import apply_feedback_to_candidates, process_feedback
from date_planner.agents.input_collector import parse_user_request
from date_planner.agents.memory_agent import load_context
from date_planner.agents.route_planner import build_course
from date_planner.agents.search_agent import filter_open_places, search_candidates
from date_planner.config.constants import CafeStyle, Mood, TimeSlot
from date_planner.memory.preference_store import init_db
from date_planner.ui.map_selector import render_district_selector
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


def main() -> None:
    """Streamlit 앱 진입점."""
    st.set_page_config(page_title="데이트 코스 플래너", layout="wide")
    _init_session_state()
    init_db()

    st.title("데이트 코스 플래너")
    st.caption("날짜, 지역, 무드를 설정하면 맞춤 데이트 코스를 추천해 드립니다.")

    # 취향 맥락 사이드바
    _render_preference_sidebar()

    # 입력 폼
    with st.form("course_form"):
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("지역 선택")
            district = render_district_selector()

        with col2:
            st.subheader("날짜 & 조건")
            selected_date = st.date_input(
                "날짜",
                value=date.today() + timedelta(days=1),
                min_value=date.today(),
            )
            time_slot = _select_enum("시간대", _TIME_SLOT_LABELS, TimeSlot.AFTERNOON)
            mood = _select_enum("무드", _MOOD_LABELS, Mood.FOOD_EXPLORATION)
            food_prefs = st.text_input("먹고 싶은 것 (쉼표로 구분)", placeholder="파스타, 카페")
            cafe_style = _select_enum("카페 스타일", _CAFE_STYLE_LABELS, CafeStyle.COZY)
            budget = st.number_input("예산 (원, 1인 기준)", min_value=10000, step=5000, value=60000)

        submitted = st.form_submit_button("코스 생성", type="primary")

    if submitted:
        if not district:
            st.warning("지역을 선택해 주세요.")
            return
        _generate_course(district, selected_date, time_slot, mood, food_prefs, cafe_style, int(budget))

    # 코스 출력 및 HITL
    if st.session_state.get("course"):
        _render_course()
        _render_hitl()


def _generate_course(
    district: str,
    selected_date,
    time_slot: TimeSlot,
    mood: Mood,
    food_prefs: str,
    cafe_style: CafeStyle,
    budget: int,
) -> None:
    """코스 생성 파이프라인을 실행하고 session_state에 결과를 저장한다."""
    food_list = [f.strip() for f in food_prefs.split(",") if f.strip()]

    raw_input = {
        "district": district,
        "date": selected_date.isoformat(),
        "time_slot": time_slot.value,
        "mood": mood.value,
        "food_preferences": food_list,
        "cafe_style": cafe_style.value,
        "budget": budget,
    }

    try:
        request = parse_user_request(raw_input)
    except ValueError as e:
        st.error(f"입력 오류: {e}")
        return

    with st.spinner("코스를 구성하고 있습니다..."):
        try:
            candidates = search_candidates(request)
            open_candidates = filter_open_places(candidates)
            course = build_course(open_candidates, request)
        except Exception as e:
            logger.error("코스 생성 실패: %s", e)
            st.error("코스 생성 중 오류가 발생했습니다. 다시 시도해 주세요.")
            return

    if not course.stops:
        st.warning("조건에 맞는 장소를 찾지 못했습니다. 조건을 바꿔 보세요.")
        return

    st.session_state["course"] = course
    st.session_state["request"] = request
    st.session_state["candidates"] = open_candidates
    st.session_state["replan_count"] = st.session_state.get("replan_count", 0)


def _render_course() -> None:
    """저장된 코스를 화면에 출력하고 Folium 지도에 마커를 표시한다."""
    course = st.session_state["course"]

    st.divider()
    st.subheader("추천 코스")

    if course.weather_note:
        st.info(f"날씨: {course.weather_note}")

    for stop in course.stops:
        with st.container(border=True):
            col_num, col_info = st.columns([1, 8])
            with col_num:
                st.markdown(f"### {stop.visit_order}")
            with col_info:
                st.markdown(f"**{stop.place.name}**")
                st.caption(f"{stop.place.address} | {stop.place.category}")
                if stop.transit_minutes_from_prev:
                    st.caption(f"이전 장소에서 {stop.transit_minutes_from_prev}분")
                cols = st.columns(3)
                cols[0].metric("별점", f"{stop.place.rating}")
                cols[1].metric("예상 비용", f"{stop.estimated_cost:,}원")
                cols[2].metric("가격대", "₩" * max(1, stop.place.price_level))

    st.metric("총 이동 시간", f"{course.total_transit_minutes}분")
    st.metric("총 예상 비용", f"{course.total_estimated_cost:,}원")

    _render_course_map(course)


def _render_course_map(course) -> None:
    """코스 장소를 Folium 지도에 마커로 표시한다."""
    try:
        import folium
        from streamlit_folium import st_folium

        m = folium.Map(location=[37.5665, 126.9780], zoom_start=13, tiles="CartoDB positron")
        for stop in course.stops:
            folium.Marker(
                location=[37.5665, 126.9780],
                popup=f"{stop.visit_order}. {stop.place.name}",
                tooltip=stop.place.name,
                icon=folium.Icon(color="red" if stop.visit_order == 1 else "blue", icon="info-sign"),
            ).add_to(m)
        st_folium(m, width=700, height=350, returned_objects=[])
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
            result = process_feedback(course, True, "", replan_count, request)
            if result.accepted:
                st.success("코스가 저장되었습니다. 즐거운 데이트 되세요!")
                st.session_state.pop("course", None)
                st.session_state.pop("candidates", None)
                st.session_state["replan_count"] = 0

    with col_no:
        if st.button("거절 & 리플랜", use_container_width=True):
            st.session_state["show_reject_form"] = True

    if st.session_state.get("show_reject_form"):
        reason = st.text_area("거절 이유를 입력해 주세요", key="reject_reason")
        if st.button("리플랜 요청"):
            if not reason.strip():
                st.warning("이유를 입력해야 리플랜이 가능합니다.")
                return

            result = process_feedback(course, False, reason, replan_count, request)

            if result.suggest_new_conditions:
                st.warning(
                    f"리플랜을 {replan_count}회 시도했습니다. 날짜나 지역을 변경해 보세요."
                )
                st.session_state.pop("course", None)
                st.session_state["replan_count"] = 0
                st.session_state.pop("show_reject_form", None)
                return

            candidates = st.session_state.get("candidates", [])
            filtered = apply_feedback_to_candidates(candidates, reason)

            with st.spinner("리플랜 중..."):
                try:
                    new_course = build_course(filtered, request)
                except Exception as e:
                    logger.error("리플랜 실패: %s", e)
                    st.error("리플랜 중 오류가 발생했습니다.")
                    return

            st.session_state["course"] = new_course
            st.session_state["candidates"] = filtered
            st.session_state["replan_count"] = result.replan_count
            st.session_state.pop("show_reject_form", None)
            st.rerun()


def _render_preference_sidebar() -> None:
    """사이드바에 현재 저장된 취향 요약을 표시한다."""
    with st.sidebar:
        st.header("내 취향")
        context = load_context()
        if context:
            st.text(context)
        else:
            st.caption("저장된 취향이 없습니다. 코스를 승인하면 취향이 학습됩니다.")


def _select_enum(label: str, label_map: dict, default) -> object:
    """Enum 값을 selectbox로 선택한다.

    Args:
        label: selectbox 레이블.
        label_map: Enum -> 표시 레이블 dict.
        default: 기본 선택값.

    Returns:
        선택된 Enum 인스턴스.
    """
    options = list(label_map.keys())
    labels = [label_map[o] for o in options]
    default_idx = options.index(default) if default in options else 0
    selected_label = st.selectbox(label, options=labels, index=default_idx)
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
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


if __name__ == "__main__":
    main()
