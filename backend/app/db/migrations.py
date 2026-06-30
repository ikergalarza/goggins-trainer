"""Migraciones idempotentes en runtime.

Añade columnas nuevas a tablas existentes sin necesidad de Alembic.
Se ejecuta en el lifespan del FastAPI tras create_all.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# (tabla, columna, definición SQL)
COLUMNS_TO_ADD = [
    # User — auth
    ("users", "hashed_password", "VARCHAR"),
    ("users", "is_master", "BOOLEAN DEFAULT FALSE"),

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

    # Goal — triatlón
    ("goals", "triathlon_distance", "VARCHAR"),     # sprint | olympic | half | ironman
    ("goals", "target_swim_time_seconds", "INTEGER"),
    ("goals", "target_bike_time_seconds", "INTEGER"),
    ("goals", "target_run_time_seconds", "INTEGER"),

    # Workout — vinculación con plan/objetivo
    ("workouts", "goal_id", "INTEGER"),
    ("workouts", "week_index", "INTEGER"),
    ("workouts", "day_of_week", "INTEGER"),

    # Workout — tracking de ediciones (Goggins respeta cambios manuales)
    ("workouts", "modified_by", "VARCHAR"),         # 'ai' | 'user' | null
    ("workouts", "updated_at", "TIMESTAMPTZ DEFAULT now()"),
]

# (enum_type_name, [values]) — ALTER TYPE ADD VALUE IF NOT EXISTS
ENUM_VALUES_TO_ADD = [
    (
        "workouttype",
        [
            "easy_run",
            "tempo",
            "intervals",
            "long_run",
            "recovery",
            "fartlek",
            "hill_repeats",
            "hyrox_sim",
            "hyrox_stations",
            "strength_upper",
            "strength_lower",
            "strength_full",
            "cross_training",
            "mobility",
            "rest",
            # Triatlón / natación / ciclismo
            "swim",
            "bike",
            "brick",
            "transition",
            "swim_technique",
            "open_water",
        ],
    ),
]


def ensure_schema(engine) -> None:
    """Añade columnas nuevas y valores a enums existentes (idempotente)."""
    # 1. Columnas nuevas
    with engine.begin() as conn:
        for table, column, col_type in COLUMNS_TO_ADD:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                ))
                logger.info(f"[migrations] OK {table}.{column}")
            except Exception as e:
                logger.warning(f"[migrations] {table}.{column} falló: {e}")

    # 2. Valores de enum nuevos. ALTER TYPE ADD VALUE no puede ejecutarse en
    #    una transacción en algunas versiones de Postgres → usamos AUTOCOMMIT.
    try:
        with engine.connect() as conn:
            ac = conn.execution_options(isolation_level="AUTOCOMMIT")
            for enum_name, values in ENUM_VALUES_TO_ADD:
                for v in values:
                    try:
                        ac.execute(text(
                            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{v}'"
                        ))
                        logger.info(f"[migrations] OK enum {enum_name} += {v}")
                    except Exception as e:
                        logger.warning(f"[migrations] enum {enum_name} += {v} falló: {e}")
    except Exception as e:
        logger.warning(f"[migrations] enum block falló: {e}")
