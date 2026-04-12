from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.database import Base


class PersonalRecord(Base):
    """Marca personal — distancias, tests, Hyrox, fuerza, etc."""
    __tablename__ = "personal_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Categoría libre para soportar muchos tipos:
    # running: "5k", "10k", "21k", "42k", "1mile", "vam_test"
    # hyrox:   "hyrox_full", "hyrox_run_only", "hyrox_roxzone"
    # fuerza:  "squat_1rm", "deadlift_1rm", "bench_1rm", "wall_balls"
    category = Column(String, nullable=False, index=True)

    # Valor numérico — interpretación depende de `unit`
    value_seconds = Column(Integer, nullable=True)  # tiempos
    value_numeric = Column(Float, nullable=True)    # kg, m/s, reps...
    unit = Column(String, nullable=True)            # "seconds" | "kg" | "m/s" | "reps"

    date_achieved = Column(Date, nullable=False)
    strava_activity_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
