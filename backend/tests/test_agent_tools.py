"""Tests de las tools del agente (agent_tools).

Cubre:
- shift_plan: desplaza en bloque los workouts futuros N días/semanas.
- adjust_week_load: escala distancia/duración de una semana por un factor,
  respetando los workouts de descanso.
- Validación de ownership: las tools no tocan workouts de otro usuario.
"""
from datetime import date

import pytest

from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.services.agent_tools import execute_tool, _get_user_workout


# ────────────────────────────────────────────────────────────────────
# shift_plan
# ────────────────────────────────────────────────────────────────────

def test_shift_plan_desplaza_dias(db, user, make_workout):
    w1 = make_workout(user, date=date(2026, 1, 5), day_of_week=0)
    w2 = make_workout(user, date=date(2026, 1, 8), day_of_week=3)

    res = execute_tool(
        "shift_plan",
        {"days": 3, "from_date": "2026-01-01"},
        user,
        db,
    )
    assert res["ok"] is True
    assert res["shifted_count"] == 2
    assert res["shift_days"] == 3

    db.refresh(w1)
    db.refresh(w2)
    assert w1.date == date(2026, 1, 8)
    assert w1.day_of_week == date(2026, 1, 8).weekday()
    assert w2.date == date(2026, 1, 11)


def test_shift_plan_semanas(db, user, make_workout):
    w = make_workout(user, date=date(2026, 1, 5))
    res = execute_tool("shift_plan", {"weeks": 1, "from_date": "2026-01-01"}, user, db)
    assert res["ok"] is True
    assert res["shift_days"] == 7
    db.refresh(w)
    assert w.date == date(2026, 1, 12)


def test_shift_plan_respeta_from_date(db, user, make_workout):
    pasado = make_workout(user, date=date(2025, 12, 30))
    futuro = make_workout(user, date=date(2026, 1, 10))
    res = execute_tool("shift_plan", {"days": 2, "from_date": "2026-01-01"}, user, db)
    assert res["shifted_count"] == 1  # solo el futuro
    db.refresh(pasado)
    db.refresh(futuro)
    assert pasado.date == date(2025, 12, 30)  # intacto
    assert futuro.date == date(2026, 1, 12)


def test_shift_plan_sin_desplazamiento_falla(db, user):
    res = execute_tool("shift_plan", {}, user, db)
    assert res["ok"] is False
    assert "days" in res["error"] or "weeks" in res["error"]


def test_shift_plan_cero_falla(db, user, make_workout):
    make_workout(user, date=date(2026, 1, 5))
    res = execute_tool("shift_plan", {"days": 0}, user, db)
    assert res["ok"] is False


def test_shift_plan_no_toca_workouts_de_otro_usuario(db, user, other_user, make_workout):
    mio = make_workout(user, date=date(2026, 1, 10))
    ajeno = make_workout(other_user, date=date(2026, 1, 10))
    res = execute_tool("shift_plan", {"days": 5, "from_date": "2026-01-01"}, user, db)
    assert res["shifted_count"] == 1
    db.refresh(mio)
    db.refresh(ajeno)
    assert mio.date == date(2026, 1, 15)
    assert ajeno.date == date(2026, 1, 10)  # intacto


# ────────────────────────────────────────────────────────────────────
# adjust_week_load
# ────────────────────────────────────────────────────────────────────

def test_adjust_week_load_baja_carga(db, user, make_workout):
    w = make_workout(
        user, date=date(2026, 1, 5), planned_distance_km=10.0, planned_duration_min=60
    )
    res = execute_tool(
        "adjust_week_load",
        {"week_start_date": "2026-01-05", "factor": 0.8},
        user,
        db,
    )
    assert res["ok"] is True
    assert res["adjusted_count"] == 1
    db.refresh(w)
    assert w.planned_distance_km == 8.0
    assert w.planned_duration_min == 48


