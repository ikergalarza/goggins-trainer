"""Configuración compartida de pytest para el backend.

Monta una base de datos SQLite en memoria por test, crea todas las tablas a
partir de los modelos SQLAlchemy y expone fixtures reutilizables (sesión de DB,
usuario sembrado, objetivos y workouts de prueba).

NOTA: La app real usa PostgreSQL y construye un engine a nivel de módulo en
`app.db.database` (incluyendo `sslmode=require`). Esos tests NO usan ese engine:
los servicios y las tools aceptan una `Session` como parámetro, así que les
pasamos nuestra sesión SQLite; y para las rutas FastAPI sobreescribimos la
dependencia `get_db`. Aun así, hay que fijar `DATABASE_URL` ANTES de importar
cualquier módulo de `app`, porque `app.core.config.Settings` lo exige.
"""
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# 1) DATABASE_URL debe existir antes de importar app.* (Settings lo requiere y
#    database.py construye el engine en import). Usamos SQLite en memoria; el
#    sufijo sslmode que añade database.py no se evalúa hasta que alguien conecta
#    con ESE engine, cosa que estos tests nunca hacen.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

# 2) Asegura que el paquete `app` es importable (raíz = backend/).
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
import app.models  # noqa: F401  (registra todos los modelos en Base.metadata)
from app.models.user import User
from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.strava_activity import StravaActivity


@pytest.fixture()
def engine():
    """Engine SQLite en memoria, compartido entre conexiones del mismo test."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Sesión de DB de prueba sobre el engine en memoria."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db):
    """Usuario sembrado básico."""
    u = User(
        name="Test Atleta",
        email="atleta@test.io",
        age=30,
        sex="M",
        weight_kg=72.0,
        experience_level="intermediate",
        years_training=4,
        training_days_per_week=5,
        max_heart_rate=190,
        resting_heart_rate=50,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def other_user(db):
    """Segundo usuario, para probar la validación de ownership."""
    u = User(name="Otro", email="otro@test.io", age=40)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_goal(db, user, **overrides):
    defaults = dict(
        user_id=user.id,
        sport="running",
        type=GoalType.race,
        description="10k sub-40",
        target_race_distance_km=10.0,
        is_active=True,
    )
    defaults.update(overrides)
    g = Goal(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@pytest.fixture()
def goal(db, user):
    return _make_goal(db, user)


@pytest.fixture()
def make_goal(db):
    """Factory para crear goals con overrides."""
    def _factory(user, **overrides):
        return _make_goal(db, user, **overrides)
    return _factory


def _make_workout(db, user, goal=None, **overrides):
    defaults = dict(
        user_id=user.id,
        goal_id=goal.id if goal else None,
        date=date(2026, 1, 5),  # lunes
        day_of_week=0,
        week_index=1,
        type=WorkoutType.easy_run,
        status=WorkoutStatus.planned,
        planned_distance_km=8.0,
        planned_duration_min=50,
        planned_heart_rate_zone="Z2",
        instructions="Trote suave",
        modified_by="ai",
    )
    defaults.update(overrides)
    w = Workout(**defaults)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture()
def make_workout(db):
    """Factory para sembrar workouts."""
    def _factory(user, goal=None, **overrides):
        return _make_workout(db, user, goal, **overrides)
    return _factory


@pytest.fixture()
def make_strava_activity(db):
    """Factory para sembrar actividades de Strava."""
    _counter = {"n": 0}

    def _factory(user, **overrides):
        _counter["n"] += 1
        defaults = dict(
            user_id=user.id,
            strava_id=1000 + _counter["n"],
            name="Carrera matutina",
            type="Run",
            distance_m=8200.0,
            moving_time_s=2900,
            average_heartrate=152.0,
            max_heartrate=178.0,
            start_date=datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        a = StravaActivity(**defaults)
        db.add(a)
        db.commit()
        db.refresh(a)
        return a

    return _factory
