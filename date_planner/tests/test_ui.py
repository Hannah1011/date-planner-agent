"""Streamlit UI 날짜 및 시간대 선택 규칙 테스트."""

from datetime import date, datetime

from date_planner.config.constants import TimeSlot
from date_planner.ui.streamlit_app import _get_available_time_slots, _get_week_end


def test_week_end_from_sunday_is_upcoming_saturday():
    assert _get_week_end(date(2026, 6, 14)) == date(2026, 6, 20)


def test_week_end_from_saturday_is_same_day():
    assert _get_week_end(date(2026, 6, 20)) == date(2026, 6, 20)


def test_today_evening_only_keeps_evening_and_night():
    now = datetime(2026, 6, 14, 18, 9)
    slots = _get_available_time_slots(now.date(), now)
    assert slots == [TimeSlot.EVENING, TimeSlot.NIGHT]


def test_today_after_evening_keeps_night_only():
    now = datetime(2026, 6, 14, 21, 0)
    slots = _get_available_time_slots(now.date(), now)
    assert slots == [TimeSlot.NIGHT]


def test_future_date_allows_all_time_slots():
    now = datetime(2026, 6, 14, 18, 9)
    slots = _get_available_time_slots(date(2026, 6, 15), now)
    assert TimeSlot.ALL_DAY in slots
    assert len(slots) == 6


def test_past_date_has_no_available_slots():
    now = datetime(2026, 6, 14, 18, 9)
    assert _get_available_time_slots(date(2026, 6, 13), now) == []
