# 예측 요청 처리 흐름

from app.schemas import VacancyInput


def calculate_fallback_score(payload: VacancyInput) -> float:
    base = 0.08
    age_factor = min(payload.building_age * 0.003, 0.12)
    size_factor = min(payload.floor_area / 10000, 0.05)
    transit_factor = min(
        (payload.nearby_subway_count * 0.01) + (payload.nearby_bus_stop_count * 0.001),
        0.04,
    )
    return max(0.0, min(base + age_factor + size_factor - transit_factor, 1.0))


def classify_risk(vacancy_rate: float) -> str:
    if vacancy_rate >= 0.2:
        return "high"
    if vacancy_rate >= 0.1:
        return "medium"
    return "low"
