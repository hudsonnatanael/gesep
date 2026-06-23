#!/usr/bin/env python3
"""Fix temperatura_pv column - set 25 values to 0 (for old records with default values)"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    print("🔧 Corrigindo valores de temperatura_pv (25°C → 0°C)...")
    
    # Set temperature_pv to 0 where it's 25 (old default value)
    result = db.execute(
        text("UPDATE sensor_data SET temperatura_pv = 0 WHERE temperatura_pv = 25.0")
    )
    db.commit()
    
    affected_rows = result.rowcount
    print(f"✅ Corrigido! {affected_rows} registro(s) atualizado(s)")
    print(f"   temperatura_pv: 25.0°C → 0°C")
    
except Exception as e:
    db.rollback()
    print(f"❌ Erro: {e}")
finally:
    db.close()
