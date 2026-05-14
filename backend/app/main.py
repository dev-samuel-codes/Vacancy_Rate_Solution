# FastAPI 서버 시작점

from fastapi import FastAPI

from app.predictor import predict_vacancy_rate
from app.schemas import PredictionResponse, VacancyInput

app = FastAPI(title="Vacancy Rate Solution API")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Vacancy Rate Solution API is running"}


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/predict", response_model=PredictionResponse)
def predict(payload: VacancyInput) -> PredictionResponse:
    return predict_vacancy_rate(payload)
