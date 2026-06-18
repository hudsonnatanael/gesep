import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Use SQLite by default (no external database needed)
# Set DATABASE_URL=postgresql://... to use PostgreSQL
db_url = os.getenv("DATABASE_URL")

if db_url:
    # Use PostgreSQL if specified
    SQLALCHEMY_DATABASE_URL = db_url
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"options": "-c timezone=America/Sao_Paulo"}
    )
else:
    # Use SQLite locally (easier for development)
    db_path = Path(__file__).parent.parent / "sensor_data.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_path}"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
