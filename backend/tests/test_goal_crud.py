"""Tests de CRUD de objetivos (Goal) con sport=triathlon + triathlon_distance.

Se llaman directamente las funciones de la ruta (`create_goal`, `list_goals`,
`update_goal`, `delete_goal`) pasándoles la sesión de prueba, sin levantar el
servidor HTTP (evita depender de httpx/TestClient).

IMPORTANTE (ver issues): el esquema Pydantic `GoalIn` de la ruta NO expone
`triathlon_distance`, así que la API actual no permite fijarlo. Aquí se prueba:
  1) Que la ruta acepta y persiste `sport="triathlon"`.
  2) Que la columna `triathlon_distance` del modelo se persiste y lee a nivel
     ORM (lo que el generador de planes realmente consume).
"""
from datetime import date

import pytest

from app.api.routes.goals import (
    GoalIn,
    create_goal,
    list_goals,
    update_goal,
    delete_goal,
)
from app.models.goal import Goal, GoalType


# ────────────────────────────────────────────────────────────────────
# CRUD vía las funciones de la ruta
# ────────────────────────────────────────────────────────────────────

def test_create_goal_triathlon_sport(db, user):
    body = GoalIn(
        sport="triathlon",
        type="race",
        description="Mi primer olímpico",
        target_race_distance_km=51.5,
        target_race_date=date(2026, 6, 1),
        target_time_seconds=9000,
    )
    out = create_goal(user.id, body, db)
    assert out["sport"] == "triathlon"
    # Se persiste como race pero se expone como 'triathlon' al frontend.
    assert out["type"] == "triathlon"
    assert out["id"] is not None

    stored = db.query(Goal).filter(Goal.id == out["id"]).first()
    assert stored.sport == "triathlon"
    assert stored.type == GoalType.race


def test_create_goal_triathlon_como_lo_manda_el_frontend(db, user):
    """El frontend envía type='triathlon' + triathlon_distance; debe persistir
    como race + sport=triathlon y devolver la distancia (regresión del bug
    'Tipo de objetivo inválido: triathlon')."""
    body = GoalIn(
        sport="triathlon",
        type="triathlon",
        description="Tritour Tossa de Mar 2026",
        triathlon_distance="sprint",
        target_race_date=date(2026, 9, 12),
        target_time_seconds=4740,
    )
    out = create_goal(user.id, body, db)
    assert out["type"] == "triathlon"
    assert out["sport"] == "triathlon"
    assert out["triathlon_distance"] == "sprint"

    stored = db.query(Goal).filter(Goal.id == out["id"]).first()
    assert stored.type == GoalType.race
    assert stored.triathlon_distance == "sprint"


def test_create_goal_tipo_invalido(db, user):
    from fastapi import HTTPException

    body = GoalIn(sport="triathlon", type="no_existe", description="x")
    with pytest.raises(HTTPException) as exc:
        create_goal(user.id, body, db)
    assert exc.value.status_code == 400


def test_list_goals_filtra_por_usuario_y_activo(db, user, other_user):
    create_goal(user.id, GoalIn(sport="triathlon", type="race", description="a", is_active=True), db)
    create_goal(user.id, GoalIn(sport="running", type="fitness", description="b", is_active=False), db)
    create_goal(other_user.id, GoalIn(sport="triathlon", type="race", description="c"), db)

    todos = list_goals(user.id, active_only=False, db=db)
    assert len(todos) == 2
    activos = list_goals(user.id, active_only=True, db=db)
    assert len(activos) == 1
    assert activos[0]["description"] == "a"


def test_update_goal(db, user):
    created = create_goal(
        user.id, GoalIn(sport="triathlon", type="race", description="viejo"), db
    )
    updated = update_goal(
        user.id,
        created["id"],
        GoalIn(sport="triathlon", type="race", description="nuevo", target_weekly_km=50.0),
        db,
    )
    assert updated["description"] == "nuevo"
    assert updated["target_weekly_km"] == 50.0


def test_update_goal_ajeno_404(db, user, other_user):
    from fastapi import HTTPException

    created = create_goal(other_user.id, GoalIn(type="race", description="x"), db)
    with pytest.raises(HTTPException) as exc:
        update_goal(user.id, created["id"], GoalIn(type="race", description="y"), db)
    assert exc.value.status_code == 404


def test_delete_goal(db, user):
    created = create_goal(user.id, GoalIn(type="race", description="x"), db)
    delete_goal(user.id, created["id"], db)
    assert db.query(Goal).filter(Goal.id == created["id"]).first() is None


def test_delete_goal_ajeno_404(db, user, other_user):
    from fastapi import HTTPException

    created = create_goal(other_user.id, GoalIn(type="race", description="x"), db)
    with pytest.raises(HTTPException) as exc:
        delete_goal(user.id, created["id"], db)
    assert exc.value.status_code == 404


# ────────────────────────────────────────────────────────────────────
# triathlon_distance a nivel ORM (no expuesto por GoalIn)
# ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("distance", ["sprint", "olympic", "half", "ironman"])
def test_triathlon_distance_se_persiste_en_modelo(db, user, distance):
    g = Goal(
        user_id=user.id,
        sport="triathlon",
        type=GoalType.race,
        description=f"Triatlón {distance}",
        triathlon_distance=distance,
        target_swim_time_seconds=1800,
        target_bike_time_seconds=4200,
        target_run_time_seconds=3000,
    )
    db.add(g)
    db.commit()
    db.refresh(g)

    stored = db.query(Goal).filter(Goal.id == g.id).first()
    assert stored.sport == "triathlon"
    assert stored.triathlon_distance == distance
    assert stored.target_swim_time_seconds == 1800
    assert stored.target_bike_time_seconds == 4200
    assert stored.target_run_time_seconds == 3000
