"""Migraciones idempotentes en runtime.

Añade columnas nuevas a tablas existentes sin necesidad de Alembic.
Se ejecuta en el lifespan del FastAPI tras create_all.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# (tabla, columna, definición SQL)
COLUMNS_TO_ADD = [
    # User — campos nuevos
    ("users", "sex", "VARCHAR"),
    ("users", "years_training", "INTEGER"),
    ("users", "experience_level", "VARCHAR"),
    ("users", "training_days_per_week", "INTEGER"),
    ("users", "vam_ms", "DOUBLE PRECISION"),

    # Goal — campos nuevos
    ("goals", "sport", "VARCHAR"),
    ("goals", "target_time_seconds", "INTEGER"),
    ("goals", "hyrox_division", "VARCHAR"),
    ("goals", "notes", "TEXT"),

    # Workout — vinculación con plan/objetivo
    ("workouts", "goal_id", "INTEGER"),
    ("workouts", "week_index", "INTEGER"),
    ("workouts", "day_of_week", "INTEGER"),
]


def ensure_schema(engine) -> None:
    """Añade columnas nuevas a tablas existentes (idempotente)."""
    with engine.begin() as conn:
        for table, column, col_type in COLUMNS_TO_ADD:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                ))
                logger.info(f"[migrations] OK {table}.{column}")
            except Exception as e:
                logger.warning(f"[migrations] {table}.{column} falló: {e}")
