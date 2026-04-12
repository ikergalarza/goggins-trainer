from sqlalchemy import Column, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base


class ActivityDetail(Base):
    """Datos extendidos de una actividad de Strava (streams, laps, segmentos).

    Se cachean en BD la primera vez que el usuario abre el detalle de la
    actividad para no machacar la API de Strava.
    """
    __tablename__ = "activity_details"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("strava_activities.id"), unique=True, index=True, nullable=False)

    # Streams: time, distance, heartrate, altitude, velocity_smooth, cadence...
    streams = Column(JSON, nullable=True)
    # Splits/laps generados por el dispositivo
    laps = Column(JSON, nullable=True)
    # Segmentos cruzados durante la actividad
    segment_efforts = Column(JSON, nullable=True)

    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
