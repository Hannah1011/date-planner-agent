"""Phase 3: API 도구 Mock 응답 스키마 및 예외처리 테스트."""

import os
import unittest.mock as mock

import pytest
import requests

from date_planner.tools.naver_search import search_places
from date_planner.tools.google_places import get_place_details, is_place_open_now
from date_planner.tools.weather import get_weather
from date_planner.tools.directions import get_transit_duration, _deterministic_mock_minutes
from date_planner.tools.crawler import get_break_time_info


@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch):
    """모든 테스트에서 Mock 모드를 강제 활성화한다."""
    monkeypatch.setenv("USE_MOCK", "true")


class TestNaverSearch:
    def test_returns_list(self):
        result = search_places("마포구 파스타")
        assert isinstance(result, list)

    def test_returns_up_to_display_count(self):
        result = search_places("마포구 카페", display=3)
        assert len(result) <= 3

    def test_each_item_has_required_keys(self):
        result = search_places("마포구 음식점")
        for item in result:
            assert "name" in item
            assert "address" in item
            assert "category" in item
            assert "link" in item

    def test_returns_empty_list_on_api_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("NAVER_CLIENT_ID", "test_id")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "test_secret")
        with mock.patch("requests.get", side_effect=requests.RequestException("timeout")):
            result = search_places("마포구 파스타")
        assert result == []

    def test_returns_empty_list_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
        result = search_places("마포구 파스타")
        assert result == []


class TestGooglePlaces:
    def test_get_details_returns_dict(self):
        result = get_place_details("연남동 파스타집", "서울 마포구 연남동")
        assert isinstance(result, dict)

    def test_get_details_has_required_keys(self):
        result = get_place_details("연남동 파스타집", "서울 마포구 연남동")
        for key in ("place_id", "rating", "price_level", "opening_hours", "reviews"):
            assert key in result

    def test_rating_is_float(self):
        result = get_place_details("테스트 카페", "서울 마포구")
        assert isinstance(result["rating"], float)

    def test_is_open_returns_bool(self):
        result = is_place_open_now("mock_place_id_001")
        assert isinstance(result, bool)

    def test_is_open_mock_returns_true(self):
        assert is_place_open_now("any_id") is True

    def test_returns_empty_on_api_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake_key")
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_place_details("카페", "서울")
        assert result == {}

    def test_returns_empty_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
        result = get_place_details("카페", "서울")
        assert result == {}


class TestWeather:
    def test_returns_dict(self):
        result = get_weather("마포구", "2026-06-15")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = get_weather("마포구", "2026-06-15")
        assert "condition" in result
        assert "temperature" in result
        assert "precipitation_probability" in result

    def test_temperature_is_numeric(self):
        result = get_weather("강남구", "2026-06-15")
        assert isinstance(result["temperature"], (int, float))

    def test_precipitation_probability_is_int(self):
        result = get_weather("종로구", "2026-06-15")
        assert isinstance(result["precipitation_probability"], int)

    def test_returns_empty_on_api_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "fake_key")
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_weather("마포구", "2026-06-15")
        assert result == {}

    def test_returns_empty_for_unknown_district(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "fake_key")
        result = get_weather("없는구", "2026-06-15")
        assert result == {}


class TestDirections:
    def test_returns_int(self):
        result = get_transit_duration("서울 마포구 연남동", "서울 마포구 홍대입구역")
        assert isinstance(result, int)

    def test_mock_within_range(self):
        result = get_transit_duration("A", "B")
        assert 15 <= result <= 45

    def test_deterministic_same_input_same_output(self):
        r1 = get_transit_duration("연남동", "홍대입구역")
        r2 = get_transit_duration("연남동", "홍대입구역")
        assert r1 == r2

    def test_different_inputs_may_differ(self):
        r1 = _deterministic_mock_minutes("A", "B")
        r2 = _deterministic_mock_minutes("C", "D")
        # 두 값이 다를 가능성이 높음 (해시 충돌 아닌 이상)
        # 최소한 둘 다 범위 내에 있어야 함
        assert 15 <= r1 <= 45
        assert 15 <= r2 <= 45

    def test_returns_negative_one_on_api_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.setenv("GOOGLE_DIRECTIONS_API_KEY", "fake_key")
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_transit_duration("A", "B")
        assert result == -1

    def test_returns_negative_one_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.delenv("GOOGLE_DIRECTIONS_API_KEY", raising=False)
        result = get_transit_duration("A", "B")
        assert result == -1


class TestCrawler:
    def test_returns_dict(self):
        result = get_break_time_info("연남동 파스타집", "서울 마포구 연남동")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = get_break_time_info("테스트 식당", "서울 마포구")
        for key in ("has_break_time", "break_start", "break_end", "last_order"):
            assert key in result

    def test_mock_has_no_break_time(self):
        result = get_break_time_info("아무 식당", "서울 강남구")
        assert result["has_break_time"] is False

    def test_returns_default_on_request_error(self, monkeypatch):
        monkeypatch.setenv("USE_MOCK", "false")
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_break_time_info("카페", "서울")
        assert result["has_break_time"] is False
