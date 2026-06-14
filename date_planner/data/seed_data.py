"""취향 반영 결과를 바로 확인할 수 있도록 샘플 데이터를 DB에 삽입한다.

사용법:
    python -m date_planner.data.seed_data
"""

from pathlib import Path

from date_planner.memory.preference_store import (
    init_db,
    save_feedback,
    save_preference,
    save_visit,
)
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_DB_PATH = Path(__file__).resolve().parents[2] / "date_planner" / "data" / "preferences.db"

_PREFERENCES = [
    ("음식", "파스타", "positive", "식감이 좋고 양이 적당함"),
    ("음식", "스테이크", "positive", "특별한 날 분위기에 잘 맞음"),
    ("음식", "패스트푸드", "negative", "데이트에 어울리지 않음"),
    ("카페", "감성 카페", "positive", "분위기가 좋아서 대화하기 편함"),
    ("카페", "프랜차이즈 카페", "negative", "너무 시끄럽고 개성이 없음"),
    ("지역", "마포구", "positive", "홍대·연남동 접근성이 좋음"),
    ("지역", "강남구", "positive", "다양한 레스토랑이 많음"),
    ("무드", "자연 & 힐링", "positive", "걷기 좋고 스트레스 해소됨"),
    ("무드", "쇼핑 & 거리 탐방", "negative", "피로감이 높음"),
    ("카페 스타일", "루프탑", "positive", "야경이 아름다워서 분위기 좋음"),
]

_VISITS = [
    ("연남동 파스타집", "음식점", "마포구", 5, "2026-05-10", "파스타가 훌륭함"),
    ("상수 감성 카페", "카페", "마포구", 4, "2026-05-15", "인테리어가 예쁨"),
    ("한강 공원", "액티비티", "마포구", 5, "2026-05-20", "피크닉 분위기 최고"),
    ("가로수길 레스토랑", "음식점", "강남구", 3, "2026-04-30", "맛은 보통"),
    ("북촌 한옥마을", "관광", "종로구", 4, "2026-04-15", "산책하기 좋음"),
]

_FEEDBACKS = [
    ("session-001", "마포구 파스타 + 감성카페 + 한강공원 코스", True, ""),
    ("session-002", "강남구 스테이크 + 루프탑카페 코스", True, ""),
    ("session-003", "종로구 한식 + 카페 코스", False, "카페가 너무 시끄러웠음"),
    ("session-004", "홍대 피자 + 맥주바 코스", False, "음식이 취향에 맞지 않음"),
    ("session-005", "연남동 브런치 + 연트럴파크 산책 코스", True, ""),
]


def insert_seed_data(db_path: Path = _DB_PATH) -> None:
    """샘플 데이터를 DB에 삽입한다.

    Args:
        db_path: 대상 SQLite DB 파일 경로.
    """
    if not init_db(db_path):
        logger.error("DB 초기화 실패 — 시드 데이터 삽입 중단")
        return

    for category, value, sentiment, reason in _PREFERENCES:
        save_preference(category, value, sentiment, reason, db_path)

    for place_name, category, district, rating, visited_at, notes in _VISITS:
        save_visit(place_name, category, district, rating, visited_at, notes, db_path)

    for session_id, course_summary, accepted, reason in _FEEDBACKS:
        save_feedback(session_id, course_summary, accepted, reason, db_path)

    logger.info(
        "시드 데이터 삽입 완료: 취향 %d건, 방문 %d건, 피드백 %d건",
        len(_PREFERENCES),
        len(_VISITS),
        len(_FEEDBACKS),
    )


if __name__ == "__main__":
    insert_seed_data()
