"""Agent 간 공유 데이터 모델(dataclass) 정의."""

from dataclasses import dataclass, field
from typing import Optional

from date_planner.config.constants import CafeStyle, Mood, TimeSlot


@dataclass
class UserRequest:
    """사용자 입력 조건을 담는 구조체."""

    district: str
    date: str
    time_slot: TimeSlot
    mood: Mood
    food_preferences: list[str]
    cafe_style: CafeStyle
    budget: int
    activities: list[str] = field(default_factory=list)


@dataclass
class PlaceCandidate:
    """검색된 장소 후보 정보."""

    name: str
    address: str
    category: str
    rating: float
    is_open: bool
    price_level: int
    district: str = ""
    place_id: str = ""
    reviews: list[dict] = field(default_factory=list)
    lat: float = 0.0
    lon: float = 0.0


@dataclass
class CourseStop:
    """코스 내 단일 방문지 정보."""

    place: PlaceCandidate
    transit_minutes_from_prev: int = 0
    estimated_cost: int = 0
    visit_order: int = 0


@dataclass
class DateCourse:
    """완성된 데이트 코스."""

    stops: list[CourseStop]
    total_transit_minutes: int
    total_estimated_cost: int
    weather_note: str = ""
    session_id: str = ""

    def summary(self) -> str:
        """코스 요약 텍스트를 반환한다."""
        parts = [f"{i + 1}. {s.place.name} ({s.place.category})" for i, s in enumerate(self.stops)]
        cost_str = f"{self.total_estimated_cost:,}원"
        transit_str = f"총 이동 {self.total_transit_minutes}분"
        return " → ".join(parts) + f" | {transit_str} | 예상 {cost_str}"
