from fastapi import FastAPI, HTTPException
from typing import Optional
from datetime import datetime
from fastapi.responses import Response, HTMLResponse
import csv
import io
import asyncio
import uvicorn
from pathlib import Path
from . import models, schemas, database

# Create tables if they don't exist
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="ESP32 Sensor API",
    description="API to receive sensor data from ESP32",
    version="1.0.0"
)

BUFFER_SIZE = 12
sensor_buffer: list[dict] = []
buffer_lock = asyncio.Lock()
EXTRACT_UI_PATH = Path(__file__).with_name("extract_ui.html")


def flush_sensor_batch_sync(batch: list[dict]) -> int:
    db = database.SessionLocal()
    try:
        db_batch = [models.SensorData(**item) for item in batch]
        db.add_all(db_batch)
        db.commit()
        return len(db_batch)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def read_sensor_data_sync(
    skip: int,
    limit: int,
    device_id: Optional[str],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
):
    db = database.SessionLocal()
    try:
        query = db.query(models.SensorData)

        if device_id:
            query = query.filter(models.SensorData.device_id == device_id)
        if start_time:
            query = query.filter(models.SensorData.timestamp >= start_time)
        if end_time:
            query = query.filter(models.SensorData.timestamp <= end_time)

        return query.offset(skip).limit(limit).all()
    finally:
        db.close()


def start_server() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


@app.get("/extract", response_class=HTMLResponse)
async def extract_interface():
    return HTMLResponse(content=EXTRACT_UI_PATH.read_text(encoding="utf-8"))


@app.post("/api/sensors/", response_model=schemas.SensorDataIngestResponse, status_code=201)
async def create_sensor_data(sensor_data: schemas.SensorDataCreate):
    batch_to_flush: list[dict] = []
    buffered_count = 0
    received_at = models.get_brazil_time()

    async with buffer_lock:
        sensor_buffer.append(
            {
                "device_id": sensor_data.device_id,
                "tensao_shunt": sensor_data.tensao_shunt,
                "irradiance": sensor_data.irradiance,
                "timestamp": received_at,
            }
        )
        if len(sensor_buffer) >= BUFFER_SIZE:
            batch_to_flush = sensor_buffer[:]
            sensor_buffer.clear()
        buffered_count = len(sensor_buffer)

    inserted_count = 0
    flushed = False
    if batch_to_flush:
        try:
            inserted_count = await asyncio.to_thread(flush_sensor_batch_sync, batch_to_flush)
            flushed = True
        except Exception:
            async with buffer_lock:
                sensor_buffer[0:0] = batch_to_flush
                buffered_count = len(sensor_buffer)
            raise HTTPException(status_code=500, detail="Failed to flush buffered measurements to database")

    return {
        "message": "Measurement buffered",
        "buffered_count": buffered_count,
        "flushed": flushed,
        "inserted_count": inserted_count,
    }

@app.get("/api/sensors/", response_model=list[schemas.SensorDataResponse])
async def read_sensor_data(
    skip: int = 0, 
    limit: int = 100, 
    device_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    format: str = "json"
):
    sensors = await asyncio.to_thread(
        read_sensor_data_sync,
        skip,
        limit,
        device_id,
        start_time,
        end_time,
    )
    
    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "device_id", "tensao_shunt", "irradiance", "timestamp"])
        for sensor in sensors:
            writer.writerow([sensor.id, sensor.device_id, sensor.tensao_shunt, sensor.irradiance, sensor.timestamp.isoformat() if sensor.timestamp else ""])
        return Response(
            content=output.getvalue(), 
            media_type="text/csv", 
            headers={"Content-Disposition": "attachment; filename=sensors_data.csv"}
        )
        
    return sensors
