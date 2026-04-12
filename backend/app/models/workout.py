from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey, Enum, Text
from sqlalchemy.sql import func
from app.db.database import Base
import enum


class WorkoutStatus(str, enum.Enum):
    planned = "planned"
    completed = "completed"
    skipped = "skipped"


class WorkoutType(str, enum.Enum):
    easy_run = "easy_run"
    tempo = "tempo"
    intervals = "intervals"
    long_run = "long_run"
    recovery = "recovery"
    strength = "strength"
    rest = "rest"


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    date = Column(Date, nullable=False)
    type = Column(Enum(WorkoutType), nullable=False)
    status = Column(Enum(WorkoutStatus), default=WorkoutStatus.planned)

    # Planificado por la IA
    planned_distance_km = Column(Float, nullable=True)
    planned_duration_min = Column(Integer, nullable=True)
    planned_heart_rate_zone = Column(String, nullable=True)
    instructions = Column(Text, nullable=True)  # descripción generada por Claude

    # Real (de Strava o feedback manual)
    actual_distance_km = Column(Float, nullable=True)
    actual_duration_min = Column(Integer, nullable=True)
    actual_avg_heart_rate = Column(Integer, nullable=True)
    actual_max_heart_rate = Column(Integer, nullable=True)
    strava_activity_id = Column(String, nullable=True)

    # Feedback del usuario
    perceived_effort = Column(Integer, nullable=True)  # 1-10
    notes = Column(Text, nullable=True)

    # Análisis de Claude post-entreno
    ai_feedback = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
