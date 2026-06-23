#!/usr/bin/env python3
"""Add temperatura_pv and temperatura_ambiente columns to sensor_data table"""
from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()
try:
    print("🔧 Adicionando colunas de temperatura ao banco...")
    
    # Check if temperatura_pv column exists
    result = db.execute(
        text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'sensor_data' 
            AND column_name = 'temperatura_pv'
        );
        """)
    )
    
    pv_exists = result.scalar()
    
    if not pv_exists:
        print("  🔧 Adicionando coluna 'temperatura_pv'...")
        db.execute(
            text("ALTER TABLE sensor_data ADD COLUMN temperatura_pv FLOAT")
        )
        print("  ✅ Coluna 'temperatura_pv' adicionada!")
    else:
        print("  ℹ️  Coluna 'temperatura_pv' já existe!")
    
    # Check if temperatura_ambiente column exists
    result = db.execute(
        text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = 'sensor_data' 
            AND column_name = 'temperatura_ambiente'
        );
        """)
    )
    
    amb_exists = result.scalar()
    
    if not amb_exists:
        print("  🔧 Adicionando coluna 'temperatura_ambiente'...")
        db.execute(
            text("ALTER TABLE sensor_data ADD COLUMN temperatura_ambiente FLOAT")
        )
        print("  ✅ Coluna 'temperatura_ambiente' adicionada!")
    else:
        print("  ℹ️  Coluna 'temperatura_ambiente' já existe!")
    
    db.commit()
    print("✅ Migração concluída com sucesso!")
    
except Exception as e:
    db.rollback()
    print(f"❌ Erro: {e}")
finally:
    db.close()
