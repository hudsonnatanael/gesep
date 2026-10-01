from fastapi import FastAPI, HTTPException
from typing import Optional
from datetime import datetime
from fastapi.responses import Response, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
import asyncio
import uvicorn
import json
import logging
from pathlib import Path
from sqlalchemy import and_, inspect, or_, text
from . import models, schemas, database

# Configure logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log startup
logger.info("="*60)
logger.info("🚀 SERVIDOR GESEP INICIANDO")
logger.info(f"📂 Banco de dados: {database.SQLALCHEMY_DATABASE_URL}")
logger.info("="*60)

# Create tables if they don't exist
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="ESP32 Sensor API",
    description="API to receive sensor data from ESP32",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Quick health check endpoint"""
    logger.info("🏥 Health check da ESP32 recebido!")
    return {"status": "ok", "server": "GESEP Ready"}

# Startup event
@app.on_event("startup")
async def startup_event():
    ensure_sensor_schema()
    logger.info("✅ Servidor pronto para receber dados da ESP32!")
    logger.info(f"📍 Acesse: http://localhost:8000/extract")
    logger.info(f"🔌 API ESP32: http://localhost:8000/api/sensors/")

BUFFER_SIZE = 10
sensor_buffer: list[dict] = []
buffer_lock = asyncio.Lock()

# Real-time broadcast system
sse_clients: list[asyncio.Queue] = []
sse_lock = asyncio.Lock()
EXTRACT_UI_PATH = Path(__file__).with_name("extract_ui.html")


def sensor_measurement_key(device_id: str, timestamp: datetime) -> tuple[str, datetime]:
    normalized_timestamp = timestamp.astimezone(models.BRAZIL_TZ).replace(tzinfo=None)
    return device_id, normalized_timestamp


def ensure_sensor_schema() -> None:
    inspector = inspect(database.engine)
    if "sensor_data" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("sensor_data")}
    if "irradiance_cell" not in columns:
        with database.engine.begin() as conn:
            conn.execute(text("ALTER TABLE sensor_data ADD COLUMN irradiance_cell FLOAT"))
        logger.info("✅ Added irradiance_cell column to sensor_data table")

    with database.engine.begin() as conn:
        if database.engine.dialect.name == "postgresql":
            result = conn.execute(text("""
                DELETE FROM sensor_data duplicate
                USING sensor_data original
                WHERE duplicate.id > original.id
                  AND duplicate.device_id = original.device_id
                  AND duplicate.timestamp = original.timestamp
            """))
        else:
            result = conn.execute(text("""
                DELETE FROM sensor_data
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM sensor_data
                    GROUP BY device_id, timestamp
                )
            """))
        if result.rowcount:
            logger.info(f"🧹 Removed {result.rowcount} exact duplicate measurements")
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_data_device_timestamp
            ON sensor_data (device_id, timestamp)
        """))


async def broadcast_sensor(data: dict) -> None:
    """Broadcast new sensor data to all connected SSE clients"""
    async with sse_lock:
        logger.info(f"🔊 Broadcasting to {len(sse_clients)} SSE clients")
        logger.debug(f"   Data: {data}")
        
        failed_clients = []
        for queue in sse_clients[:]:
            try:
                queue.put_nowait(data)
                logger.debug(f"✅ Data sent to queue")
            except asyncio.QueueFull:
                logger.warning(f"❌ Queue full, removing client")
                failed_clients.append(queue)
            except Exception as e:
                logger.error(f"❌ Error sending to queue: {e}")
                failed_clients.append(queue)
        
        # Remove failed clients
        for client in failed_clients:
            if client in sse_clients:
                sse_clients.remove(client)


