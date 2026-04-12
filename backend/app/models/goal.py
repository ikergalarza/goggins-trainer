from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy import DateTime
from app.db.database import Base
import enum


class GoalType(str, enum.Enum):
    weekly_km = "weekly_km"
    race = "race"         # preparar una carrera concreta
    weight_loss = "weight_loss"
    fitness = "fitness"   # mejorar condición general
    custom = "custom"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    type = Column(Enum(GoalType), nullable=False)
    description = Column(String, nullable=False)

    # Valores numéricos según el tipo
    target_weekly_km = Column(Float, nullable=True)
    target_race_distance_km = Column(Float, nullable=True)
    target_race_date = Column(Date, nullable=True)
    target_weight_kg = Column(Float, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
