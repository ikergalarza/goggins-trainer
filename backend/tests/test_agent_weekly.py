"""Herramientas de Goggins para "un día más a la semana" y fechas fiables.

Hasta ahora no había forma de añadir una sesión semanal con WOD a todo el plan,
los entrenos nuevos se asociaban al "último objetivo creado" (no al de su
fecha) y una fecha mal resuelta se aceptaba sin rechistar.
"""
from datetime import date, timedelta

import pytest

from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import agent_tools, wod_structure
from app.services.agent_tools import execute_tool

DOMINGO = date(2026, 11, 22)
HYROX_DAY = date(2027, 2, 7)      # domingo
MEDIA_DAY = date(2027, 4, 4)      # domingo

WOD = {
    "objective": "Tolerancia a wall balls",
    "warmup": {"duration_min": 10, "steps": ["500 m remo suave"]},
    "blocks": [{"title": "Principal", "format": "rounds", "rounds": 4, "rest_s": 120, "items": [
        {"exercise": "run", "distance_m": 400, "pace": "4:40/km"},
        {"exercise": "wall_balls", "reps": 15, "weight_kg": 6},
        {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152}]}],
    "cooldown": ["5' trote suave"],
}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    monkeypatch.setattr(agent_tools, "today_madrid", lambda: DOMINGO)


@pytest.fixture()
def metas(db, user):
    """Dos carreras activas y un plan combinado en vigor (Hyrox hasta feb, media hasta abril)."""
    hyrox = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao", target_race_date=HYROX_DAY, is_active=True)
    media = Goal(user_id=user.id, type=GoalType.race, description="Media SS", target_race_date=MEDIA_DAY, is_active=True)
    db.add_all([hyrox, media]); db.commit()
    return hyrox, media


