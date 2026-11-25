"""Migraciones idempotentes en runtime.

Añade columnas nuevas a tablas existentes sin necesidad de Alembic.
Se ejecuta en el lifespan del FastAPI tras create_all.

IMPORTANTE (un despliegue fallido): un `ALTER TABLE` pide un bloqueo EXCLUSIVO
aunque la columna ya exista. Con una conversación con Goggins abierta, el
arranque esperaba ese bloqueo hasta que el healthcheck (60 s) tumbaba el
despliegue, y el resto de consultas se encolaban detrás. Por eso aquí SOLO se
ejecuta DDL cuando falta algo, y nunca se espera un bloqueo más de 3 s.
"""
import logging
from sqlalchemy import inspect, text

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
    ("users", "vam_updated_at", "TIMESTAMPTZ"),
    ("users", "adaptive_paces", "JSON"),
    ("users", "station_feedback", "JSON"),

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
    ("workouts", "structure", "JSON"),
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
            "race",
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


# Tiempo máximo esperando un bloqueo: si la tabla está en uso, no se cuelga el arranque.
_LOCK_TIMEOUT = "3s"

# DDL suelto de PostgreSQL. `needed` devuelve alguna fila SOLO si hay que ejecutar `sql`.
RAW_DDL = [
    # strava_activities: pasar de UNIQUE(strava_id) global a UNIQUE(user_id, strava_id).
    # La constraint vieja la generó SQLAlchemy con este nombre por defecto.
    {
        "needed": "SELECT 1 FROM pg_constraint WHERE conname = 'strava_activities_strava_id_key'",
        "sql": "ALTER TABLE strava_activities DROP CONSTRAINT IF EXISTS strava_activities_strava_id_key",
    },
    {
        "needed": "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_strava_user_activity')",
        "sql": "ALTER TABLE strava_activities ADD CONSTRAINT uq_strava_user_activity UNIQUE (user_id, strava_id)",
    },
    # El modelo declara strava_id con index=True; en una BD ya existente
    # create_all no lo crea, así que lo garantizamos aquí (modelo <-> BD).
    {
        "needed": "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_strava_activities_strava_id')",
        "sql": "CREATE INDEX IF NOT EXISTS ix_strava_activities_strava_id ON strava_activities (strava_id)",
    },
]


def _is_postgres(engine) -> bool:
    return engine.dialect.name == "postgresql"


def _missing_columns(engine, columns):
    """De `columns` (tabla, columna, tipo), las que faltan en tablas que existen."""
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    have: dict[str, set[str]] = {}
    missing = []
    for table, column, col_type in columns:
        if table not in tables:
            continue                      # create_all la crea ya completa
        if table not in have:
            have[table] = {c["name"] for c in insp.get_columns(table)}
        if column not in have[table]:
            missing.append((table, column, col_type))
    return missing


def _run_ddl(engine, sql: str, label: str) -> None:
    """Una sentencia en su propia transacción, sin esperar bloqueos más de _LOCK_TIMEOUT."""
    try:
        with engine.begin() as conn:
            if _is_postgres(engine):
                conn.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
            conn.execute(text(sql))
        logger.info(f"[migrations] OK {label}")
    except Exception as e:
        logger.warning(f"[migrations] {label} falló: {e}")


def _add_columns(engine, columns) -> None:
    guard = "IF NOT EXISTS " if _is_postgres(engine) else ""
    for table, column, col_type in _missing_columns(engine, columns):
        _run_ddl(engine, f"ALTER TABLE {table} ADD COLUMN {guard}{column} {col_type}", f"{table}.{column}")


def _add_enum_values(engine) -> None:
    """Valores de enum que faltan. ALTER TYPE ADD VALUE no puede ir en una transacción
    en algunas versiones de Postgres → AUTOCOMMIT."""
    try:
        with engine.connect() as conn:
            ac = conn.execution_options(isolation_level="AUTOCOMMIT")
            for enum_name, values in ENUM_VALUES_TO_ADD:
                have = {r[0] for r in ac.execute(text(
                    "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :n"
                ), {"n": enum_name})}
                missing = [v for v in values if v not in have]
                if not missing:
                    continue
                ac.execute(text(f"SET lock_timeout = '{_LOCK_TIMEOUT}'"))
                for v in missing:
                    try:
                        ac.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{v}'"))
                        logger.info(f"[migrations] OK enum {enum_name} += {v}")
                    except Exception as e:
                        logger.warning(f"[migrations] enum {enum_name} += {v} falló: {e}")
                ac.execute(text("RESET lock_timeout"))      # la conexión vuelve al pool limpia
    except Exception as e:
        logger.warning(f"[migrations] enum block falló: {e}")


def ensure_schema(engine) -> None:
    """Añade lo que FALTE (columnas, constraints/índices, valores de enum). Idempotente;
    con el esquema al día no ejecuta ningún DDL."""
    _add_columns(engine, COLUMNS_TO_ADD)
    if not _is_postgres(engine):
        return                            # lo de abajo es propio de PostgreSQL
    for item in RAW_DDL:
        try:
            with engine.connect() as conn:
                needed = conn.execute(text(item["needed"])).first() is not None
        except Exception as e:
            logger.warning(f"[migrations] comprobación ddl falló: {e}")
            continue
        if needed:
            _run_ddl(engine, item["sql"], f"ddl: {item['sql'][:60]}")
    _add_enum_values(engine)
