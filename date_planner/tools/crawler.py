"""브레이크타임 정보 크롤러 (Google Places에서 불명확한 상위 5개 장소만 대상).

USE_MOCK=true 환경 변수가 설정된 경우 Mock 응답을 반환한다.
실제 크롤링은 차단 최소화를 위해 requests + BeautifulSoup을 사용한다.
"""

import os
import re

import requests
from bs4 import BeautifulSoup

from date_planner.utils.logger import get_logger

logger = get_logger(__name__)

_REQUEST_TIMEOUT = 5
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_NAVER_SEARCH_URL = "https://search.naver.com/search.naver"

_MOCK_BREAK_TIME = {
    "has_break_time": False,
    "break_start": None,
    "break_end": None,
    "last_order": None,
}


def get_break_time_info(place_name: str, address: str) -> dict:
    """장소의 브레이크타임 정보를 크롤링으로 수집한다.

    Google Places 영업시간 데이터가 불명확한 경우에만 호출해야 한다.

    Args:
        place_name: 장소 이름.
        address: 장소 주소.

    Returns:
        has_break_time, break_start, break_end, last_order 를 포함한 dict.
        에러 시 has_break_time=False 인 기본 dict.
    """
    if _use_mock():
        logger.debug("브레이크타임 Mock 반환: %s", place_name)
        return dict(_MOCK_BREAK_TIME)

    try:
        query = f"{place_name} {address} 브레이크타임"
        html = _fetch_naver_search(query)
        if not html:
            return dict(_MOCK_BREAK_TIME)
        return _parse_break_time(html)
    except Exception as e:
        logger.error("브레이크타임 크롤링 실패: %s — 기본값 반환", e)
        return dict(_MOCK_BREAK_TIME)


def _fetch_naver_search(query: str) -> str:
    """네이버 검색 결과 HTML을 가져온다.

    Args:
        query: 검색 쿼리 문자열.

    Returns:
        HTML 문자열. 에러 시 빈 문자열.
    """
    try:
        response = requests.get(
            _NAVER_SEARCH_URL,
            params={"query": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error("네이버 검색 HTML 수집 실패: %s", e)
        return ""


def _parse_break_time(html: str) -> dict:
    """HTML에서 브레이크타임 정보를 파싱한다.

    Args:
        html: 네이버 검색 결과 HTML.

    Returns:
        has_break_time, break_start, break_end, last_order 를 포함한 dict.
    """
    result = dict(_MOCK_BREAK_TIME)
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")

        break_pattern = re.search(r"브레이크타임\s*(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", text)
        if break_pattern:
            result["has_break_time"] = True
            result["break_start"] = break_pattern.group(1)
            result["break_end"] = break_pattern.group(2)

        last_order_pattern = re.search(r"라스트\s*오더\s*(\d{1,2}:\d{2})", text)
        if last_order_pattern:
            result["last_order"] = last_order_pattern.group(1)
    except Exception as e:
        logger.error("브레이크타임 HTML 파싱 실패: %s", e)

    return result


def _use_mock() -> bool:
    """USE_MOCK 환경 변수가 'true'로 설정되어 있으면 True를 반환한다."""
    return os.getenv("USE_MOCK", "true").lower() == "true"
