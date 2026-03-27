from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from .database import Base
from datetime import datetime, timedelta

def get_brazil_time():
    return datetime.utcnow() - timedelta(hours=3)

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    tensao_shunt = Column(Float, nullable=False)
    irradiance = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=get_brazil_time)
