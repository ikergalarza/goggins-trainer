from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)

    # Datos físicos
    age = Column(Integer)
    weight_kg = Column(Float)
    height_cm = Column(Float)
    resting_heart_rate = Column(Integer)
    max_heart_rate = Column(Integer)

    # Zonas cardíacas (calculadas o manuales)
    heart_rate_zones = Column(JSON)  # {"z1": [0,120], "z2": [120,140], ...}

    # Strava
    strava_athlete_id = Column(String, unique=True, nullable=True)
    strava_access_token = Column(String, nullable=True)
    strava_refresh_token = Column(String, nullable=True)
    strava_token_expires_at = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
