from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Railway inyecta DATABASE_URL como postgres://, SQLAlchemy necesita postgresql://
_db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Railway PostgreSQL requiere SSL
engine = create_engine(_db_url, connect_args={"sslmode": "require"})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
