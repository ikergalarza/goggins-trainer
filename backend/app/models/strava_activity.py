from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.db.database import Base


class StravaActivity(Base):
    __tablename__ = "strava_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    strava_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(String, nullable=True)
    type = Column(String, nullable=True)   # Run, Ride, etc.

    distance_m = Column(Float, nullable=True)
    moving_time_s = Column(Integer, nullable=True)
    elapsed_time_s = Column(Integer, nullable=True)
    elevation_gain_m = Column(Float, nullable=True)

    average_speed_ms = Column(Float, nullable=True)
    max_speed_ms = Column(Float, nullable=True)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)

    start_date = Column(DateTime(timezone=True), nullable=True)

    # Payload completo de Strava por si necesitamos más datos
    raw_data = Column(JSON, nullable=True)

    synced_at = Column(DateTime(timezone=True), server_default=func.now())
