"""Agent별 LLM 모델 매핑. Resource Aware Optimization 전략을 반영한다."""

MODEL_CONFIG: dict[str, str] = {
    "input_collector": "gpt-4o-mini",
    "search": "gpt-4o",
    "route_planner": "gpt-4o",
    "memory": "text-embedding-3-small",
    "feedback_replan": "gpt-4o",
}