def _planificar(db, user, goal, lunes: date, semanas: int, dows=(0, 1, 3, 5)):
    for w in range(semanas):
        for d in dows:
            db.add(Workout(user_id=user.id, goal_id=goal.id, date=lunes + timedelta(weeks=w, days=d), day_of_week=d,
                           type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.commit()


def _creados(db, tipo):
    return db.query(Workout).filter(Workout.type == tipo).order_by(Workout.date).all()


# --- add_weekly_session --------------------------------------------------------

def test_un_dia_mas_por_semana_elige_un_dia_libre_y_cubre_las_semanas(db, user, metas):
    hyrox, _ = metas
    _planificar(db, user, hyrox, date(2026, 11, 23), 3)             # lun, mar, jue, sáb ocupados
    out = execute_tool("add_weekly_session", {"type": "hyrox_stations", "end_date": "2026-12-13"}, user, db)
    assert out["ok"] and out["mutation"] == "add_weekly_session"
    ws = _creados(db, WorkoutType.hyrox_stations)
    assert out["created"] == len(ws) == 3                            # una por semana
    assert {w.date.weekday() for w in ws} <= {2, 4, 6}               # nunca un día ya ocupado
    assert len({w.date.weekday() for w in ws}) == 1                  # siempre el MISMO día de la semana
    assert out["weekday"] in ("miércoles", "viernes", "domingo")
    assert all(w.goal_id == hyrox.id and w.status == WorkoutStatus.planned for w in ws)


def test_con_dia_y_wod_las_sesiones_llevan_estructura_y_duracion_calculada(db, user, metas):
    out = execute_tool("add_weekly_session", {
        "type": "hyrox_stations", "weekday": 4, "end_date": "2026-12-11", "structure": WOD, "duration_min": 90,
    }, user, db)
    ws = _creados(db, WorkoutType.hyrox_stations)
    assert [str(w.date) for w in ws] == ["2026-11-27", "2026-12-04", "2026-12-11"]     # viernes
    assert out["weekday"] == "viernes"
    for w in ws:
        assert w.structure["blocks"][0]["items"][1]["weight_kg"] == 6
        assert 35 <= w.planned_duration_min <= 42                  # calculada del WOD, no el 90 a ojo
        assert w.structure["estimate"]["warmup_min"] == 10


def test_por_defecto_cubre_hasta_la_ultima_carrera_saltando_las_semanas_de_carrera(db, user, metas):
    hyrox, media = metas
    out = execute_tool("add_weekly_session", {"type": "easy_run", "weekday": 2, "distance_km": 6}, user, db)
    ws = _creados(db, WorkoutType.easy_run)
    fechas = [w.date for w in ws]
    assert fechas[0] == date(2026, 11, 25) and all(f.weekday() == 2 for f in fechas)
    assert fechas[-1] <= MEDIA_DAY
    # nada en la semana de cada carrera (lunes 1 feb – dom 7 feb, lunes 29 mar – dom 4 abr)
    assert not [f for f in fechas if date(2027, 2, 1) <= f <= HYROX_DAY or date(2027, 3, 29) <= f <= MEDIA_DAY]
    # cada sesión va al objetivo de SU bloque
    assert all(w.goal_id == (hyrox.id if w.date <= HYROX_DAY else media.id) for w in ws)
    assert out["created"] == len(ws) and out["skipped_race_weeks"] == 2


def test_no_planifica_en_el_pasado(db, user, metas):
    out = execute_tool("add_weekly_session", {"type": "easy_run", "weekday": 0, "start_date": "2026-11-16", "end_date": "2026-12-07"}, user, db)
    assert [str(w.date) for w in _creados(db, WorkoutType.easy_run)] == ["2026-11-23", "2026-11-30", "2026-12-07"]
    assert out["ok"]


def test_repetir_la_peticion_no_duplica(db, user, metas):
    args = {"type": "easy_run", "weekday": 4, "end_date": "2026-12-11"}
    execute_tool("add_weekly_session", args, user, db)
    again = execute_tool("add_weekly_session", args, user, db)
    assert len(_creados(db, WorkoutType.easy_run)) == 3
    assert not again["ok"] and "ya" in again["error"].lower()


@pytest.mark.parametrize("args", [
    {"type": "inventado"},
    {"type": "race"},
    {"type": "easy_run", "weekday": 9},
    {"type": "easy_run", "start_date": "2026-12-10", "end_date": "2026-12-01"},
    {"type": "easy_run", "weekday": 2, "start_date": "2025-11-26", "end_date": "2025-12-10"},   # año equivocado
])
def test_peticiones_invalidas_se_rechazan_sin_crear_nada(db, user, metas, args):
    out = execute_tool("add_weekly_session", args, user, db)
    assert not out["ok"] and out["error"]
    assert db.query(Workout).count() == 0


# --- add_recurring_workout: ahora con WOD y objetivo por fecha ----------------

def test_recurrente_acepta_wod_y_asocia_cada_fecha_a_su_bloque(db, user, metas):
    hyrox, media = metas
    out = execute_tool("add_recurring_workout", {
        "type": "strength_lower", "start_date": "2027-02-01", "end_date": "2027-02-22",
        "days_of_week": [1], "structure": WOD,
    }, user, db)
    ws = _creados(db, WorkoutType.strength_lower)
    assert out["ok"] and [str(w.date) for w in ws] == ["2027-02-02", "2027-02-09", "2027-02-16"]
    assert [w.goal_id for w in ws] == [hyrox.id, media.id, media.id]          # el 9 feb ya es del bloque de la media
    assert all(w.structure and w.planned_duration_min for w in ws)


# --- objetivo por fecha en add_workout ----------------------------------------

def test_add_workout_se_asocia_al_objetivo_de_su_fecha(db, user, metas):
    hyrox, media = metas
    _planificar(db, user, hyrox, date(2026, 11, 23), 1)
    _planificar(db, user, media, date(2027, 2, 8), 1)
    a = execute_tool("add_workout", {"date": "2026-12-01", "type": "easy_run"}, user, db)
    b = execute_tool("add_workout", {"date": "2027-03-02", "type": "easy_run"}, user, db)
    assert db.query(Workout).get(a["workout_id"]).goal_id == hyrox.id
    assert db.query(Workout).get(b["workout_id"]).goal_id == media.id


def test_un_goal_id_inventado_se_ignora_y_uno_propio_se_respeta(db, user, metas, other_user):
    hyrox, media = metas
    ajeno = Goal(user_id=other_user.id, type=GoalType.race, description="De otro", is_active=True)
    db.add(ajeno); db.commit()
    _planificar(db, user, hyrox, date(2026, 11, 23), 1)
    malo = execute_tool("add_workout", {"date": "2026-12-01", "type": "easy_run", "goal_id": 99999}, user, db)
    de_otro = execute_tool("add_workout", {"date": "2026-12-02", "type": "easy_run", "goal_id": ajeno.id}, user, db)
    bueno = execute_tool("add_workout", {"date": "2026-12-03", "type": "easy_run", "goal_id": media.id}, user, db)
    assert db.query(Workout).get(malo["workout_id"]).goal_id == hyrox.id
    assert db.query(Workout).get(de_otro["workout_id"]).goal_id == hyrox.id
    assert db.query(Workout).get(bueno["workout_id"]).goal_id == media.id


def test_add_workout_avisa_si_ya_hay_algo_ese_dia(db, user, metas):
    hyrox, _ = metas
    _planificar(db, user, hyrox, date(2026, 11, 23), 1)                       # lunes 23 ocupado
    out = execute_tool("add_workout", {"date": "2026-11-23", "type": "mobility"}, user, db)
    assert out["ok"] and out["weekday"] == "lunes"
    assert [o["type"] for o in out["same_day_other_workouts"]] == ["easy_run"]


# --- fechas: la de hoy es la de España y lo absurdo se rechaza -----------------

@pytest.mark.parametrize("fecha", ["2025-11-27", "2030-01-01", "2026-10-01"])
def test_add_workout_rechaza_fechas_lejanas_a_hoy(db, user, metas, fecha):
    out = execute_tool("add_workout", {"date": fecha, "type": "easy_run"}, user, db)
    assert not out["ok"] and "domingo 2026-11-22" in out["error"]
    assert db.query(Workout).count() == 0


def test_mover_a_una_fecha_absurda_se_rechaza(db, user, metas, make_workout):
    w = make_workout(user, date=date(2026, 11, 24))
    out = execute_tool("move_workout", {"workout_id": w.id, "new_date": "2025-11-27"}, user, db)
    assert not out["ok"]
    db.refresh(w)
    assert w.date == date(2026, 11, 24)


def test_list_y_shift_usan_el_hoy_de_españa_no_el_del_servidor(db, user, metas, make_workout):
    ayer = make_workout(user, date=date(2026, 11, 21))
    hoy = make_workout(user, date=date(2026, 11, 22))
    lst = execute_tool("list_workouts", {}, user, db)
    assert [w["id"] for w in lst["workouts"]] == [hoy.id]
    execute_tool("shift_plan", {"days": 1}, user, db)
    db.refresh(ayer); db.refresh(hoy)
    assert ayer.date == date(2026, 11, 21) and hoy.date == date(2026, 11, 23)


# --- set_training_days_per_week ------------------------------------------------

def test_guarda_los_dias_de_entreno_por_semana(db, user):
    out = execute_tool("set_training_days_per_week", {"days": 6}, user, db)
    assert out["ok"] and out["mutation"] == "set_training_days_per_week"
    db.refresh(user)
    assert user.training_days_per_week == 6


@pytest.mark.parametrize("dias", [0, 8, "muchos", None])
def test_dias_de_entreno_invalidos(db, user, dias):
    out = execute_tool("set_training_days_per_week", {"days": dias}, user, db)
    assert not out["ok"]
    db.refresh(user)
    assert user.training_days_per_week == 5          # el del fixture, intacto
