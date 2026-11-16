"""Tests del generador de planes.

Cubre:
- `_compute_weeks`: cálculo de semanas (Monday-based) hasta la carrera.
- El cálculo de `workout_date` (cada workout cae en el lunes correcto de su
  semana, replicando la fórmula del save loop de `generate_plan_stream`).
- `_parse_response`: parseo del JSON devuelto por Claude, incluyendo planes
  multideporte (swim/bike/brick).
"""
from datetime import date, timedelta

import pytest

from app.models.goal import Goal, GoalType
from app.services import plan_generator
from app.services.plan_generator import _compute_weeks, _parse_response


# ────────────────────────────────────────────────────────────────────
# _compute_weeks  (semanas Monday-based hasta la carrera, incl. semana de carrera)
# ────────────────────────────────────────────────────────────────────

def test_compute_weeks_sin_fecha_devuelve_8():
    goal = Goal(type=GoalType.race, description="sin fecha", target_race_date=None)
    assert _compute_weeks(goal) == 8


def test_compute_weeks_carrera_misma_semana_es_1(monkeypatch):
    # Fijamos "hoy" = miércoles 7 enero 2026; la carrera es el viernes de la
    # misma semana → el plan dura 1 semana (la de la competición).
    fake_today = date(2026, 1, 7)  # miércoles
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: fake_today)
    goal = Goal(type=GoalType.race, description="x", target_race_date=date(2026, 1, 9))
    assert _compute_weeks(goal) == 1


def test_compute_weeks_carrera_semana_siguiente_es_2(monkeypatch):
    fake_today = date(2026, 1, 7)  # miércoles, semana del lunes 5 ene
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: fake_today)
    # Carrera el lunes 12 ene (semana siguiente) → 2 semanas.
    goal = Goal(type=GoalType.race, description="x", target_race_date=date(2026, 1, 12))
    assert _compute_weeks(goal) == 2


def test_compute_weeks_doce_semanas(monkeypatch):
    fake_today = date(2026, 1, 5)  # lunes
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: fake_today)
    # 11 semanas después + la propia semana de carrera = 12.
    race = date(2026, 1, 5) + timedelta(weeks=11)
    goal = Goal(type=GoalType.race, description="x", target_race_date=race)
    assert _compute_weeks(goal) == 12


def test_compute_weeks_se_capa_en_30(monkeypatch):
    fake_today = date(2026, 1, 5)
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: fake_today)
    race = date(2026, 1, 5) + timedelta(weeks=60)
    goal = Goal(type=GoalType.race, description="x", target_race_date=race)
    assert _compute_weeks(goal) == 30


# ────────────────────────────────────────────────────────────────────
# workout_date: cada workout cae en el lunes correcto de su semana
# ────────────────────────────────────────────────────────────────────

def _workout_date(monday_this_week: date, week_idx: int, dow: int) -> date:
    """Replica la fórmula de generate_plan_stream para ubicar un workout."""
    return monday_this_week + timedelta(weeks=week_idx - 1, days=dow)


def test_workout_date_semana1_lunes_cae_en_lunes():
    today = date(2026, 1, 7)  # miércoles
    monday_this_week = today - timedelta(days=today.weekday())
    assert monday_this_week == date(2026, 1, 5)  # lunes
    d = _workout_date(monday_this_week, week_idx=1, dow=0)
    assert d == date(2026, 1, 5)
    assert d.weekday() == 0  # lunes


def test_workout_date_semana1_domingo():
    monday = date(2026, 1, 5)
    d = _workout_date(monday, week_idx=1, dow=6)  # domingo
    assert d == date(2026, 1, 11)
    assert d.weekday() == 6


def test_workout_date_semana3_lunes():
    monday = date(2026, 1, 5)
    d = _workout_date(monday, week_idx=3, dow=0)
    # semana 3 = +2 semanas
    assert d == date(2026, 1, 19)
    assert d.weekday() == 0


def test_workout_date_inicio_de_cada_semana_siempre_es_lunes():
    monday = date(2026, 1, 5)
    for week_idx in range(1, 13):
        d = _workout_date(monday, week_idx=week_idx, dow=0)
        assert d.weekday() == 0, f"semana {week_idx} no empieza en lunes"


# ────────────────────────────────────────────────────────────────────
# _parse_response
# ────────────────────────────────────────────────────────────────────

def test_parse_response_running_basico():
    text = (
        "Aquí tienes tu plan:\n"
        "```json\n"
        '{"plan_name": "Plan 10k", "weeks": 1, "weekly_plan": '
        '[{"week": 1, "workouts": [{"day_of_week": 0, "type": "easy_run", '
        '"distance_km": 8.0, "duration_min": 50, "hr_zone": "Z2", '
        '"instructions": "Trote suave"}]}]}\n'
        "```\n"
        "Enfoque: base aeróbica."
    )
    data, summary = _parse_response(text)
    assert data is not None
    assert data["plan_name"] == "Plan 10k"
    assert data["weekly_plan"][0]["workouts"][0]["type"] == "easy_run"
    assert summary == "Enfoque: base aeróbica."


