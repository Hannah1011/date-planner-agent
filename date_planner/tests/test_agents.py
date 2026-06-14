"""Phase 5: Agent 입출력 타입 및 예외처리 테스트 (LLM 호출 없음)."""

import os
from datetime import date, timedelta
from pathlib import Path

import pytest

from date_planner.agents.models import (
    CourseStop,
    DateCourse,
    PlaceCandidate,
    UserRequest,
)
from date_planner.agents.input_collector import parse_user_request, build_search_query
from date_planner.agents.search_agent import search_candidates, filter_open_places
from date_planner.agents.route_planner import build_course, is_within_budget
from date_planner.agents.memory_agent import load_context, save_accepted_course
from date_planner.agents.feedback_replan import process_feedback, apply_feedback_to_candidates
from date_planner.config.constants import CafeStyle, Mood, TimeSlot


@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")


@pytest.fixture
def sample_request() -> UserRequest:
    future = (date.today() + timedelta(days=1)).isoformat()
    return UserRequest(
        district="마포구",
        date=future,
        time_slot=TimeSlot.AFTERNOON,
        mood=Mood.FOOD_EXPLORATION,
        food_preferences=["파스타", "카페"],
        cafe_style=CafeStyle.COZY,
        budget=60000,
    )


@pytest.fixture
def sample_candidates() -> list[PlaceCandidate]:
    return [
        PlaceCandidate(
            name="연남동 파스타집",
            address="서울 마포구 연남동 123",
            category="음식점>이탈리안",
            rating=4.5,
            is_open=True,
            price_level=2,
        ),
        PlaceCandidate(
            name="상수 감성 카페",
            address="서울 마포구 상수동 56",
            category="카페>커피전문점",
            rating=4.2,
            is_open=True,
            price_level=1,
        ),
        PlaceCandidate(
            name="폐점된 가게",
            address="서울 마포구 연남동 99",
            category="음식점",
            rating=3.0,
            is_open=False,
            price_level=1,
        ),
    ]


@pytest.fixture
def sample_course(sample_candidates) -> DateCourse:
    stops = [
        CourseStop(place=sample_candidates[0], transit_minutes_from_prev=0, estimated_cost=25000, visit_order=1),
        CourseStop(place=sample_candidates[1], transit_minutes_from_prev=15, estimated_cost=15000, visit_order=2),
    ]
    return DateCourse(
        stops=stops,
        total_transit_minutes=15,
        total_estimated_cost=40000,
        weather_note="맑음 22.0°C",
        session_id="test-session-001",
    )


