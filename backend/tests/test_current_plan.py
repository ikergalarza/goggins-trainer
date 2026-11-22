"""UN solo plan en vigor: combinado o individual, a elegir al generarlo.

La vista del Plan enseñaba una pestaña por objetivo además del combinado, así
que un plan combinado aparecía "partido" en trozos que parecían planes propios.
Ahora el backend dice qué plan hay (kind + objetivos) y la vista lo enseña
entero; qué plan generar se elige al generar.
"""
import json
from datetime import date

import pytest
from fastapi import HTTPException

from app.api.routes.plans import current_plan
from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import plan_generator

HOY = date(2026, 11, 18)  # miércoles


def _goal(db, user, desc, race=None, active=True, type_=GoalType.race):
    g = Goal(user_id=user.id, type=type_, description=desc, target_race_date=race, is_active=active)
    db.add(g); db.commit(); db.refresh(g)
    return g


def _w(db, user, goal, day, status=WorkoutStatus.planned, type_=WorkoutType.easy_run):
    w = Workout(user_id=user.id, goal_id=goal.id if goal else None, date=day, type=type_, status=status)
    db.add(w); db.commit(); db.refresh(w)
    return w


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    from app.api.routes import plans
    monkeypatch.setattr(plans, "today_madrid", lambda: HOY)


def _current(db, user):
    return current_plan(user.id, current=user, db=db)


def test_sin_entrenos_no_hay_plan(db, user):
    out = _current(db, user)
    assert out == {"kind": "none", "goals": [], "workouts": []}


def test_un_solo_objetivo_es_plan_individual(db, user):
    a = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7))
    _w(db, user, a, date(2026, 11, 20))
    out = _current(db, user)
    assert out["kind"] == "single"
    assert [g["id"] for g in out["goals"]] == [a.id]
    assert len(out["workouts"]) == 1


def test_dos_objetivos_con_entrenos_planificados_es_plan_combinado_ordenado_por_fecha(db, user):
    media = _goal(db, user, "Media SS", date(2027, 4, 4))
    hyrox = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7))
    _w(db, user, hyrox, date(2026, 11, 20))
    _w(db, user, media, date(2027, 2, 20))
    out = _current(db, user)
    assert out["kind"] == "combined"
    assert [g["description"] for g in out["goals"]] == ["Hyrox Bilbao", "Media SS"]   # por fecha de carrera
    assert [w["goal_id"] for w in out["workouts"]] == [hyrox.id, media.id]


def test_no_cuela_historial_de_objetivos_que_ya_no_son_el_plan(db, user):
    vieja = _goal(db, user, "Prueba vieja", active=False)
    hyrox = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7))
    _w(db, user, vieja, date(2026, 5, 1), status=WorkoutStatus.completed)     # historia de otro plan
    _w(db, user, None, date(2026, 6, 1))                                      # huérfano
    _w(db, user, hyrox, date(2026, 11, 20))
    out = _current(db, user)
    assert out["kind"] == "single"
    assert [w["goal_id"] for w in out["workouts"]] == [hyrox.id]


def test_lo_ya_hecho_del_plan_en_vigor_se_ve(db, user):
    hyrox = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7))
    _w(db, user, hyrox, date(2026, 11, 16), status=WorkoutStatus.completed)
    _w(db, user, hyrox, date(2026, 11, 20))
    assert len(_current(db, user)["workouts"]) == 2


def test_sin_planificados_se_usa_el_plan_de_los_ultimos_dias(db, user):
    hyrox = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7))
    _w(db, user, hyrox, date(2026, 11, 16), status=WorkoutStatus.completed)   # todo hecho, nada pendiente
    out = _current(db, user)
    assert out["kind"] == "single" and len(out["workouts"]) == 1


def test_otro_usuario_no_puede_ver_el_plan(db, user, other_user):
    with pytest.raises(HTTPException) as e:
        current_plan(user.id, current=other_user, db=db)
    assert e.value.status_code == 403


# --- generar sustituye el plan entero, sea individual o combinado -------------

class _Stream:
    def __init__(self, text): self._t = text
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def text_stream(self):
        yield self._t
    def get_final_message(self):
        class _M: stop_reason = "end_turn"
        return _M()


def _fake_client(monkeypatch, workouts_por_semana):
    text = "```json\n" + json.dumps({"plan_name": "p", "weeks": 2, "weekly_plan": [
        {"week": 1, "workouts": workouts_por_semana}, {"week": 2, "workouts": workouts_por_semana}]}) + "\n```"

    class _C:
        class messages:
            @staticmethod
            def stream(**kw):
                return _Stream(text)

    monkeypatch.setattr(plan_generator.ai_client, "get_client", lambda: _C())


def test_generar_un_plan_individual_sustituye_tambien_lo_planificado_de_otros_objetivos(db, user, monkeypatch):
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: HOY)
    hyrox = _goal(db, user, "Hyrox Bilbao", date(2027, 2, 7), type_=GoalType.hyrox)
    media = _goal(db, user, "Media SS", date(2027, 4, 4))
    hecho = _w(db, user, media, date(2026, 11, 10), status=WorkoutStatus.completed)
    _w(db, user, media, date(2026, 12, 1))          # del combinado anterior: debe desaparecer
    _w(db, user, hyrox, date(2026, 12, 2))
    _w(db, user, None, date(2026, 12, 3))           # huérfano
    _fake_client(monkeypatch, [{"day_of_week": 4, "type": "easy_run", "distance_km": 5}])

    list(plan_generator.generate_plan_stream(user, media, db))

    planned = db.query(Workout).filter(Workout.status == WorkoutStatus.planned).all()
    assert planned and all(w.goal_id == media.id for w in planned)     # solo el plan nuevo
    assert db.query(Workout).get(hecho.id) is not None                  # la historia se conserva
