"""SQLite 기반 취향/피드백/방문기록 영속 저장소.

모든 함수는 try-except로 감싸며, 예외 발생 시 로깅 후
빈 결과([], "", False)를 반환해 시스템 중단을 방지한다.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from date_planner.config.constants import MEMORY_LOAD_LIMIT
from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "date_planner" / "data" / "preferences.db"


def _get_connection(db_path: Path) -> sqlite3.Connection:
    """DB 파일 경로에 대한 sqlite3 Connection을 반환한다.

    Args:
        db_path: SQLite DB 파일 경로.

    Returns:
        sqlite3.Connection 인스턴스.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = _DEFAULT_DB_PATH) -> bool:
    """DB 파일이 없으면 생성하고 3개 테이블을 초기화한다.

    Args:
        db_path: SQLite DB 파일 경로. 기본값은 data/preferences.db.

    Returns:
        초기화 성공 여부.
    """
    try:
        with _get_connection(db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    category  TEXT    NOT NULL,
                    value     TEXT    NOT NULL,
                    sentiment TEXT    NOT NULL,
                    reason    TEXT,
                    created_at TEXT   NOT NULL
                );

                CREATE TABLE IF NOT EXISTS visit_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    place_name  TEXT    NOT NULL,
                    category    TEXT    NOT NULL,
                    district    TEXT    NOT NULL,
                    rating      INTEGER,
                    visited_at  TEXT    NOT NULL,
                    notes       TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback_log (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id     TEXT    NOT NULL,
                    course_summary TEXT    NOT NULL,
                    accepted       INTEGER NOT NULL,
                    reason         TEXT,
                    created_at     TEXT    NOT NULL
                );
            """)
        logger.info("DB 초기화 완료: %s", db_path)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError, OSError) as e:
        logger.error("DB 초기화 실패: %s", e)
        return False


def save_feedback(
    session_id: str,
    course_summary: str,
    accepted: bool,
    reason: str = "",
    db_path: Path = _DEFAULT_DB_PATH,
) -> bool:
    """피드백 로그를 feedback_log 테이블에 저장한다.

    Args:
        session_id: 세션 식별자.
        course_summary: 제안된 코스 요약 텍스트.
        accepted: True면 승인, False면 거절.
        reason: 거절 이유 (선택).
        db_path: SQLite DB 파일 경로.

    Returns:
        저장 성공 여부.
    """
    try:
        with _get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO feedback_log (session_id, course_summary, accepted, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, course_summary, int(accepted), reason, _now()),
            )
        logger.debug("피드백 저장 완료: session=%s accepted=%s", session_id, accepted)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.error("피드백 저장 실패: %s", e)
        return False


def save_preference(
    category: str,
    value: str,
    sentiment: str,
    reason: str = "",
    db_path: Path = _DEFAULT_DB_PATH,
) -> bool:
    """취향 정보를 user_preferences 테이블에 저장한다.

    Args:
        category: 취향 카테고리 (예: "음식", "카페", "무드").
        value: 구체적인 값 (예: "파스타", "감성 카페").
        sentiment: "positive" 또는 "negative".
        reason: 해당 취향의 이유 (선택).
        db_path: SQLite DB 파일 경로.

    Returns:
        저장 성공 여부.
    """
    try:
        with _get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (category, value, sentiment, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category, value, sentiment, reason, _now()),
            )
        logger.debug("취향 저장 완료: category=%s value=%s sentiment=%s", category, value, sentiment)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.error("취향 저장 실패: %s", e)
        return False


def save_visit(
    place_name: str,
    category: str,
    district: str,
    rating: int,
    visited_at: str,
    notes: str = "",
    db_path: Path = _DEFAULT_DB_PATH,
) -> bool:
    """방문 기록을 visit_history 테이블에 저장한다.

    Args:
        place_name: 장소 이름.
        category: 장소 카테고리 (예: "음식점", "카페").
        district: 구 이름 (예: "마포구").
        rating: 사용자 평가 1~5.
        visited_at: 방문 날짜 문자열 (YYYY-MM-DD).
        notes: 메모 (선택).
        db_path: SQLite DB 파일 경로.

    Returns:
        저장 성공 여부.
    """
    try:
        with _get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO visit_history (place_name, category, district, rating, visited_at, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (place_name, category, district, rating, visited_at, notes),
            )
        logger.debug("방문 기록 저장 완료: %s (%s)", place_name, visited_at)
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.error("방문 기록 저장 실패: %s", e)
        return False


def load_preferences(
    limit: int = MEMORY_LOAD_LIMIT,
    db_path: Path = _DEFAULT_DB_PATH,
) -> list[dict]:
    """최근 N건의 취향 데이터를 로드한다.

    Args:
        limit: 로드할 최대 건수. 기본값은 MEMORY_LOAD_LIMIT(20).
        db_path: SQLite DB 파일 경로.

    Returns:
        취향 dict 리스트. 에러 시 빈 리스트.
    """
    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(
                """
                SELECT category, value, sentiment, reason, created_at
                FROM user_preferences
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.error("취향 로드 실패: %s", e)
        return []


def load_visit_history(
    district: Optional[str] = None,
    db_path: Path = _DEFAULT_DB_PATH,
) -> list[dict]:
    """방문 기록을 조회한다.

    Args:
        district: 구 이름으로 필터링. None이면 전체 조회.
        db_path: SQLite DB 파일 경로.

    Returns:
        방문 기록 dict 리스트. 에러 시 빈 리스트.
    """
    try:
        with _get_connection(db_path) as conn:
            if district:
                rows = conn.execute(
                    """
                    SELECT place_name, category, district, rating, visited_at, notes
                    FROM visit_history
                    WHERE district = ?
                    ORDER BY visited_at DESC
                    """,
                    (district,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT place_name, category, district, rating, visited_at, notes
                    FROM visit_history
                    ORDER BY visited_at DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.error("방문 기록 조회 실패: %s", e)
        return []


def get_preference_summary(db_path: Path = _DEFAULT_DB_PATH) -> str:
    """LLM 프롬프트에 주입할 취향 요약 텍스트를 생성한다.

    최근 MEMORY_LOAD_LIMIT건의 취향을 sentiment별로 분류해 요약한다.

    Args:
        db_path: SQLite DB 파일 경로.

    Returns:
        요약 텍스트. 데이터가 없거나 에러 시 빈 문자열.
    """
    preferences = load_preferences(db_path=db_path)
    if not preferences:
        return ""

    positives = [p for p in preferences if p.get("sentiment") == "positive"]
    negatives = [p for p in preferences if p.get("sentiment") == "negative"]

    lines: list[str] = ["사용자 취향 정보:"]

    if positives:
        lines.append("- 선호:")
        for p in positives:
            reason_part = f" ({p['reason']})" if p.get("reason") else ""
            lines.append(f"  * {p['category']}: {p['value']}{reason_part}")

    if negatives:
        lines.append("- 비선호:")
        for p in negatives:
            reason_part = f" ({p['reason']})" if p.get("reason") else ""
            lines.append(f"  * {p['category']}: {p['value']}{reason_part}")

    return "\n".join(lines)


def _now() -> str:
    """현재 시각을 마이크로초 단위 ISO 형식 문자열로 반환한다."""
    return datetime.now().isoformat(timespec="microseconds")