def flush_sensor_batch_sync(batch: list[dict]) -> list[dict]:
    db = database.SessionLocal()
    try:
        unique_batch = []
        seen_keys = set()
        for item in batch:
            key = sensor_measurement_key(item["device_id"], item["timestamp"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique_batch.append(item)

        if not unique_batch:
            return []

        existing_records = db.query(models.SensorData).filter(
            or_(
                *(
                    and_(
                        models.SensorData.device_id == item["device_id"],
                        models.SensorData.timestamp == item["timestamp"],
                    )
                    for item in unique_batch
                )
            )
        ).all()
        existing_keys = {
            sensor_measurement_key(item.device_id, item.timestamp.replace(tzinfo=models.BRAZIL_TZ))
            for item in existing_records
        }

        new_items = [
            item for item in unique_batch
            if sensor_measurement_key(item["device_id"], item["timestamp"]) not in existing_keys
        ]
        if not new_items:
            db.rollback()
            logger.info("⏭️ Ignored duplicate sensor measurements")
            return []

        db_batch = [models.SensorData(**item) for item in new_items]
        db.add_all(db_batch)
        db.commit()
        
        # Refresh to get the IDs
        for item in db_batch:
            db.refresh(item)
        
        # Return the saved data with IDs
        return [
            {
                "id": item.id,
                "device_id": item.device_id,
                "tensao_shunt": item.tensao_shunt,
                "irradiance": item.irradiance,
                "irradiance_cell": item.irradiance_cell,
                "temperatura": item.temperatura,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            }
            for item in db_batch
        ]
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
        
        # Log total records
        total_records = query.count()
        logger.info(f"  📊 Total records in DB: {total_records}")

        if device_id:
            query = query.filter(models.SensorData.device_id == device_id)
            logger.info(f"  🔍 Filtering by device_id: {device_id}")
            
        if start_time:
            logger.info(f"  📅 Filtering start_time >= {start_time} (tzinfo: {start_time.tzinfo})")
            query = query.filter(models.SensorData.timestamp >= start_time)
            
        if end_time:
            logger.info(f"  📅 Filtering end_time <= {end_time} (tzinfo: {end_time.tzinfo})")
            query = query.filter(models.SensorData.timestamp <= end_time)

        # Order by timestamp (oldest first)
        query = query.order_by(models.SensorData.timestamp.asc())
        
        results = query.offset(skip).limit(limit).all()
        logger.info(f"  ✅ After filters: {len(results)} records (ordered by timestamp)")
        return results
    except Exception as e:
        logger.error(f"❌ ERROR in read_sensor_data_sync: {type(e).__name__}: {e}", exc_info=True)
        raise
    finally:
        db.close()


def start_server() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


@app.get("/extract", response_class=HTMLResponse)
async def extract_interface():
    return HTMLResponse(content=EXTRACT_UI_PATH.read_text(encoding="utf-8"))


@app.get("/api/sensors/stream")
async def stream_sensor_data():
    """Server-Sent Events endpoint for real-time sensor data"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    
    async with sse_lock:
        sse_clients.append(queue)
        logger.info(f"📡 New SSE client connected. Total clients: {len(sse_clients)}")
    
    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=55)
                    try:
                        json_data = json.dumps(data)
                        logger.debug(f"📨 Sending SSE data: {json_data}")
                        yield f"data: {json_data}\n\n"
                    except TypeError as e:
                        logger.error(f"❌ JSON serialization error: {e}, data type: {type(data)}, data: {data}")
                        # Try to fix timestamp serialization
                        if isinstance(data, dict) and "timestamp" in data:
                            data["timestamp"] = str(data["timestamp"])
                            json_data = json.dumps(data)
                            yield f"data: {json_data}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            logger.info(f"📡 SSE client disconnected")
        finally:
            async with sse_lock:
                if queue in sse_clients:
                    sse_clients.remove(queue)
                    logger.info(f"Total clients after disconnect: {len(sse_clients)}")
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/extract", response_class=HTMLResponse)
async def extract_interface():
    return HTMLResponse(content=EXTRACT_UI_PATH.read_text(encoding="utf-8"))


@app.post("/api/sensors/", response_model=schemas.SensorDataIngestResponse, status_code=201)
async def create_sensor_data(sensor_data: schemas.SensorDataCreate | list[schemas.SensorDataCreate]):
    items = sensor_data if isinstance(sensor_data, list) else [sensor_data]

    if not items:
        raise HTTPException(status_code=400, detail="No sensor data provided")

    batches_to_flush: list[list[dict]] = []
    buffered_count = 0
    inserted_count = 0
    flushed = False
    saved_data = []

    for current_item in items:
        effective_shunt = current_item.tensao_shunt if current_item.tensao_shunt is not None else current_item.irradiance_cell
        if effective_shunt is None:
            effective_shunt = 0.0

        logger.info(
            f"📥 Received sensor data: device={current_item.device_id}, shunt={effective_shunt}, "
            f"irrad={current_item.irradiance}, irrad_cell={current_item.irradiance_cell}"
        )

        raw_timestamp = current_item.timestamp
        if raw_timestamp is not None:
            if raw_timestamp.tzinfo is None:
                received_at = models.BRAZIL_TZ.localize(raw_timestamp)
            else:
                received_at = raw_timestamp.astimezone(models.BRAZIL_TZ)
        else:
            received_at = models.get_brazil_time()

        data_to_buffer = {
            "device_id": current_item.device_id,
            "tensao_shunt": effective_shunt,
            "irradiance": current_item.irradiance,
            "irradiance_cell": current_item.irradiance_cell,
            "temperatura": current_item.temperatura,
            "temperatura_pv": current_item.temperatura_pv,
            "temperatura_ambiente": current_item.temperatura_ambiente,
            "timestamp": received_at,
        }

        async with buffer_lock:
            sensor_buffer.append(data_to_buffer)
            while len(sensor_buffer) >= BUFFER_SIZE:
                batches_to_flush.append(sensor_buffer[:BUFFER_SIZE])
                del sensor_buffer[:BUFFER_SIZE]
                logger.info(f"💾 Buffer full ({BUFFER_SIZE} items), flushing to database")
            buffered_count = len(sensor_buffer)

    for batch_index, batch_to_flush in enumerate(batches_to_flush):
        try:
            batch_saved_data = await asyncio.to_thread(flush_sensor_batch_sync, batch_to_flush)
            saved_data.extend(batch_saved_data)
            inserted_count += len(batch_saved_data)
            flushed = True
            logger.info(f"✅ Saved {len(batch_saved_data)} records to database")
            for record in batch_saved_data:
                await broadcast_sensor(record)
        except Exception as e:
            logger.error(f"❌ Error flushing to database: {e}")
            async with buffer_lock:
                pending_batches = batches_to_flush[batch_index:]
                sensor_buffer[0:0] = [item for pending_batch in pending_batches for item in pending_batch]
                buffered_count = len(sensor_buffer)
            raise HTTPException(status_code=500, detail="Failed to flush buffered measurements to database")

    return {
        "message": "Measurement buffered",
        "buffered_count": buffered_count,
        "flushed": flushed,
        "inserted_count": inserted_count,
    }

@app.get("/api/debug/fix-timezone")
async def fix_timezone():
    """Fix timestamps in existing records by adding 3 hours"""
    from sqlalchemy import text, inspect
    db = database.SessionLocal()
    try:
        # Add 3 hours to all timestamps
        result = db.execute(
            text("UPDATE sensor_data SET timestamp = timestamp + INTERVAL '3 hours'")
        )
        db.commit()
        affected_rows = result.rowcount
        logger.info(f"✅ Fixed {affected_rows} records - added 3 hours to all timestamps")
        return {
            "message": "Timezone fix applied successfully",
            "records_updated": affected_rows,
            "action": "Added 3 hours to all timestamps"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error fixing timezone: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix timezone: {str(e)}")
    finally:
        db.close()

@app.get("/api/debug/status")
async def debug_status():
    """Debug endpoint showing system status"""
    import datetime as dt_module
    current_time = models.get_brazil_time()
    
    return {
        "connected_sse_clients": len(sse_clients),
        "buffer_size": len(sensor_buffer),
        "server_time_brazil": current_time.isoformat(),
        "server_time_utc": dt_module.datetime.now(dt_module.timezone.utc).isoformat(),
        "timezone": "America/Sao_Paulo (Brazil)",
        "hour": current_time.hour,
    }

@app.get("/api/debug/test-sse")
async def debug_test_sse():
    """Test endpoint to send a test message via SSE"""
    test_data = {
        "id": 999,
        "device_id": "TEST_ESP32",
        "tensao_shunt": 0.00123,
        "irradiance": 456.78,
        "irradiance_cell": 321.09,
        "temperatura": 28.5,
        "timestamp": models.get_brazil_time().isoformat()
    }
    logger.info(f"🧪 Test SSE message: {test_data}")
    await broadcast_sensor(test_data)
    return {"message": "Test message sent to all SSE clients", "sse_clients": len(sse_clients)}

@app.get("/api/debug/latest")
async def debug_latest():
    """Get latest records without any filters"""
    db = database.SessionLocal()
    try:
        records = db.query(models.SensorData).order_by(models.SensorData.id.desc()).limit(10).all()
        logger.info(f"📊 Latest records: {len(records)} found")
        for r in records:
            logger.info(f"  - ID: {r.id}, Device: {r.device_id}, TS: {r.timestamp}")
        return {
            "total": len(records),
            "sse_clients_connected": len(sse_clients),
            "buffer_size": len(sensor_buffer),
            "server_time": models.get_brazil_time().isoformat(),
            "records": [
                {
                    "id": r.id,
                    "device_id": r.device_id,
                    "tensao_shunt": r.tensao_shunt,
                    "irradiance": r.irradiance,
                    "irradiance_cell": r.irradiance_cell,
                    "temperatura": r.temperatura,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                }
                for r in records
            ]
        }
    finally:
        db.close()

@app.get("/api/debug/system-status")
async def system_status():
    """Get system status for debugging"""
    db = database.SessionLocal()
    try:
        total_records = db.query(models.SensorData).count()
        latest = db.query(models.SensorData).order_by(models.SensorData.id.desc()).first()
        
        latest_time = latest.timestamp.isoformat() if latest else None
        current_time = models.get_brazil_time()
        
        return {
            "status": "OK",
            "sse_clients_connected": len(sse_clients),
            "buffered_records": len(sensor_buffer),
            "database_total_records": total_records,
            "latest_record_time": latest_time,
            "current_server_time": current_time.isoformat(),
            "timezone": "America/Sao_Paulo",
        }
    finally:
        db.close()

@app.get("/api/debug/fix-temp-pv")
async def fix_temp_pv():
    """Fix old records with temperatura_pv = 25.0 (set to 0)"""
    from sqlalchemy import text
    db = database.SessionLocal()
    try:
        # Set temperatura_pv to 0 where it's 25 (old default value)
        result = db.execute(
            text("UPDATE sensor_data SET temperatura_pv = 0 WHERE temperatura_pv = 25.0")
        )
        db.commit()
        affected_rows = result.rowcount
        logger.info(f"✅ Fixed {affected_rows} records - set temperatura_pv from 25.0°C to 0°C")
        return {
            "message": "Temperature PV fix applied successfully",
            "records_updated": affected_rows,
            "action": "Set temperatura_pv from 25.0°C to 0°C for old records"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error fixing temperatura_pv: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fix temperatura_pv: {str(e)}")
    finally:
        db.close()

@app.get("/api/sensors/", response_model=list[schemas.SensorDataResponse])
async def read_sensor_data(
    skip: int = 0, 
    limit: int = 100, 
    device_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    format: str = "json"
):
    # Parse datetime strings with flexible handling
    start_dt = None
    end_dt = None
    
    logger.info(f"📥 Query received: skip={skip}, limit={limit}, device_id={device_id}, start_time={start_time}, end_time={end_time}")
    
    if start_time:
        try:
            # Handle both "2024-01-01T10:30" and "2024-01-01T10:30:00" formats
            # datetime-local from HTML doesn't include timezone info, so we parse it as naive and then add Brazil timezone
            naive_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            
            # If it's a naive datetime (no timezone), add Brazil timezone
            if naive_dt.tzinfo is None:
                start_dt = models.BRAZIL_TZ.localize(naive_dt)
            else:
                start_dt = naive_dt
            
            logger.info(f"  ✅ Parsed start_time: {start_dt}")
        except Exception as e:
            logger.error(f"  ❌ Failed to parse start_time '{start_time}': {type(e).__name__}: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid start_time format: {str(e)}")
    
    if end_time:
        try:
            naive_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            
            # If it's a naive datetime (no timezone), add Brazil timezone
            if naive_dt.tzinfo is None:
                end_dt = models.BRAZIL_TZ.localize(naive_dt)
            else:
                end_dt = naive_dt
            
            logger.info(f"  ✅ Parsed end_time: {end_dt}")
        except Exception as e:
            logger.error(f"  ❌ Failed to parse end_time '{end_time}': {type(e).__name__}: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid end_time format: {str(e)}")
    
    try:
        sensors = await asyncio.to_thread(
            read_sensor_data_sync,
            skip,
            limit,
            device_id,
            start_dt,
            end_dt,
        )
    except Exception as e:
        logger.error(f"❌ Error executing query: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
    
    logger.info(f"✅ Query returned {len(sensors)} records")
    
    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "device_id", "tensao_shunt", "irradiance", "irradiance_cell", "temperatura", "temperatura_pv", "temperatura_ambiente", "timestamp"])
        for sensor in sensors:
            writer.writerow([
                sensor.id, 
                sensor.device_id, 
                sensor.tensao_shunt, 
                sensor.irradiance, 
                sensor.irradiance_cell if sensor.irradiance_cell is not None else "",
                sensor.temperatura if sensor.temperatura is not None else "",
                sensor.temperatura_pv if sensor.temperatura_pv is not None else "",
                sensor.temperatura_ambiente if sensor.temperatura_ambiente is not None else "",
                sensor.timestamp.isoformat() if sensor.timestamp else ""
            ])
        return Response(
            content=output.getvalue(), 
            media_type="text/csv", 
            headers={"Content-Disposition": "attachment; filename=sensors_data.csv"}
        )
        
    return sensors

@app.get("/api/sensors/count")
async def count_sensors():
    """Get total number of sensor records in database"""
    db = database.SessionLocal()
    try:
        total = db.query(models.SensorData).count()
        latest = db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).first()
        
        response = {
            "total_records": total,
            "latest_timestamp": latest.timestamp.isoformat() if latest else None,
            "latest_device": latest.device_id if latest else None,
            "buffer_count": len(sensor_buffer),
            "connected_clients": len(sse_clients)
        }
        
        if total > 0:
            logger.info(f"✅ Dados encontrados! Total: {total} registros")
        
        return response
    finally:
        db.close()