def test_adjust_week_load_sube_carga(db, user, make_workout):
    w = make_workout(
        user, date=date(2026, 1, 6), planned_distance_km=10.0, planned_duration_min=60
    )
    res = execute_tool(
        "adjust_week_load",
        {"week_start_date": "2026-01-05", "factor": 1.15},
        user,
        db,
    )
    assert res["ok"] is True
    db.refresh(w)
    assert w.planned_distance_km == 11.5
    assert w.planned_duration_min == 69


def test_adjust_week_load_no_toca_rest(db, user, make_workout):
    rest = make_workout(
        user,
        date=date(2026, 1, 7),
        type=WorkoutType.rest,
        planned_distance_km=None,
        planned_duration_min=None,
    )
    run = make_workout(
        user, date=date(2026, 1, 8), planned_distance_km=10.0, planned_duration_min=60
    )
    res = execute_tool(
        "adjust_week_load",
        {"week_start_date": "2026-01-05", "factor": 0.5},
        user,
        db,
    )
    assert res["adjusted_count"] == 1  # solo el run
    db.refresh(run)
    assert run.planned_distance_km == 5.0


def test_adjust_week_load_solo_la_semana_indicada(db, user, make_workout):
    dentro = make_workout(user, date=date(2026, 1, 5), planned_distance_km=10.0)
    fuera = make_workout(user, date=date(2026, 1, 12), planned_distance_km=10.0)
    execute_tool(
        "adjust_week_load",
        {"week_start_date": "2026-01-05", "factor": 2.0},
        user,
        db,
    )
    db.refresh(dentro)
    db.refresh(fuera)
    assert dentro.planned_distance_km == 20.0
    assert fuera.planned_distance_km == 10.0  # semana siguiente, intacto


def test_adjust_week_load_factor_invalido(db, user):
    res = execute_tool("adjust_week_load", {"week_start_date": "2026-01-05", "factor": 0}, user, db)
    assert res["ok"] is False


def test_adjust_week_load_no_toca_otro_usuario(db, user, other_user, make_workout):
    ajeno = make_workout(other_user, date=date(2026, 1, 5), planned_distance_km=10.0)
    res = execute_tool(
        "adjust_week_load",
        {"week_start_date": "2026-01-05", "factor": 0.5},
        user,
        db,
    )
    assert res["adjusted_count"] == 0
    db.refresh(ajeno)
    assert ajeno.planned_distance_km == 10.0


# ────────────────────────────────────────────────────────────────────
# Ownership en tools por-workout (move/update/delete)
# ────────────────────────────────────────────────────────────────────

def test_get_user_workout_solo_devuelve_los_del_usuario(db, user, other_user, make_workout):
    ajeno = make_workout(other_user, date=date(2026, 1, 5))
    assert _get_user_workout(ajeno.id, user, db) is None
    assert _get_user_workout(ajeno.id, other_user, db) is not None


def test_move_workout_ajeno_devuelve_no_encontrado(db, user, other_user, make_workout):
    ajeno = make_workout(other_user, date=date(2026, 1, 5))
    res = execute_tool(
        "move_workout",
        {"workout_id": ajeno.id, "new_date": "2026-01-09"},
        user,
        db,
    )
    assert res["ok"] is False
    assert "no encontrado" in res["error"].lower()
    db.refresh(ajeno)
    assert ajeno.date == date(2026, 1, 5)  # intacto


def test_delete_workout_ajeno_no_borra(db, user, other_user, make_workout):
    ajeno = make_workout(other_user, date=date(2026, 1, 5))
    res = execute_tool("delete_workout", {"workout_id": ajeno.id}, user, db)
    assert res["ok"] is False
    # Sigue existiendo
    assert db.query(Workout).filter(Workout.id == ajeno.id).first() is not None


def test_tool_desconocida(db, user):
    res = execute_tool("no_existe", {}, user, db)
    assert res["ok"] is False
    assert "desconocida" in res["error"].lower()
