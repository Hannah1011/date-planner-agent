"""Phase 1: 프로젝트 뼈대 검증 테스트."""

import logging

from date_planner.config.constants import (
    MAX_TRANSIT_MINUTES,
    RECOMMENDED_TOTAL_TRANSIT,
    MIN_COURSE_PLACES,
    MAX_COURSE_PLACES,
    MAX_REPLAN_ATTEMPTS,
    MEMORY_LOAD_LIMIT,
    SEOUL_DISTRICTS,
    TimeSlot,
    Mood,
    CafeStyle,
    Sentiment,
)
from date_planner.config.model_config import MODEL_CONFIG
from date_planner.utils.logger import get_logger


class TestConstants:
    """상수 값 및 Enum 검증."""

    def test_transit_limits(self):
        assert MAX_TRANSIT_MINUTES == 30
        assert RECOMMENDED_TOTAL_TRANSIT == 120

    def test_course_place_limits(self):
        assert MIN_COURSE_PLACES == 2
        assert MAX_COURSE_PLACES == 5
        assert MIN_COURSE_PLACES < MAX_COURSE_PLACES

    def test_replan_limit(self):
        assert MAX_REPLAN_ATTEMPTS == 3

    def test_memory_load_limit(self):
        assert MEMORY_LOAD_LIMIT == 20

    def test_seoul_districts_count(self):
        assert len(SEOUL_DISTRICTS) == 25

    def test_seoul_districts_known_values(self):
        assert "마포구" in SEOUL_DISTRICTS
        assert "강남구" in SEOUL_DISTRICTS
        assert "중구" in SEOUL_DISTRICTS

    def test_time_slot_enum_members(self):
        members = {ts.value for ts in TimeSlot}
        assert members == {"MORNING", "LUNCH", "AFTERNOON", "EVENING", "NIGHT", "ALL_DAY"}

    def test_mood_enum_members(self):
        assert len(list(Mood)) == 5

    def test_cafe_style_enum_members(self):
        assert len(list(CafeStyle)) == 4

    def test_sentiment_enum_members(self):
        values = {s.value for s in Sentiment}
        assert values == {"positive", "negative"}


class TestModelConfig:
    """모델 설정 검증."""

    def test_all_agents_have_model(self):
        required_agents = {"input_collector", "search", "route_planner", "memory", "feedback_replan"}
        assert required_agents.issubset(MODEL_CONFIG.keys())
        assert MODEL_CONFIG["course_narrator"] == "gpt-4o-mini"

    def test_lightweight_model_for_input_collector(self):
        assert MODEL_CONFIG["input_collector"] == "gpt-4o-mini"

    def test_embedding_model_for_memory(self):
        assert MODEL_CONFIG["memory"] == "text-embedding-3-small"


class TestLogger:
    """로거 팩토리 검증."""

    def test_get_logger_returns_logger_instance(self):
        logger = get_logger("test.foundation")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_same_name_returns_same_instance(self):
        logger_a = get_logger("test.singleton")
        logger_b = get_logger("test.singleton")
        assert logger_a is logger_b

    def test_logger_has_handlers(self):
        logger = get_logger("test.handlers")
        assert len(logger.handlers) >= 1

    def test_logger_name_matches(self):
        logger = get_logger("test.name_check")
        assert logger.name == "test.name_check"
