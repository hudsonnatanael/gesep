from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class SensorDataCreate(BaseModel):
    device_id: str = Field(..., description="Unique identifier of the ESP32")
    tensao_shunt: float = Field(..., description="tensao_shunt read by the sensor")
    irradiance: float = Field(..., description="Solar irradiance read by the sensor")
    temperatura: float = Field(..., description="Temperature read by DS18B20 sensor")


class SensorDataIngestResponse(BaseModel):
    message: str
    buffered_count: int
    flushed: bool
    inserted_count: int

class SensorDataResponse(BaseModel):
    id: int
    device_id: str
    tensao_shunt: float
    irradiance: float
    temperatura: Optional[float] = None  # Pode ser None para dados antigos
    timestamp: datetime

    class Config:
        from_attributes = True
        