# 요청/응답 데이터 형식

from pydantic import BaseModel, Field


class VacancyInput(BaseModel):
    region: str = Field(..., examples=["Jeonju"])
    building_type: str = Field(..., examples=["office"])
    floor_area: float = Field(..., ge=0, examples=[84.2])
    building_age: int = Field(..., ge=0, examples=[12])
    nearby_subway_count: int = Field(0, ge=0, examples=[1])
    nearby_bus_stop_count: int = Field(0, ge=0, examples=[8])


class PredictionResponse(BaseModel):
    vacancy_rate: float
    risk_level: str
