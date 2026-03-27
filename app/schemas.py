from pydantic import BaseModel, Field
from datetime import datetime

class SensorDataCreate(BaseModel):
    device_id: str = Field(..., description="Unique identifier of the ESP32")
    tensao_shunt: float = Field(..., description="tensao_shunt read by the sensor")
    irradiance: float = Field(..., description="Solar irradiance read by the sensor")


class SensorDataIngestResponse(BaseModel):
    message: str
    buffered_count: int
    flushed: bool
    inserted_count: int

class SensorDataResponse(SensorDataCreate):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
