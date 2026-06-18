#!/usr/bin/env python3
"""Add temperatura column to sensor_data table if it doesn't exist"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    # Check if column exists
    result = db.execute(
        text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'sensor_data' 
            AND column_name = 'temperatura'
        );
        """)
    )
    
    column_exists = result.scalar()
    
    if column_exists:
        print("✅ Coluna 'temperatura' já existe!")
    else:
        print("🔧 Adicionando coluna 'temperatura' ao banco...")
        
        # Add column with default value of 25.0
        db.execute(
            text("""
            ALTER TABLE sensor_data 
            ADD COLUMN temperatura FLOAT NOT NULL DEFAULT 25.0
            """)
        )
        db.commit()
        
        print("✅ Coluna 'temperatura' adicionada com sucesso!")
        print("   Valor padrão: 25.0°C para dados antigos")
        
except Exception as e:
    db.rollback()
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