class TestInputCollector:
    def test_parse_valid_input(self, sample_request):
        future = sample_request.date
        raw = {
            "district": "마포구",
            "date": future,
            "time_slot": "AFTERNOON",
            "mood": "FOOD_EXPLORATION",
            "food_preferences": ["파스타"],
            "cafe_style": "COZY",
            "budget": 60000,
        }
        result = parse_user_request(raw)
        assert isinstance(result, UserRequest)
        assert result.district == "마포구"
        assert result.time_slot == TimeSlot.AFTERNOON

    def test_parse_invalid_district_raises(self):
        with pytest.raises(ValueError):
            parse_user_request({"district": "없는구", "date": "2030-01-01", "budget": 50000})

    def test_parse_past_date_raises(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        with pytest.raises(ValueError):
            parse_user_request({"district": "마포구", "date": past, "budget": 50000})

    def test_unknown_time_slot_defaults_to_all_day(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        result = parse_user_request({
            "district": "마포구",
            "date": future,
            "time_slot": "UNKNOWN_SLOT",
            "budget": 50000,
        })
        assert result.time_slot == TimeSlot.ALL_DAY

    def test_build_search_query_with_preferences(self, sample_request):
        query = build_search_query(sample_request)
        assert "마포구" in query
        assert "파스타" in query

    def test_build_search_query_without_preferences(self, sample_request):
        sample_request.food_preferences = []
        query = build_search_query(sample_request)
        assert "마포구" in query
        assert "맛집" in query


class TestSearchAgent:
    def test_search_candidates_returns_list(self, sample_request):
        result = search_candidates(sample_request)
        assert isinstance(result, list)

    def test_each_candidate_is_place_candidate(self, sample_request):
        results = search_candidates(sample_request)
        for item in results:
            assert isinstance(item, PlaceCandidate)

    def test_each_candidate_has_name(self, sample_request):
        results = search_candidates(sample_request)
        for item in results:
            assert item.name

    def test_filter_open_places_excludes_closed(self, sample_candidates):
        open_only = filter_open_places(sample_candidates)
        assert all(c.is_open for c in open_only)
        assert len(open_only) == 2

    def test_filter_open_places_empty_input(self):
        assert filter_open_places([]) == []


class TestRoutePlanner:
    def test_build_course_returns_date_course(self, sample_candidates, sample_request):
        course = build_course(sample_candidates, sample_request)
        assert isinstance(course, DateCourse)

    def test_build_course_has_stops(self, sample_candidates, sample_request):
        course = build_course(sample_candidates, sample_request)
        assert len(course.stops) >= 1

    def test_build_course_empty_candidates(self, sample_request):
        course = build_course([], sample_request)
        assert isinstance(course, DateCourse)
        assert len(course.stops) == 0

    def test_stops_have_order(self, sample_candidates, sample_request):
        course = build_course(sample_candidates, sample_request)
        for i, stop in enumerate(course.stops):
            assert stop.visit_order == i + 1

    def test_is_within_budget_true(self, sample_course):
        assert is_within_budget(sample_course, 100000) is True

    def test_is_within_budget_false(self, sample_course):
        assert is_within_budget(sample_course, 10000) is False

    def test_course_summary_returns_string(self, sample_course):
        summary = sample_course.summary()
        assert isinstance(summary, str)
        assert "연남동 파스타집" in summary

    def test_weather_note_populated(self, sample_candidates, sample_request):
        course = build_course(sample_candidates, sample_request)
        assert isinstance(course.weather_note, str)


class TestMemoryAgent:
    def test_load_context_returns_string(self, tmp_path):
        result = load_context(db_path=tmp_path / "test.db")
        assert isinstance(result, str)

    def test_load_context_empty_when_no_data(self, tmp_path):
        result = load_context(db_path=tmp_path / "empty.db")
        assert result == ""

    def test_save_accepted_course_does_not_raise(self, sample_course, tmp_path):
        db = tmp_path / "pref.db"
        from date_planner.memory.preference_store import init_db
        init_db(db)
        save_accepted_course(sample_course, db_path=db)


class TestFeedbackReplan:
    def test_accepted_returns_true(self, sample_course, sample_request):
        result = process_feedback(sample_course, True, "", 0, sample_request)
        assert result.accepted is True
        assert result.suggest_new_conditions is False

    def test_rejected_increments_count(self, sample_course, sample_request):
        result = process_feedback(sample_course, False, "카페가 너무 시끄러웠어요", 0, sample_request)
        assert result.accepted is False
        assert result.replan_count == 1

    def test_rejected_no_reason_does_not_increment(self, sample_course, sample_request):
        result = process_feedback(sample_course, False, "", 0, sample_request)
        assert result.replan_count == 0

    def test_exceeded_replan_limit_suggests_new_conditions(self, sample_course, sample_request):
        from date_planner.config.constants import MAX_REPLAN_ATTEMPTS
        result = process_feedback(
            sample_course, False, "전부 별로예요", MAX_REPLAN_ATTEMPTS, sample_request
        )
        assert result.suggest_new_conditions is True

    def test_apply_feedback_returns_list(self, sample_candidates):
        result = apply_feedback_to_candidates(sample_candidates, "파스타가 별로야")
        assert isinstance(result, list)

    def test_apply_feedback_empty_reason_unchanged(self, sample_candidates):
        result = apply_feedback_to_candidates(sample_candidates, "")
        assert result == sample_candidates
