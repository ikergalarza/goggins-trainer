from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Railway inyecta postgres://, SQLAlchemy necesita postgresql://
_db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Añadir sslmode=require si no está ya en la URL
if "sslmode" not in _db_url:
    _separator = "&" if "?" in _db_url else "?"
    _db_url = f"{_db_url}{_separator}sslmode=require"

engine = create_engine(_db_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
