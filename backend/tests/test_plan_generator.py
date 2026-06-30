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
    monkeypatch.setattr(plan_generator, "date", _FrozenDate(fake_today))
    goal = Goal(type=GoalType.race, description="x", target_race_date=date(2026, 1, 9))
    assert _compute_weeks(goal) == 1


def test_compute_weeks_carrera_semana_siguiente_es_2(monkeypatch):
    fake_today = date(2026, 1, 7)  # miércoles, semana del lunes 5 ene
    monkeypatch.setattr(plan_generator, "date", _FrozenDate(fake_today))
    # Carrera el lunes 12 ene (semana siguiente) → 2 semanas.
    goal = Goal(type=GoalType.race, description="x", target_race_date=date(2026, 1, 12))
    assert _compute_weeks(goal) == 2


def test_compute_weeks_doce_semanas(monkeypatch):
    fake_today = date(2026, 1, 5)  # lunes
    monkeypatch.setattr(plan_generator, "date", _FrozenDate(fake_today))
    # 11 semanas después + la propia semana de carrera = 12.
    race = date(2026, 1, 5) + timedelta(weeks=11)
    goal = Goal(type=GoalType.race, description="x", target_race_date=race)
    assert _compute_weeks(goal) == 12


def test_compute_weeks_se_capa_en_30(monkeypatch):
    fake_today = date(2026, 1, 5)
    monkeypatch.setattr(plan_generator, "date", _FrozenDate(fake_today))
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

def _FrozenDate(frozen: date):
    """Devuelve una subclase de `date` cuyo `today()` está fijado.

    Se usa con `monkeypatch.setattr(plan_generator, "date", _FrozenDate(x))`.
    Al ser subclase de `date`, el constructor, `weekday()` y la aritmética con
    `timedelta` se comportan exactamente igual; solo `today()` cambia.
    """

    class _Frozen(date):
        @classmethod
        def today(cls):
            return date(frozen.year, frozen.month, frozen.day)

    return _Frozen
