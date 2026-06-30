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
    # Nota: el triatlón se modela reutilizando type=race con sport=triathlon
    # (es una "carrera" con fecha y tiempo objetivo). La distancia concreta
    # del triatlón se guarda en la columna triathlon_distance, no en GoalType,
    # para no inflar el enum ni romper registros existentes.


class Sport(str, enum.Enum):
    running = "running"
    hyrox = "hyrox"
    triathlon = "triathlon"


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

    # Triatlón (sport=triathlon, type=race)
    triathlon_distance = Column(String, nullable=True)  # sprint | olympic | half | ironman
    # Splits objetivo opcionales por disciplina (en segundos)
    target_swim_time_seconds = Column(Integer, nullable=True)
    target_bike_time_seconds = Column(Integer, nullable=True)
    target_run_time_seconds = Column(Integer, nullable=True)

    # Volumen
    target_weekly_km = Column(Float, nullable=True)

    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
