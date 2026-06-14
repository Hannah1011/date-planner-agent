"""Phase 4: Guardrails 경계값 및 통합 검증 테스트."""

from datetime import date, timedelta

import pytest

from date_planner.guardrails.validators import (
    check_replan_limit,
    validate_budget,
    validate_course_size,
    validate_date,
    validate_district,
    validate_transit_time,
    validate_user_input,
)
from date_planner.config.constants import (
    MAX_COURSE_PLACES,
    MAX_REPLAN_ATTEMPTS,
    MAX_TRANSIT_MINUTES,
    MIN_COURSE_PLACES,
)


class TestValidateDistrict:
    def test_valid_district(self):
        assert validate_district("마포구") is True

    def test_all_25_districts_valid(self):
        from date_planner.config.constants import SEOUL_DISTRICTS
        for d in SEOUL_DISTRICTS:
            assert validate_district(d) is True

    def test_invalid_district(self):
        assert validate_district("없는구") is False

    def test_empty_string(self):
        assert validate_district("") is False

    def test_partial_name(self):
        assert validate_district("마포") is False


class TestValidateDate:
    def test_today_is_valid(self):
        today = date.today().isoformat()
        assert validate_date(today) is True

    def test_future_date_is_valid(self):
        future = (date.today() + timedelta(days=7)).isoformat()
        assert validate_date(future) is True

    def test_past_date_is_invalid(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        assert validate_date(past) is False

    def test_invalid_format(self):
        assert validate_date("20260614") is False

    def test_nonsense_string(self):
        assert validate_date("not-a-date") is False


class TestValidateBudget:
    def test_positive_budget(self):
        assert validate_budget(50000) is True

    def test_one_won(self):
        assert validate_budget(1) is True

    def test_zero_is_invalid(self):
        assert validate_budget(0) is False

    def test_negative_is_invalid(self):
        assert validate_budget(-1000) is False

    def test_non_int_is_invalid(self):
        assert validate_budget("50000") is False  # type: ignore[arg-type]

    def test_float_is_invalid(self):
        assert validate_budget(50000.0) is False  # type: ignore[arg-type]


class TestValidateTransitTime:
    def test_zero_minutes(self):
        assert validate_transit_time(0) is True

    def test_max_minutes(self):
        assert validate_transit_time(MAX_TRANSIT_MINUTES) is True

    def test_one_over_max(self):
        assert validate_transit_time(MAX_TRANSIT_MINUTES + 1) is False

    def test_negative_minutes(self):
        assert validate_transit_time(-1) is False


class TestValidateCourseSize:
    def test_min_size(self):
        places = ["A"] * MIN_COURSE_PLACES
        assert validate_course_size(places) is True

    def test_max_size(self):
        places = ["A"] * MAX_COURSE_PLACES
        assert validate_course_size(places) is True

    def test_below_min(self):
        places = ["A"] * (MIN_COURSE_PLACES - 1)
        assert validate_course_size(places) is False

    def test_above_max(self):
        places = ["A"] * (MAX_COURSE_PLACES + 1)
        assert validate_course_size(places) is False

    def test_empty_list(self):
        assert validate_course_size([]) is False


class TestCheckReplanLimit:
    def test_zero_attempts_allowed(self):
        assert check_replan_limit(0) is True

    def test_one_below_max_allowed(self):
        assert check_replan_limit(MAX_REPLAN_ATTEMPTS - 1) is True

    def test_at_max_not_allowed(self):
        assert check_replan_limit(MAX_REPLAN_ATTEMPTS) is False

    def test_above_max_not_allowed(self):
        assert check_replan_limit(MAX_REPLAN_ATTEMPTS + 1) is False


class TestValidateUserInput:
    def test_all_valid(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        valid, msg = validate_user_input({
            "district": "마포구",
            "date": future,
            "budget": 50000,
        })
        assert valid is True
        assert msg == ""

    def test_invalid_district_returns_error_message(self):
        future = (date.today() + timedelta(days=1)).isoformat()
        valid, msg = validate_user_input({
            "district": "없는구",
            "date": future,
            "budget": 50000,
        })
        assert valid is False
        assert "없는구" in msg

    def test_past_date_returns_error_message(self):
        past = (date.today() - timedelta(days=1)).isoformat()
        valid, msg = validate_user_input({"date": past})
        assert valid is False
        assert past in msg

    def test_zero_budget_returns_error_message(self):
        valid, msg = validate_user_input({"budget": 0})
        assert valid is False
        assert "예산" in msg

    def test_multiple_errors_joined(self):
        valid, msg = validate_user_input({
            "district": "없는구",
            "budget": -100,
        })
        assert valid is False
        assert "|" in msg

    def test_empty_dict_is_valid(self):
        valid, msg = validate_user_input({})
        assert valid is True
        assert msg == ""
