"""공통 로거 팩토리. 파일 핸들러와 콘솔 핸들러를 동시에 설정한다."""

import logging
import os
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
_LOG_FILE = _LOG_DIR / "date_planner.log"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _ensure_log_dir() -> None:
    """로그 디렉토리가 없으면 생성한다."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """이름으로 Logger를 생성하거나 기존 Logger를 반환한다.

    Args:
        name: 로거 이름. 보통 __name__ 을 전달한다.

    Returns:
        설정이 완료된 logging.Logger 인스턴스.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        _ensure_log_dir()
        file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as e:
        logger.warning("로그 파일 핸들러 설정 실패, 콘솔 출력만 사용합니다: %s", e)

    return logger
