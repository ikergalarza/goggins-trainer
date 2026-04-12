from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, Enum, Text, DateTime
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class GoalType(str, enum.Enum):
    race = "race"               # carrera de running (5k, 10k, 21k, 42k, trail, ...)
    hyrox = "hyrox"             # competición Hyrox
    weekly_km = "weekly_km"     # volumen semanal
    fitness = "fitness"         # mejorar condición general
    custom = "custom"


class Sport(str, enum.Enum):
    running = "running"
    hyrox = "hyrox"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    sport = Column(String, nullable=True)        # running | hyrox
    type = Column(Enum(GoalType), nullable=False)
    description = Column(String, nullable=False)

    # Carrera de running
    target_race_distance_km = Column(Float, nullable=True)
    target_race_date = Column(Date, nullable=True)
    target_time_seconds = Column(Integer, nullable=True)  # tiempo objetivo en segundos

    # Hyrox
    hyrox_division = Column(String, nullable=True)   # open | pro | doubles | relay

    # Volumen
    target_weekly_km = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
