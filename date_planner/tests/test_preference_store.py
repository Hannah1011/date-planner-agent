"""Phase 2: preference_store CRUD 및 예외처리 테스트."""

import sqlite3
from pathlib import Path

import pytest

from date_planner.memory.preference_store import (
    init_db,
    save_feedback,
    save_preference,
    save_visit,
    load_preferences,
    load_visit_history,
    get_preference_summary,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """테스트용 임시 DB 경로를 제공한다."""
    db = tmp_path / "test_preferences.db"
    init_db(db)
    return db


class TestInitDb:
    def test_creates_db_file(self, tmp_path):
        db = tmp_path / "new.db"
        assert not db.exists()
        result = init_db(db)
        assert result is True
        assert db.exists()

    def test_creates_all_tables(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert {"user_preferences", "visit_history", "feedback_log"}.issubset(tables)

    def test_idempotent_on_existing_db(self, tmp_db):
        # 두 번 호출해도 오류 없이 True 반환
        result = init_db(tmp_db)
        assert result is True

    def test_returns_false_on_invalid_path(self):
        # 쓰기 불가 경로에 대한 graceful 처리
        bad_path = Path("/no_permission_dir/test.db")
        result = init_db(bad_path)
        assert result is False


class TestSaveAndLoadPreference:
    def test_save_and_load_single(self, tmp_db):
        save_preference("음식", "파스타", "positive", "맛있음", tmp_db)
        rows = load_preferences(db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["value"] == "파스타"
        assert rows[0]["sentiment"] == "positive"

    def test_load_respects_limit(self, tmp_db):
        for i in range(10):
            save_preference("음식", f"메뉴{i}", "positive", "", tmp_db)
        rows = load_preferences(limit=5, db_path=tmp_db)
        assert len(rows) == 5

    def test_load_returns_most_recent_first(self, tmp_db):
        save_preference("음식", "비빔밥", "positive", "", tmp_db)
        save_preference("음식", "파스타", "positive", "", tmp_db)
        rows = load_preferences(db_path=tmp_db)
        assert rows[0]["value"] == "파스타"

    def test_save_negative_sentiment(self, tmp_db):
        save_preference("카페", "프랜차이즈", "negative", "시끄러움", tmp_db)
        rows = load_preferences(db_path=tmp_db)
        assert rows[0]["sentiment"] == "negative"

    def test_load_returns_empty_on_no_data(self, tmp_db):
        rows = load_preferences(db_path=tmp_db)
        assert rows == []

    def test_load_returns_empty_on_db_error(self, tmp_path):
        bad_db = tmp_path / "missing.db"  # init_db 안 함 → 테이블 없음
        rows = load_preferences(db_path=bad_db)
        assert rows == []


class TestSaveAndLoadVisit:
    def test_save_and_load_all(self, tmp_db):
        save_visit("홍대 카페", "카페", "마포구", 5, "2026-06-01", "좋음", tmp_db)
        rows = load_visit_history(db_path=tmp_db)
        assert len(rows) == 1
        assert rows[0]["place_name"] == "홍대 카페"

    def test_filter_by_district(self, tmp_db):
        save_visit("A카페", "카페", "마포구", 4, "2026-06-01", "", tmp_db)
        save_visit("B레스토랑", "음식점", "강남구", 3, "2026-06-02", "", tmp_db)
        mapo_rows = load_visit_history(district="마포구", db_path=tmp_db)
        assert len(mapo_rows) == 1
        assert mapo_rows[0]["district"] == "마포구"

    def test_no_district_filter_returns_all(self, tmp_db):
        save_visit("X", "카페", "마포구", 4, "2026-06-01", "", tmp_db)
        save_visit("Y", "음식점", "강남구", 3, "2026-06-02", "", tmp_db)
        rows = load_visit_history(db_path=tmp_db)
        assert len(rows) == 2

    def test_load_returns_empty_on_db_error(self, tmp_path):
        bad_db = tmp_path / "missing.db"
        rows = load_visit_history(db_path=bad_db)
        assert rows == []


class TestSaveFeedback:
    def test_save_accepted(self, tmp_db):
        result = save_feedback("s1", "마포구 파스타 코스", True, "", tmp_db)
        assert result is True

    def test_save_rejected_with_reason(self, tmp_db):
        result = save_feedback("s2", "강남구 코스", False, "너무 멀어요", tmp_db)
        assert result is True

    def test_save_feedback_returns_false_on_error(self, tmp_path):
        bad_db = tmp_path / "missing.db"
        result = save_feedback("s3", "코스", True, "", bad_db)
        assert result is False


class TestGetPreferenceSummary:
    def test_returns_empty_string_when_no_data(self, tmp_db):
        summary = get_preference_summary(db_path=tmp_db)
        assert summary == ""

    def test_contains_positive_section(self, tmp_db):
        save_preference("음식", "파스타", "positive", "맛있음", tmp_db)
        summary = get_preference_summary(db_path=tmp_db)
        assert "선호" in summary
        assert "파스타" in summary

    def test_contains_negative_section(self, tmp_db):
        save_preference("카페", "프랜차이즈", "negative", "시끄러움", tmp_db)
        summary = get_preference_summary(db_path=tmp_db)
        assert "비선호" in summary
        assert "프랜차이즈" in summary

    def test_returns_empty_string_on_db_error(self, tmp_path):
        bad_db = tmp_path / "missing.db"
        summary = get_preference_summary(db_path=bad_db)
        assert summary == ""
