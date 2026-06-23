#!/usr/bin/env python3
"""Fix temperatura column - allow NULL values for backward compatibility"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    print("🔧 Alterando coluna 'temperatura' para aceitar NULL...")
    
    db.execute(
        text("ALTER TABLE sensor_data ALTER COLUMN temperatura DROP NOT NULL")
    )
    db.commit()
    
    print("✅ Coluna 'temperatura' agora aceita NULL!")
    
except Exception as e:
    db.rollback()
    print(f"❌ Erro: {e}")
finally:
    db.close()
