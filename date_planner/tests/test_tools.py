"""Phase 3: API 도구 응답 스키마 및 예외처리 테스트.

requests.get을 mock해 실제 HTTP 호출 없이 검증한다.
"""

import unittest.mock as mock
from unittest.mock import MagicMock

import pytest
import requests

from date_planner.tools.naver_search import search_places
from date_planner.tools.google_places import (
    get_place_details,
    is_place_open_now,
    search_place_suggestions,
)
from date_planner.tools.weather import get_weather
from date_planner.tools.directions import get_transit_duration
from date_planner.tools.crawler import get_break_time_info


def _make_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """requests.Response를 흉내내는 Mock 객체를 생성한다."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


# --- 네이버 검색 ---

_NAVER_JSON = {
    "items": [
        {"title": "연남동 <b>파스타</b>집", "roadAddress": "서울 마포구 연남동 123-4",
         "category": "음식점>이탈리안", "link": "https://example.com/a"},
        {"title": "상수 감성 카페", "roadAddress": "서울 마포구 상수동 56-7",
         "category": "카페>커피전문점", "link": "https://example.com/b"},
        {"title": "홍대 레스토랑", "roadAddress": "서울 마포구 서교동 89-1",
         "category": "음식점>양식", "link": "https://example.com/c"},
    ]
}


class TestNaverSearch:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("NAVER_CLIENT_ID", "test_id")
        monkeypatch.setenv("NAVER_CLIENT_SECRET", "test_secret")

    def test_returns_list(self):
        with mock.patch("requests.get", return_value=_make_response(_NAVER_JSON)):
            result = search_places("마포구 파스타")
        assert isinstance(result, list)

    def test_returns_up_to_display_count(self):
        two_item_json = {"items": _NAVER_JSON["items"][:2]}
        with mock.patch("requests.get", return_value=_make_response(two_item_json)):
            result = search_places("마포구 카페", display=2)
        assert len(result) == 2

    def test_each_item_has_required_keys(self):
        with mock.patch("requests.get", return_value=_make_response(_NAVER_JSON)):
            result = search_places("마포구 음식점")
        for item in result:
            assert "name" in item
            assert "address" in item
            assert "category" in item
            assert "link" in item

    def test_strips_html_tags_from_name(self):
        with mock.patch("requests.get", return_value=_make_response(_NAVER_JSON)):
            result = search_places("파스타")
        assert "<b>" not in result[0]["name"]

    def test_returns_empty_list_on_api_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("timeout")):
            result = search_places("마포구 파스타")
        assert result == []

    def test_returns_empty_list_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
        monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
        result = search_places("마포구 파스타")
        assert result == []


# --- Google Places ---

_FIND_PLACE_JSON = {"candidates": [{"place_id": "ChIJmock001"}]}
_PLACE_DETAILS_JSON = {
    "result": {
        "place_id": "ChIJmock001",
        "rating": 4.2,
        "price_level": 2,
        "opening_hours": {
            "open_now": True,
            "periods": [],
            "weekday_text": ["월요일: 10:00 – 22:00"],
        },
        "reviews": [{"rating": 5, "text": "맛있어요"}],
    }
}
_OPEN_NOW_JSON = {"result": {"opening_hours": {"open_now": True}}}
_TEXT_SEARCH_JSON = {
    "results": [
        {
            "name": "연남동 파스타집",
            "formatted_address": "서울 마포구 연남동 123-4",
            "place_id": "ChIJmock001",
        },
        {
            "name": "연남 파스타",
            "formatted_address": "서울 마포구 연남동 55-6",
            "place_id": "ChIJmock002",
        },
    ]
}


class TestGooglePlaces:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "test_key")

    def test_get_details_returns_dict(self):
        with mock.patch("requests.get", side_effect=[
            _make_response(_FIND_PLACE_JSON),
            _make_response(_PLACE_DETAILS_JSON),
        ]):
            result = get_place_details("연남동 파스타집", "서울 마포구 연남동")
        assert isinstance(result, dict)

    def test_get_details_has_required_keys(self):
        with mock.patch("requests.get", side_effect=[
            _make_response(_FIND_PLACE_JSON),
            _make_response(_PLACE_DETAILS_JSON),
        ]):
            result = get_place_details("연남동 파스타집", "서울 마포구 연남동")
        for key in ("place_id", "opening_hours", "lat", "lon"):
            assert key in result

    def test_does_not_request_rating_or_price_level(self):
        with mock.patch("requests.get", side_effect=[
            _make_response(_FIND_PLACE_JSON),
            _make_response(_PLACE_DETAILS_JSON),
        ]) as mock_get:
            get_place_details("카페", "서울 마포구")
        fields = mock_get.call_args_list[1].kwargs["params"]["fields"]
        assert "rating" not in fields
        assert "price_level" not in fields
        assert "reviews" not in fields

    def test_is_open_returns_bool(self):
        with mock.patch("requests.get", return_value=_make_response(_OPEN_NOW_JSON)):
            result = is_place_open_now("ChIJmock001")
        assert isinstance(result, bool)

    def test_is_open_returns_true_when_open(self):
        with mock.patch("requests.get", return_value=_make_response(_OPEN_NOW_JSON)):
            assert is_place_open_now("ChIJmock001") is True

    def test_returns_empty_on_api_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_place_details("카페", "서울")
        assert result == {}

    def test_returns_empty_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
        result = get_place_details("카페", "서울")
        assert result == {}

    def test_is_open_defaults_true_on_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = is_place_open_now("ChIJmock001")
        assert result is True

    def test_search_place_suggestions_returns_name_and_address(self):
        with mock.patch("requests.get", return_value=_make_response(_TEXT_SEARCH_JSON)):
            result, notice = search_place_suggestions("연남동 파스타")
        assert result[0]["name"] == "연남동 파스타집"
        assert result[0]["address"] == "서울 마포구 연남동 123-4"
        assert notice == ""

    def test_search_place_suggestions_falls_back_to_naver_on_google_denied(self):
        denied = {"status": "REQUEST_DENIED", "error_message": "not authorized", "results": []}
        naver_result = [{"name": "약수역", "address": "서울 중구", "category": "지하철역"}]
        with mock.patch("requests.get", return_value=_make_response(denied)):
            with mock.patch(
                "date_planner.tools.google_places.search_places",
                return_value=naver_result,
            ):
                result, notice = search_place_suggestions("약수")
        assert result[0]["name"] == "약수역"
        assert result[0]["source"] == "Naver Local Search"
        assert "권한 오류" in notice


# --- 날씨 ---

_WEATHER_JSON = {
    "list": [
        {
            "dt_txt": "2030-06-15 12:00:00",
            "weather": [{"description": "맑음"}],
            "main": {"temp": 22.5},
            "pop": 0.1,
        }
    ]
}


class TestWeather:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "test_key")

    def test_returns_dict(self):
        with mock.patch("requests.get", return_value=_make_response(_WEATHER_JSON)):
            result = get_weather("마포구", "2030-06-15")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        with mock.patch("requests.get", return_value=_make_response(_WEATHER_JSON)):
            result = get_weather("마포구", "2030-06-15")
        assert "condition" in result
        assert "temperature" in result
        assert "precipitation_probability" in result

    def test_temperature_is_numeric(self):
        with mock.patch("requests.get", return_value=_make_response(_WEATHER_JSON)):
            result = get_weather("강남구", "2030-06-15")
        assert isinstance(result["temperature"], (int, float))

    def test_precipitation_is_int(self):
        with mock.patch("requests.get", return_value=_make_response(_WEATHER_JSON)):
            result = get_weather("종로구", "2030-06-15")
        assert isinstance(result["precipitation_probability"], int)

    def test_returns_empty_on_api_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_weather("마포구", "2030-06-15")
        assert result == {}

    def test_unknown_district_falls_back_to_seoul(self):
        with mock.patch("requests.get", return_value=_make_response(_WEATHER_JSON)):
            result = get_weather("없는구", "2030-06-15")
        assert isinstance(result, dict)
        assert "condition" in result

    def test_returns_empty_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)
        result = get_weather("마포구", "2030-06-15")
        assert result == {}


# --- Directions ---

_DIRECTIONS_JSON = {
    "routes": [{"legs": [{"duration": {"value": 1200}}]}]
}


class TestDirections:
    @pytest.fixture(autouse=True)
    def set_env(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DIRECTIONS_API_KEY", "test_key")

    def test_returns_int(self):
        with mock.patch("requests.get", return_value=_make_response(_DIRECTIONS_JSON)):
            result = get_transit_duration("서울 마포구 연남동", "서울 마포구 홍대입구역")
        assert isinstance(result, int)

    def test_returns_correct_minutes(self):
        with mock.patch("requests.get", return_value=_make_response(_DIRECTIONS_JSON)):
            result = get_transit_duration("A", "B")
        assert result == 20  # 1200초 / 60 = 20분

    def test_returns_negative_one_on_api_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_transit_duration("A", "B")
        assert result == -1

    def test_returns_negative_one_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DIRECTIONS_API_KEY", raising=False)
        result = get_transit_duration("A", "B")
        assert result == -1

    def test_returns_negative_one_when_no_routes(self):
        with mock.patch("requests.get", return_value=_make_response({"routes": []})):
            result = get_transit_duration("A", "B")
        assert result == -1


# --- 크롤러 ---

_BREAK_TIME_HTML = """
<html><body>
브레이크타임 14:00 - 17:00 라스트 오더 21:30
</body></html>
"""


class TestCrawler:
    def test_returns_dict(self):
        with mock.patch("requests.get", return_value=_make_response({})) as m:
            m.return_value.text = "<html><body></body></html>"
            m.return_value.raise_for_status.return_value = None
            result = get_break_time_info("카페", "서울 마포구")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        with mock.patch("requests.get") as m:
            m.return_value.raise_for_status.return_value = None
            m.return_value.text = "<html><body></body></html>"
            result = get_break_time_info("카페", "서울 마포구")
        for key in ("has_break_time", "break_start", "break_end", "last_order"):
            assert key in result

    def test_parses_break_time_from_html(self):
        with mock.patch("requests.get") as m:
            m.return_value.raise_for_status.return_value = None
            m.return_value.text = _BREAK_TIME_HTML
            result = get_break_time_info("테스트 식당", "서울 마포구")
        assert result["has_break_time"] is True
        assert result["break_start"] == "14:00"
        assert result["break_end"] == "17:00"
        assert result["last_order"] == "21:30"

    def test_returns_default_on_request_error(self):
        with mock.patch("requests.get", side_effect=requests.RequestException("error")):
            result = get_break_time_info("카페", "서울")
        assert result["has_break_time"] is False
