#!/usr/bin/env python3
"""Check database status and ESP32 connectivity"""
from app.database import SessionLocal
from app.models import SensorData
from datetime import datetime, timezone, timedelta
import pytz

db = SessionLocal()
try:
    # Get first and last records
    first = db.query(SensorData).order_by(SensorData.timestamp).first()
    last = db.query(SensorData).order_by(SensorData.timestamp.desc()).first()
    
    total = db.query(SensorData).count()
    
    print(f"\n📊 DATABASE STATUS")
    print(f"{'─' * 50}")
    print(f"Total records: {total}")
    
    if first and last:
        print(f"\nFirst record:  {first.timestamp}")
        print(f"Last record:   {last.timestamp}")
        print(f"Time span:     {last.timestamp - first.timestamp}")
    
    # Check current time in São Paulo timezone
    tz = pytz.timezone('America/Sao_Paulo')
    current_time_br = datetime.now(tz)
    print(f"\n🕐 CURRENT TIME (São Paulo): {current_time_br.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Check if ESP32 is sending recent data
    if last:
        time_diff = current_time_br.replace(tzinfo=None) - last.timestamp
        if time_diff.total_seconds() < 60:
            print("✅ ESP32 IS CONNECTED - Receiving data in real-time!")
        elif time_diff.total_seconds() < 3600:
            print(f"⚠️  ESP32 last sent data {time_diff.total_seconds():.0f} seconds ago")
        else:
            hours = time_diff.total_seconds() / 3600
            print(f"❌ ESP32 NOT CONNECTED - Last data was {hours:.1f} hours ago")
    
finally:
    db.close()
