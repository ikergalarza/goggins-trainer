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



# ── Plan combinado (varias carreras encadenadas, UN bloque por carrera) ──────

def test_combined_blocks_reparte_semanas_por_carrera(monkeypatch):
    """16 nov → Hyrox 7 feb (12 sem) y después media 4 abr (8 sem, desde el
    lunes siguiente a la carrera 1). week_index global continuo."""
    from app.services.plan_generator import _combined_blocks
    g1 = Goal(id=1, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    g2 = Goal(id=2, type=GoalType.race, description="Media", target_race_date=date(2027, 4, 4))
    blocks = _combined_blocks([g2, g1], today=date(2026, 11, 16))
    assert [b["goal"].id for b in blocks] == [1, 2]
    assert blocks[0]["start_monday"] == date(2026, 11, 16)
    assert blocks[0]["weeks"] == 12
    assert blocks[0]["offset"] == 0
    assert blocks[1]["start_monday"] == date(2027, 2, 8)  # lunes tras la carrera 1
    assert blocks[1]["weeks"] == 8
    assert blocks[1]["offset"] == 12
    assert sum(b["weeks"] for b in blocks) == 20


def test_combined_blocks_ignora_carreras_pasadas():
    from app.services.plan_generator import _combined_blocks
    pasada = Goal(id=1, type=GoalType.race, description="Vieja", target_race_date=date(2026, 4, 4))
    futura = Goal(id=2, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    blocks = _combined_blocks([pasada, futura], today=date(2026, 11, 16))
    assert [b["goal"].id for b in blocks] == [2]


def test_purge_all_planned_limpia_todo_lo_planificado(db, user):
    """Regenerar el combinado EMPIEZA DE CERO: borra lo planificado de TODOS los
    objetivos (también viejos/inactivos) y los huérfanos; lo completado queda."""
    from datetime import date as _d
    from app.models.workout import Workout, WorkoutType, WorkoutStatus
    from app.services.plan_generator import _purge_all_planned
    g1 = Goal(user_id=user.id, type=GoalType.hyrox, description="H", target_race_date=_d(2027, 2, 7), is_active=True)
    viejo = Goal(user_id=user.id, type=GoalType.race, description="Prueba vieja", is_active=False)
    db.add_all([g1, viejo]); db.commit()
    db.add(Workout(user_id=user.id, goal_id=g1.id, date=_d(2026, 12, 1), type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.add(Workout(user_id=user.id, goal_id=viejo.id, date=_d(2026, 12, 2), type=WorkoutType.tempo, status=WorkoutStatus.planned))
    db.add(Workout(user_id=user.id, goal_id=None, date=_d(2026, 12, 3), type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.add(Workout(user_id=user.id, goal_id=g1.id, date=_d(2026, 11, 1), type=WorkoutType.easy_run, status=WorkoutStatus.completed))
    db.commit()
    n = _purge_all_planned(user, db)
    assert n == 3
    restantes = db.query(Workout).filter(Workout.user_id == user.id).all()
    assert len(restantes) == 1 and restantes[0].status == WorkoutStatus.completed


class _FakeAIStream:
    """Imita client.messages.stream(...) para un texto fijo."""
    def __init__(self, text):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        yield self._text

    def get_final_message(self):
        class _M:
            stop_reason = "end_turn"
        return _M()


def _plan_json(week_workouts: dict[int, list[dict]]) -> str:
    weekly = [
        {"week": wk, "focus": "x", "workouts": ws} for wk, ws in week_workouts.items()
    ]
    return "```json\n" + __import__("json").dumps({
        "plan_name": "p", "weeks": len(weekly), "phases": [], "weekly_plan": weekly,
    }) + "\n```"


def test_generate_combinado_un_bloque_por_carrera(db, user, monkeypatch):
    """El combinado hace UNA llamada IA por carrera: el bloque Hyrox con el
    prompt Hyrox (SkiErg...), el de carrera a pie sin él; fechas y week_index
    del bloque 2 continúan tras la carrera 1; purga total previa."""
    from datetime import date as _d
    from app.models.workout import Workout, WorkoutType, WorkoutStatus

    monkeypatch.setattr(plan_generator, "today_madrid", lambda: _d(2026, 11, 16))

    hyrox = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao",
                 hyrox_division="dobles mixto", target_race_date=_d(2027, 2, 7), is_active=True)
    media = Goal(user_id=user.id, type=GoalType.race, description="Media SS",
                 target_race_date=_d(2027, 4, 4), is_active=True)
    viejo = Goal(user_id=user.id, type=GoalType.race, description="Prueba vieja", is_active=False)
    db.add_all([hyrox, media, viejo]); db.commit()
    # Restos de la "prueba anterior": deben desaparecer al regenerar
    db.add(Workout(user_id=user.id, goal_id=viejo.id, date=_d(2026, 11, 18), type=WorkoutType.tempo, status=WorkoutStatus.planned))
    db.add(Workout(user_id=user.id, goal_id=hyrox.id, date=_d(2026, 11, 10), type=WorkoutType.hyrox_stations, status=WorkoutStatus.completed))
    db.commit()

    calls: list[dict] = []
    respuestas = [
        _plan_json({1: [{"type": "hyrox_stations", "day_of_week": 0, "duration_min": 60}],
                    2: [{"type": "easy_run", "day_of_week": 2, "distance_km": 8}]}),
        _plan_json({1: [{"type": "recovery", "day_of_week": 0, "duration_min": 30}],
                    2: [{"type": "long_run", "day_of_week": 6, "distance_km": 16}]}),
    ]

    class _FakeMessages:
        def stream(self, **kwargs):
            calls.append(kwargs)
            return _FakeAIStream(respuestas[len(calls) - 1])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(plan_generator.ai_client, "get_client", lambda: _FakeClient())

    events = list(plan_generator.generate_plan_stream(user, hyrox, db, extra_goals=[media]))
    done = next(e for e in events if e.get("phase") == "done")

    # Una llamada por carrera, cada una con SU prompt
    assert len(calls) == 2
    assert "SkiErg" in calls[0]["system"]
    assert "SkiErg" not in calls[1]["system"]
    assert "BLOQUE 1" in calls[0]["messages"][0]["content"]
    assert "BLOQUE 2" in calls[1]["messages"][0]["content"]
    # El bloque 2 arranca en transición tras la carrera 1
    assert "transici" in calls[1]["messages"][0]["content"].lower()

    ws = db.query(Workout).filter(Workout.user_id == user.id, Workout.status == WorkoutStatus.planned).order_by(Workout.date).all()
    assert [(w.type, str(w.date), w.week_index, w.goal_id) for w in ws] == [
        (WorkoutType.hyrox_stations, "2026-11-16", 1, hyrox.id),
        (WorkoutType.easy_run, "2026-11-25", 2, hyrox.id),
        (WorkoutType.race, "2027-02-07", 12, hyrox.id),   # día de la carrera 1 (siempre sale)
        (WorkoutType.recovery, "2027-02-08", 13, media.id),
        (WorkoutType.long_run, "2027-02-21", 14, media.id),
        (WorkoutType.race, "2027-04-04", 20, media.id),   # día de la carrera 2
    ]
    # La prueba vieja se purgó; lo completado se conserva
    assert db.query(Workout).filter(Workout.goal_id == viejo.id).count() == 0
    assert db.query(Workout).filter(Workout.status == WorkoutStatus.completed).count() == 1
    assert done["workouts_created"] == 6   # 4 de la IA + las 2 carreras
    assert done["weeks"] == 20


# ── control de calidad: las sesiones de estaciones flojas se completan ─────────

_POBRE = {"warmup": {"duration_min": 10}, "blocks": [{"title": "P", "format": "rounds", "rounds": 4, "items": [
    {"exercise": "run", "distance_m": 400}, {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152}]}]}


def _plan_hyrox(*sesiones):
    """sesiones: (semana, dia, tipo, structure)"""
    semanas = {}
    for w, d, t, st in sesiones:
        semanas.setdefault(w, []).append({"day_of_week": d, "type": t, "structure": st, "instructions": "x"})
    return {"weekly_plan": [{"week": w, "workouts": ws} for w, ws in semanas.items()]}


def test_una_sesion_de_estaciones_floja_se_completa_con_una_de_calidad(db, user):
    from datetime import date as _d
    from app.models.workout import Workout, WorkoutType
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", target_race_date=_d(2027, 2, 7), is_active=True)
    db.add(g); db.commit()
    data = _plan_hyrox((1, 3, "hyrox_stations", _POBRE),                 # floja
                       (1, 5, "hyrox_sim", _POBRE),                      # los simulacros no se tocan
                       (2, 1, "easy_run", None))
    plan_generator._insert_plan_workouts(db, user, data, _d(2026, 11, 30), g.id, goal=g)
    db.commit()
    est = db.query(Workout).filter(Workout.type == WorkoutType.hyrox_stations).one()
    assert len({i["exercise"] for b in est.structure["blocks"] for i in b["items"] if i["exercise"] != "run"}) >= 3
    assert est.planned_duration_min >= 35 and est.planned_distance_km > 0
    assert est.instructions.startswith("Activación")                       # va 2 días antes del simulacro
    sim = db.query(Workout).filter(Workout.type == WorkoutType.hyrox_sim).one()
    assert sim.structure["blocks"][0]["items"][1]["exercise"] == "sled_push" and len(sim.structure["blocks"]) == 1


def test_la_semana_de_carrera_y_las_sesiones_completas_se_respetan(db, user):
    from datetime import date as _d
    from app.models.workout import Workout
    from app.services import hyrox_wods
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", target_race_date=_d(2027, 2, 7), is_active=True)
    db.add(g); db.commit()
    rica = hyrox_wods.build_session("open_men", variant=1, weeks_to_race=5)["structure"]
    data = _plan_hyrox((1, 3, "hyrox_stations", rica), (10, 3, "hyrox_stations", _POBRE))   # semana 10 = carrera
    plan_generator._insert_plan_workouts(db, user, data, _d(2026, 11, 30), g.id, goal=g)
    db.commit()
    filas = db.query(Workout).filter(Workout.type == "hyrox_stations").order_by(Workout.date).all()
    assert filas[0].structure["blocks"][0]["title"] == rica["blocks"][0]["title"] and filas[0].instructions == "x"
    assert filas[1].instructions == "x" and len(filas[1].structure["blocks"]) == 1
