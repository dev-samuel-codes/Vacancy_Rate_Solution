# 모델 로드 및 실제 예측

from app.schemas import PredictionResponse, VacancyInput
from app.services import calculate_fallback_score, classify_risk


def predict_vacancy_rate(payload: VacancyInput) -> PredictionResponse:
    vacancy_rate = calculate_fallback_score(payload)
    return PredictionResponse(
        vacancy_rate=round(vacancy_rate, 4),
        risk_level=classify_risk(vacancy_rate),
    )
