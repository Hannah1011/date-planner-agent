"""전역 상수 및 Enum 정의. 매직 넘버·문자열은 반드시 이 파일에서만 선언한다."""

from enum import Enum

# --- 이동 시간 제약 ---
MAX_TRANSIT_MINUTES: int = 30
RECOMMENDED_TOTAL_TRANSIT: int = 120

# --- 코스 장소 수 제약 ---
MIN_COURSE_PLACES: int = 2
MAX_COURSE_PLACES: int = 5

# --- 리플랜 횟수 제한 ---
MAX_REPLAN_ATTEMPTS: int = 3

# --- 메모리 로드 건수 ---
MEMORY_LOAD_LIMIT: int = 20

# --- 서울 25개 구 ---
SEOUL_DISTRICTS: list[str] = [
    "강남구", "강동구", "강북구", "강서구", "관악구",
    "광진구", "구로구", "금천구", "노원구", "도봉구",
    "동대문구", "동작구", "마포구", "서대문구", "서초구",
    "성동구", "성북구", "송파구", "양천구", "영등포구",
    "용산구", "은평구", "종로구", "중구", "중랑구",
]


class TimeSlot(str, Enum):
    """하루 시간대 구분."""

    MORNING = "MORNING"       # 10:00 ~ 12:00
    LUNCH = "LUNCH"           # 12:00 ~ 14:00
    AFTERNOON = "AFTERNOON"   # 14:00 ~ 17:00
    EVENING = "EVENING"       # 18:00 ~ 21:00
    NIGHT = "NIGHT"           # 21:00 이후
    ALL_DAY = "ALL_DAY"       # 하루 전체


class Mood(str, Enum):
    """데이트 무드 구분."""

    NATURE_HEALING = "NATURE_HEALING"         # 자연 & 힐링
    FOOD_EXPLORATION = "FOOD_EXPLORATION"     # 맛있는 거 탐방
    NEW_ACTIVITY = "NEW_ACTIVITY"             # 새로운 액티비티
    COZY_CAFE = "COZY_CAFE"                   # 느긋한 카페 투어
    SHOPPING_STREET = "SHOPPING_STREET"       # 쇼핑 & 거리 탐방


class CafeStyle(str, Enum):
    """카페 스타일 구분."""

    COZY = "COZY"             # 감성
    QUIET = "QUIET"           # 조용한 분위기
    LUXURY = "LUXURY"         # 루프탑
    FRANCHISE = "FRANCHISE"   # 대형 프랜차이즈


class Sentiment(str, Enum):
    """피드백 감성 구분."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
