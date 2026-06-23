#!/usr/bin/env python3
"""Fix temperatura_pv and temperatura_ambiente - divide values > 1000 by 100 (scale fix)"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    print("🔧 Corrigindo escala de temperatura (dividindo por 100 valores > 1000)...")
    
    # Fix temperatura_pv
    result_pv = db.execute(
        text("UPDATE sensor_data SET temperatura_pv = temperatura_pv / 100 WHERE temperatura_pv > 1000")
    )
    db.commit()
    print(f"  ✅ temperatura_pv: {result_pv.rowcount} registro(s) corrigido(s)")
    
    # Fix temperatura_ambiente
    result_amb = db.execute(
        text("UPDATE sensor_data SET temperatura_ambiente = temperatura_ambiente / 100 WHERE temperatura_ambiente > 1000")
    )
    db.commit()
    print(f"  ✅ temperatura_ambiente: {result_amb.rowcount} registro(s) corrigido(s)")
    
    print("✅ Migração concluída!")
    
except Exception as e:
    db.rollback()
    print(f"❌ Erro: {e}")
finally:
    db.close()
