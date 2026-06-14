"""Phase 5: Agent 입출력 타입 및 예외처리 테스트.

tool 함수를 monkeypatch로 대체해 LLM·HTTP 호출 없이 검증한다.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from date_planner.agents.models import CourseStop, DateCourse, PlaceCandidate, UserRequest
from date_planner.agents.input_collector import parse_user_request, build_search_query
from date_planner.agents.search_agent import (
    _build_queries,
    _enrich_candidates,
    search_candidates,
    filter_open_places,
)
from date_planner.agents.route_planner import build_course, is_within_budget
from date_planner.agents.memory_agent import load_context, save_accepted_course
from date_planner.agents.course_narrator import generate_course_description
from date_planner.agents.feedback_replan import process_feedback, apply_feedback_to_candidates
from date_planner.config.constants import CafeStyle, Mood, TimeSlot


# --- Mock 반환 데이터 ---

_MOCK_NAVER_RESULTS = [
    {"name": "연남동 파스타집", "address": "서울 마포구 연남동 123-4",
     "category": "음식점>이탈리안", "link": "https://example.com/a", "lat": 37.5609, "lon": 126.9237},
    {"name": "상수 감성 카페", "address": "서울 마포구 상수동 56-7",
     "category": "카페>커피전문점", "link": "https://example.com/b", "lat": 37.5481, "lon": 126.9228},
]

_MOCK_PLACE_DETAILS = {
    "place_id": "ChIJmock001",
    "rating": 4.2,
    "price_level": 2,
    "opening_hours": {"open_now": True, "periods": [], "weekday_text": []},
    "reviews": [{"rating": 5, "text": "좋아요", "author_name": "테스터", "relative_time_description": "1달 전"}],
    "lat": 37.5609,
    "lon": 126.9237,
}

_MOCK_WEATHER = {"condition": "맑음", "temperature": 22.0, "precipitation_probability": 10}


@pytest.fixture(autouse=True)
def mock_tools(monkeypatch):
    """모든 외부 API 호출을 monkeypatch로 대체한다."""
    monkeypatch.setattr("date_planner.agents.search_agent.search_places",
                        lambda q, display=5: _MOCK_NAVER_RESULTS)
    monkeypatch.setattr("date_planner.agents.search_agent.get_place_details",
                        lambda name, addr: _MOCK_PLACE_DETAILS)
    monkeypatch.setattr("date_planner.agents.search_agent.is_place_open_now",
                        lambda pid: True)
    monkeypatch.setattr("date_planner.agents.route_planner.get_transit_duration",
                        lambda o, d: 20)
    monkeypatch.setattr("date_planner.agents.route_planner.get_weather",
                        lambda dist, dt: _MOCK_WEATHER)
    monkeypatch.setattr("date_planner.agents.feedback_replan.save_accepted_course",
                        lambda course, reason="": None)
    monkeypatch.setattr("date_planner.agents.feedback_replan.save_rejected_course",
                        lambda course, reason, session_id: None)


@pytest.fixture
def sample_request() -> UserRequest:
    future = (date.today() + timedelta(days=1)).isoformat()
    return UserRequest(
        district="마포구",
        date=future,
        time_slots=[TimeSlot.AFTERNOON],
        moods=[Mood.FOOD_EXPLORATION],
        food_preferences=["파스타", "카페"],
        cafe_style=CafeStyle.COZY,
    )


@pytest.fixture
def sample_candidates() -> list[PlaceCandidate]:
    return [
        PlaceCandidate(name="연남동 파스타집", address="서울 마포구 연남동 123",
                       category="음식점>이탈리안", rating=4.5, is_open=True, price_level=2),
        PlaceCandidate(name="상수 감성 카페", address="서울 마포구 상수동 56",
                       category="카페>커피전문점", rating=4.2, is_open=True, price_level=1),
        PlaceCandidate(name="폐점된 가게", address="서울 마포구 연남동 99",
                       category="음식점", rating=3.0, is_open=False, price_level=1),
    ]


@pytest.fixture
def sample_course(sample_candidates) -> DateCourse:
    stops = [
        CourseStop(place=sample_candidates[0], transit_minutes_from_prev=0,
                   estimated_cost=25000, visit_order=1),
        CourseStop(place=sample_candidates[1], transit_minutes_from_prev=15,
                   estimated_cost=15000, visit_order=2),
    ]
    return DateCourse(stops=stops, total_transit_minutes=15, total_estimated_cost=40000,
                      weather_note="맑음 22.0°C", session_id="test-session-001")


class TestInputCollector:
    def test_parse_valid_input(self, sample_request):
        future = sample_request.date
        raw = {"district": "마포구", "date": future, "time_slots": ["AFTERNOON"],
               "moods": ["FOOD_EXPLORATION"], "food_preferences": ["파스타"],
               "cafe_style": "COZY"}
        result = parse_user_request(raw)
        assert isinstance(result, UserRequest)
        assert result.district == "마포구"
        assert TimeSlot.AFTERNOON in result.time_slots
        assert Mood.FOOD_EXPLORATION in result.moods

    def test_parse_invalid_district_raises(self):
        with pytest.raises(ValueError):
            parse_user_request({"district": "없는구", "date": "2030-01-01", "budget": 50000})

    def test_parse_past_date_raises(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        with pytest.raises(ValueError):
            parse_user_request({"district": "마포구", "date": past, "budget": 50000})

    def test_unknown_time_slot_defaults_to_all_day(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        result = parse_user_request({"district": "마포구", "date": future,
                                     "time_slots": ["UNKNOWN"]})
        assert TimeSlot.ALL_DAY in result.time_slots

    def test_legacy_mood_single_value(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        result = parse_user_request({"district": "마포구", "date": future,
                                     "mood": "NATURE_HEALING"})
        assert Mood.NATURE_HEALING in result.moods

    def test_moods_list_multiple(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        result = parse_user_request({"district": "마포구", "date": future,
                                     "moods": ["FOOD_EXPLORATION", "COZY_CAFE"]})
        assert len(result.moods) == 2

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
        for item in search_candidates(sample_request):
            assert isinstance(item, PlaceCandidate)

    def test_each_candidate_has_name(self, sample_request):
        for item in search_candidates(sample_request):
            assert item.name

    def test_filter_open_places_excludes_closed(self, sample_candidates):
        open_only = filter_open_places(sample_candidates)
        assert all(c.is_open for c in open_only)
        assert len(open_only) == 2

    def test_filter_open_places_empty_input(self):
        assert filter_open_places([]) == []

    def test_build_queries_searches_popup_and_shopping_for_selected_moods(self, sample_request):
        sample_request.moods = [Mood.NEW_ACTIVITY, Mood.SHOPPING_STREET]
        queries = _build_queries(sample_request)
        query_text = " ".join(query for query, _, _ in queries)
        assert "팝업스토어" in query_text
        assert "전시회" in query_text
        assert "편집샵" in query_text
        assert "쇼핑몰" in query_text

    def test_activity_search_excludes_restaurant_results(self):
        raw_results = [
            (
                {"name": "소금구이집", "address": "서울 성동구", "category": "음식점>한식"},
                "activity",
                Mood.SHOPPING_STREET.value,
            ),
            (
                {"name": "성수 편집샵", "address": "서울 성동구", "category": "쇼핑>패션"},
                "activity",
                Mood.SHOPPING_STREET.value,
            ),
        ]
        result = _enrich_candidates(raw_results)
        assert [candidate.name for candidate in result] == ["성수 편집샵"]


class TestRoutePlanner:
    def test_build_course_returns_date_course(self, sample_candidates, sample_request):
        assert isinstance(build_course(sample_candidates, sample_request), DateCourse)

    def test_build_course_has_stops(self, sample_candidates, sample_request):
        assert len(build_course(sample_candidates, sample_request).stops) >= 1

    def test_build_course_empty_candidates(self, sample_request):
        course = build_course([], sample_request)
        assert len(course.stops) == 0

    def test_stops_have_correct_order(self, sample_candidates, sample_request):
        for i, stop in enumerate(build_course(sample_candidates, sample_request).stops):
            assert stop.visit_order == i + 1

    def test_is_within_budget_true(self, sample_course):
        assert is_within_budget(sample_course, 100000) is True

    def test_is_within_budget_false(self, sample_course):
        assert is_within_budget(sample_course, 10000) is False

    def test_course_summary_contains_place_name(self, sample_course):
        assert "연남동 파스타집" in sample_course.summary()

    def test_weather_note_is_string(self, sample_candidates, sample_request):
        assert isinstance(build_course(sample_candidates, sample_request).weather_note, str)

    def test_includes_at_least_one_place_for_each_selected_mood(self, sample_request):
        sample_request.time_slots = [TimeSlot.MORNING]
        sample_request.moods = [
            Mood.FOOD_EXPLORATION,
            Mood.SHOPPING_STREET,
            Mood.NEW_ACTIVITY,
        ]
        candidates = [
            PlaceCandidate(
                name="맛집", address="서울 마포구 1", category="음식점",
                rating=0, is_open=True, price_level=0, category_type="food",
                mood_tags=[Mood.FOOD_EXPLORATION.value],
            ),
            PlaceCandidate(
                name="편집샵", address="서울 마포구 2", category="쇼핑",
                rating=0, is_open=True, price_level=0, category_type="activity",
                mood_tags=[Mood.SHOPPING_STREET.value],
            ),
            PlaceCandidate(
                name="팝업스토어", address="서울 마포구 3", category="문화",
                rating=0, is_open=True, price_level=0, category_type="activity",
                mood_tags=[Mood.NEW_ACTIVITY.value],
            ),
        ]
        course = build_course(candidates, sample_request)
        included_tags = {tag for stop in course.stops for tag in stop.place.mood_tags}
        assert all(mood.value in included_tags for mood in sample_request.moods)

    def test_does_not_fill_course_with_multiple_restaurants(self, sample_request):
        sample_request.time_slots = [TimeSlot.ALL_DAY]
        sample_request.moods = [
            Mood.FOOD_EXPLORATION,
            Mood.SHOPPING_STREET,
            Mood.NEW_ACTIVITY,
        ]
        candidates = [
            PlaceCandidate(
                name="맛집", address="서울 성동구 1", category="음식점",
                rating=0, is_open=True, price_level=0, category_type="food",
                mood_tags=[Mood.FOOD_EXPLORATION.value],
            ),
            PlaceCandidate(
                name="편집샵", address="서울 성동구 2", category="쇼핑",
                rating=0, is_open=True, price_level=0, category_type="activity",
                mood_tags=[Mood.SHOPPING_STREET.value],
            ),
            PlaceCandidate(
                name="팝업스토어", address="서울 성동구 3", category="문화",
                rating=0, is_open=True, price_level=0, category_type="activity",
                mood_tags=[Mood.NEW_ACTIVITY.value],
            ),
            PlaceCandidate(
                name="한식집", address="서울 성동구 4", category="음식점",
                rating=0, is_open=True, price_level=0, category_type="food",
            ),
            PlaceCandidate(
                name="고깃집", address="서울 성동구 5", category="음식점",
                rating=0, is_open=True, price_level=0, category_type="food",
            ),
            PlaceCandidate(
                name="카페", address="서울 성동구 6", category="카페",
                rating=0, is_open=True, price_level=0, category_type="cafe",
            ),
        ]
        course = build_course(candidates, sample_request)
        food_count = sum(stop.place.category_type == "food" for stop in course.stops)
        assert food_count == 1


class TestMemoryAgent:
    def test_load_context_returns_string(self, tmp_path):
        assert isinstance(load_context(db_path=tmp_path / "test.db"), str)

    def test_load_context_empty_when_no_data(self, tmp_path):
        assert load_context(db_path=tmp_path / "empty.db") == ""

    def test_save_accepted_course_does_not_raise(self, sample_course, tmp_path):
        db = tmp_path / "pref.db"
        from date_planner.memory.preference_store import init_db
        init_db(db)
        save_accepted_course(sample_course, db_path=db)


class TestCourseNarrator:
    def test_template_analyzes_saved_preferences(self, sample_course, sample_request, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        description = generate_course_description(
            sample_course,
            sample_request,
            "사용자 취향 정보:\n- 선호:\n  * 카페: 감성 카페",
        )
        assert description.startswith("저장된 취향과 이번 선택을 분석해보니")
        assert "그래서 이번 코스는" in description
        assert description.endswith(".")

    def test_template_does_not_claim_saved_preferences_when_empty(
        self, sample_course, sample_request, monkeypatch
    ):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        description = generate_course_description(sample_course, sample_request)
        assert description.startswith("이번 선택을 분석해보니")


class TestFeedbackReplan:
    def test_accepted_returns_true(self, sample_course, sample_request):
        result = process_feedback(sample_course, True, "", 0, sample_request)
        assert result.accepted is True
        assert result.suggest_new_conditions is False

    def test_rejected_increments_count(self, sample_course, sample_request):
        result = process_feedback(sample_course, False, "카페가 시끄러웠어요", 0, sample_request)
        assert result.accepted is False
        assert result.replan_count == 1

    def test_rejected_no_reason_does_not_increment(self, sample_course, sample_request):
        result = process_feedback(sample_course, False, "", 0, sample_request)
        assert result.replan_count == 0

    def test_exceeded_limit_suggests_new_conditions(self, sample_course, sample_request):
        from date_planner.config.constants import MAX_REPLAN_ATTEMPTS
        result = process_feedback(sample_course, False, "전부 별로예요",
                                  MAX_REPLAN_ATTEMPTS, sample_request)
        assert result.suggest_new_conditions is True

    def test_apply_feedback_returns_list(self, sample_candidates):
        assert isinstance(apply_feedback_to_candidates(sample_candidates, "파스타가 별로야"), list)

    def test_apply_feedback_empty_reason_unchanged(self, sample_candidates):
        assert apply_feedback_to_candidates(sample_candidates, "") == sample_candidates
