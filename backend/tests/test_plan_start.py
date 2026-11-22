"""El plan arranca DESDE HOY: nada planificado en el pasado.

Síntoma: generado un domingo, la "Semana 1" empezaba el lunes ya pasado y traía
seis días de entrenos imposibles de hacer. Entre semana se descarta lo que ya
pasó; en sábado/domingo la semana 1 es la siguiente.
"""
from datetime import date

from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import plan_generator
from app.services.plan_generator import _combined_blocks, _compute_weeks, _plan_start

DOMINGO = date(2026, 11, 22)
SABADO = date(2026, 11, 21)
MIERCOLES = date(2026, 11, 18)


def test_entre_semana_se_arranca_el_lunes_de_esta_semana():
    for d in range(16, 21):  # lunes 16 .. viernes 20
        assert _plan_start(date(2026, 11, d)) == date(2026, 11, 16)


def test_en_fin_de_semana_la_semana_1_es_la_siguiente():
    assert _plan_start(SABADO) == date(2026, 11, 23)
    assert _plan_start(DOMINGO) == date(2026, 11, 23)
    assert _plan_start(DOMINGO, date(2027, 2, 7)) == date(2026, 11, 23)


def test_si_la_carrera_es_esta_misma_semana_no_se_salta_a_la_siguiente():
    assert _plan_start(SABADO, date(2026, 11, 22)) == date(2026, 11, 16)   # carrera el domingo


def test_semanas_hasta_la_carrera_desde_el_domingo(monkeypatch):
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: DOMINGO)
    g = Goal(type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    assert _compute_weeks(g) == 11          # lunes 23 nov .. semana del 1 feb (antes salían 12)


def test_el_combinado_desde_el_domingo_empieza_el_lunes_siguiente():
    g1 = Goal(id=1, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7))
    g2 = Goal(id=2, type=GoalType.race, description="Media", target_race_date=date(2027, 4, 4))
    b = _combined_blocks([g1, g2], DOMINGO)
    assert b[0]["start_monday"] == date(2026, 11, 23) and b[0]["weeks"] == 11
    assert b[1]["start_monday"] == date(2027, 2, 8) and b[1]["weeks"] == 8 and b[1]["offset"] == 11


def test_no_se_guardan_entrenos_en_el_pasado(db, user):
    g = Goal(user_id=user.id, type=GoalType.fitness, description="Forma", is_active=True)
    db.add(g); db.commit()
    data = {"weekly_plan": [{"week": 1, "workouts": [
        {"day_of_week": d, "type": "easy_run", "distance_km": 5} for d in range(7)]}]}
    n = plan_generator._insert_plan_workouts(db, user, data, date(2026, 11, 16), g.id, not_before=MIERCOLES)
    db.commit()
    fechas = sorted(str(w.date) for w in db.query(Workout).all())
    assert n == 5
    assert fechas[0] == "2026-11-18" and fechas[-1] == "2026-11-22"      # miércoles .. domingo


def test_generar_un_plan_individual_un_miercoles_descarta_lunes_y_martes(db, user, monkeypatch):
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: MIERCOLES)
    g = Goal(user_id=user.id, type=GoalType.fitness, description="Forma", is_active=True)
    db.add(g); db.commit()
    semana = [{"day_of_week": d, "type": "easy_run", "distance_km": 5} for d in range(7)]
    import json

    class _S:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def text_stream(self):
            yield "```json\n" + json.dumps({"plan_name": "p", "weeks": 8, "weekly_plan": [
                {"week": w, "workouts": semana} for w in range(1, 9)]}) + "\n```"
        def get_final_message(self):
            class _M: stop_reason = "end_turn"
            return _M()

    class _C:
        class messages:
            @staticmethod
            def stream(**kw):
                _C.last = kw
                return _S()

    monkeypatch.setattr(plan_generator.ai_client, "get_client", lambda: _C())
    list(plan_generator.generate_plan_stream(user, g, db))
    primero = db.query(Workout).order_by(Workout.date).first()
    assert str(primero.date) == "2026-11-18"                              # hoy, no el lunes
    # la IA sabe qué día es y desde cuándo planificar
    msg = _C.last["messages"][0]["content"]
    assert "miércoles" in msg and "2026-11-16" in msg