def test_parse_response_multideporte_swim_bike_brick():
    text = (
        "```json\n"
        "{\n"
        '  "plan_name": "Plan Olímpico",\n'
        '  "weeks": 1,\n'
        '  "discipline_split": {"swim": "2x", "bike": "2x", "run": "3x"},\n'
        '  "weekly_plan": [\n'
        "    {\n"
        '      "week": 1,\n'
        '      "workouts": [\n'
        '        {"day_of_week": 0, "discipline": "swim", "type": "swim_technique", "distance_km": 1.5, "duration_min": 45, "hr_zone": "Z2", "instructions": "Drills"},\n'
        '        {"day_of_week": 2, "discipline": "bike", "type": "bike", "distance_km": 40.0, "duration_min": 90, "hr_zone": "Z3", "instructions": "Rodaje"},\n'
        '        {"day_of_week": 5, "discipline": "brick", "type": "brick", "distance_km": 30.0, "duration_min": 100, "hr_zone": "Z3", "instructions": "Bici 25k + carrera 5k"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
        "Resumen multideporte."
    )
    data, summary = _parse_response(text)
    assert data is not None
    assert data["discipline_split"] == {"swim": "2x", "bike": "2x", "run": "3x"}
    workouts = data["weekly_plan"][0]["workouts"]
    disciplines = {w["discipline"] for w in workouts}
    types = {w["type"] for w in workouts}
    assert disciplines == {"swim", "bike", "brick"}
    assert {"swim_technique", "bike", "brick"} <= types
    assert summary == "Resumen multideporte."


def test_parse_response_sin_bloque_json_devuelve_none():
    data, summary = _parse_response("No hay JSON aquí, solo texto.")
    assert data is None
    assert summary == "No hay JSON aquí, solo texto."


def test_parse_response_json_invalido_devuelve_none():
    text = "```json\n{invalid json, no quotes}\n```"
    data, summary = _parse_response(text)
    assert data is None
    assert summary == text


# ────────────────────────────────────────────────────────────────────
# Helper: congelar `date.today()` sin romper date(...) ni la aritmética
# ────────────────────────────────────────────────────────────────────



# ── Plan combinado (varias carreras encadenadas) ────────────────────────────

def test_combined_weeks_hasta_la_ultima_carrera(monkeypatch):
    from app.services.plan_generator import _compute_weeks_combined
    fake_today = date(2026, 11, 16)  # lunes
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: fake_today)
    g1 = Goal(type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    g2 = Goal(type=GoalType.race, description="Media", target_race_date=date(2027, 4, 4))
    # Hasta el 4 de abril: lunes 16 nov -> lunes 29 mar = 19 semanas + la de carrera = 20
    assert _compute_weeks_combined([g2, g1]) == 20


def test_goal_for_date_asigna_por_bloques():
    from app.services.plan_generator import _goal_for_date, _races_in_order
    g1 = Goal(id=1, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    g2 = Goal(id=2, type=GoalType.race, description="Media", target_race_date=date(2027, 4, 4))
    races = _races_in_order([g2, g1])
    assert [g.id for g in races] == [1, 2]
    assert _goal_for_date(races, date(2026, 12, 1)) == 1   # bloque Hyrox
    assert _goal_for_date(races, date(2027, 2, 7)) == 1    # el día de la carrera aún es su bloque
    assert _goal_for_date(races, date(2027, 2, 8)) == 2    # transición -> media
    assert _goal_for_date(races, date(2027, 5, 1)) == 2    # tras la última, a la última


def test_purge_combinado_limpia_ambos_objetivos(db, user):
    from datetime import date as _d
    from app.models.workout import Workout, WorkoutType, WorkoutStatus
    from app.services.plan_generator import _purge_planned_before_generate
    g1 = Goal(user_id=user.id, type=GoalType.hyrox, description="H", target_race_date=_d(2027, 2, 7), is_active=True)
    g2 = Goal(user_id=user.id, type=GoalType.race, description="M", target_race_date=_d(2027, 4, 4), is_active=True)
    db.add_all([g1, g2]); db.commit()
    for g in (g1, g2):
        db.add(Workout(user_id=user.id, goal_id=g.id, date=_d(2026, 12, 1), type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.add(Workout(user_id=user.id, goal_id=g1.id, date=_d(2026, 11, 1), type=WorkoutType.easy_run, status=WorkoutStatus.completed))
    db.commit()
    n = _purge_planned_before_generate(user, g1, db, extra_goals=[g2])
    assert n == 2
    restantes = db.query(Workout).filter(Workout.user_id == user.id).all()
    assert len(restantes) == 1 and restantes[0].status == WorkoutStatus.completed
