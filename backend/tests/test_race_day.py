"""El día de la carrera tiene que SALIR en el plan (también en el combinado).

Antes dependía de que la IA se acordase de poner un workout ese día; en el plan
combinado no lo hacía. Ahora cada carrera con fecha lleva siempre su entrada
`race` en su día, y lo que la IA planificase DESPUÉS de la carrera se descarta.
"""
from datetime import date

from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import discipline, plan_generator
from app.services.plan_generator import _with_race_day

LUNES = date(2026, 11, 23)


def _hyrox(**kw):
    base = dict(id=1, type=GoalType.hyrox, description="Hyrox Bilbao", hyrox_division="dobles mixto",
                target_race_date=date(2027, 2, 7))  # domingo
    base.update(kw)
    return Goal(**base)


def _plan(*semanas):
    """_plan({1: [(dow, type), ...]}, ...) → data con weekly_plan."""
    return {"weekly_plan": [
        {"week": wk, "focus": "x", "workouts": [
            {"day_of_week": d, "type": t, "instructions": f"{t} s{wk}"} for d, t in ws]}
        for wk, ws in semanas
    ]}


def test_race_es_un_tipo_de_workout_valido():
    assert WorkoutType("race") is WorkoutType.race


def test_el_dia_de_carrera_se_empareja_con_cualquier_actividad_de_ese_dia():
    for strava in ("Run", "Workout", "WeightTraining", "Ride", "Swim", None):
        assert discipline.activity_matches_workout(strava, "race"), strava


def test_se_anade_el_dia_de_carrera_si_la_ia_no_lo_puso():
    g = _hyrox(target_time_seconds=5400)
    out = _with_race_day(_plan((1, [(1, "easy_run")])), g, LUNES)
    semana_carrera = (date(2027, 2, 7) - LUNES).days // 7 + 1   # 11
    wb = next(w for w in out["weekly_plan"] if w["week"] == semana_carrera)
    race = [w for w in wb["workouts"] if w["type"] == "race"]
    assert len(race) == 1
    assert race[0]["day_of_week"] == 6                      # domingo
    assert race[0]["duration_min"] == 90                    # tiempo objetivo 1:30
    assert "Hyrox Bilbao" in race[0]["instructions"]
    # las semanas que sí había se conservan
    assert any(w["week"] == 1 for w in out["weekly_plan"])


def test_distancia_de_la_carrera_a_pie():
    media = Goal(id=2, type=GoalType.race, description="Media SS", target_race_distance_km=21.1,
                 target_race_date=date(2026, 12, 6))  # domingo, 2 semanas después
    out = _with_race_day(_plan(), media, LUNES)
    race = [w for wb in out["weekly_plan"] for w in wb["workouts"] if w["type"] == "race"][0]
    assert race["distance_km"] == 21.1


def test_lo_que_la_ia_puso_ese_dia_pasa_a_ser_la_carrera_y_conserva_su_estrategia():
    g = _hyrox()
    data = _plan((11, [(5, "easy_run"), (6, "rest")]))
    data["weekly_plan"][0]["workouts"][1]["instructions"] = "Sal controlado el primer km y no te pases en el sled."
    out = _with_race_day(data, g, LUNES)
    wb = next(w for w in out["weekly_plan"] if w["week"] == 11)
    domingo = [w for w in wb["workouts"] if w["day_of_week"] == 6]
    assert len(domingo) == 1 and domingo[0]["type"] == "race"
    assert "Sal controlado el primer km" in domingo[0]["instructions"]
    # el sábado de taper se mantiene
    assert any(w["day_of_week"] == 5 and w["type"] == "easy_run" for w in wb["workouts"])


def test_se_descarta_lo_planificado_despues_de_la_carrera():
    g = _hyrox(target_race_date=date(2027, 2, 4))           # jueves de la semana 11
    data = _plan((11, [(2, "tempo"), (3, "rest"), (4, "easy_run"), (5, "long_run")]),
                 (12, [(0, "easy_run")]))
    out = _with_race_day(data, g, LUNES)
    assert all(w["week"] <= 11 for w in out["weekly_plan"])
    wb = next(w for w in out["weekly_plan"] if w["week"] == 11)
    dows = sorted(w["day_of_week"] for w in wb["workouts"])
    assert dows == [2, 3]                                   # miércoles + carrera el jueves
    assert [w for w in wb["workouts"] if w["day_of_week"] == 3][0]["type"] == "race"


def test_sin_fecha_o_carrera_ya_pasada_no_se_toca_nada():
    sin_fecha = Goal(id=3, type=GoalType.fitness, description="Forma")
    data = _plan((1, [(0, "easy_run")]))
    assert _with_race_day(data, sin_fecha, LUNES) is data
    pasada = _hyrox(target_race_date=date(2026, 11, 1))
    assert _with_race_day(data, pasada, LUNES) is data


def test_el_plan_generado_guarda_la_carrera_en_su_dia_y_con_su_objetivo(db, user):
    hyrox = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao",
                 target_race_date=date(2026, 12, 6), is_active=True)  # domingo, semana 2
    db.add(hyrox); db.commit()
    data = _plan((1, [(1, "easy_run")]), (2, [(2, "tempo")]))
    n = plan_generator._insert_plan_workouts(db, user, data, LUNES, hyrox.id, goal=hyrox)
    db.commit()
    carrera = db.query(Workout).filter(Workout.type == WorkoutType.race).all()
    assert n == 3
    assert [(str(w.date), w.goal_id, w.week_index, w.status) for w in carrera] == [
        ("2026-12-06", hyrox.id, 2, WorkoutStatus.planned)]


# --- planes YA generados: se les añade el día de carrera que les falta ---------

HOY = date(2026, 11, 22)


def _plan_combinado_sin_carreras(db, user, monkeypatch):
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: HOY)
    hyrox = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao",
                 target_race_date=date(2027, 2, 7), is_active=True)
    media = Goal(user_id=user.id, type=GoalType.race, description="Media SS", target_race_distance_km=21.1,
                 target_race_date=date(2027, 4, 4), is_active=True)
    db.add_all([hyrox, media]); db.commit()
    for g, dia in ((hyrox, date(2026, 11, 24)), (media, date(2027, 3, 2))):
        db.add(Workout(user_id=user.id, goal_id=g.id, date=dia, type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.commit()
    return hyrox, media


def test_el_plan_ya_generado_recibe_sus_dias_de_carrera(db, user, monkeypatch):
    hyrox, media = _plan_combinado_sin_carreras(db, user, monkeypatch)
    assert plan_generator.backfill_race_days(db) == 2
    carreras = db.query(Workout).filter(Workout.type == WorkoutType.race).order_by(Workout.date).all()
    assert [(str(w.date), w.goal_id, w.planned_distance_km) for w in carreras] == [
        ("2027-02-07", hyrox.id, None), ("2027-04-04", media.id, 21.1)]
    assert all(w.instructions and w.status == WorkoutStatus.planned for w in carreras)


def test_es_idempotente(db, user, monkeypatch):
    _plan_combinado_sin_carreras(db, user, monkeypatch)
    plan_generator.backfill_race_days(db)
    assert plan_generator.backfill_race_days(db) == 0
    assert db.query(Workout).filter(Workout.type == WorkoutType.race).count() == 2


def test_lo_que_la_ia_puso_el_dia_de_la_carrera_pasa_a_ser_la_carrera(db, user, monkeypatch):
    hyrox, _ = _plan_combinado_sin_carreras(db, user, monkeypatch)
    db.add(Workout(user_id=user.id, goal_id=hyrox.id, date=date(2027, 2, 7), type=WorkoutType.rest,
                   status=WorkoutStatus.planned, instructions="Día de carrera: sal controlado en el sled."))
    db.commit()
    plan_generator.backfill_race_days(db)
    ese_dia = db.query(Workout).filter(Workout.goal_id == hyrox.id, Workout.date == date(2027, 2, 7)).all()
    assert len(ese_dia) == 1 and ese_dia[0].type == WorkoutType.race
    assert "sal controlado en el sled" in ese_dia[0].instructions      # conserva su estrategia


def test_no_convierte_un_entreno_normal_en_la_carrera_conservando_sus_instrucciones(db, user, monkeypatch):
    hyrox, _ = _plan_combinado_sin_carreras(db, user, monkeypatch)
    db.add(Workout(user_id=user.id, goal_id=hyrox.id, date=date(2027, 2, 7), type=WorkoutType.easy_run,
                   status=WorkoutStatus.planned, instructions="Rodaje de 5 km muy suave."))
    db.commit()
    plan_generator.backfill_race_days(db)
    w = db.query(Workout).filter(Workout.goal_id == hyrox.id, Workout.date == date(2027, 2, 7)).one()
    assert w.type == WorkoutType.race and "Rodaje" not in w.instructions


def test_ignora_carreras_pasadas_y_objetivos_que_no_estan_en_el_plan(db, user, monkeypatch):
    monkeypatch.setattr(plan_generator, "today_madrid", lambda: HOY)
    pasada = Goal(user_id=user.id, type=GoalType.race, description="Vieja", target_race_date=date(2026, 10, 1), is_active=True)
    sin_plan = Goal(user_id=user.id, type=GoalType.race, description="Otra", target_race_date=date(2027, 5, 1), is_active=True)
    en_plan = Goal(user_id=user.id, type=GoalType.race, description="Esta", target_race_date=date(2027, 3, 1), is_active=True)
    db.add_all([pasada, sin_plan, en_plan]); db.commit()
    for g in (pasada, en_plan):
        db.add(Workout(user_id=user.id, goal_id=g.id, date=date(2026, 11, 25), type=WorkoutType.easy_run, status=WorkoutStatus.planned))
    db.commit()
    assert plan_generator.backfill_race_days(db) == 1
    assert [w.goal_id for w in db.query(Workout).filter(Workout.type == WorkoutType.race)] == [en_plan.id]


def test_el_arranque_añade_los_dias_de_carrera_y_no_rompe_si_falla(db, user, monkeypatch):
    from app.db import seed
    _plan_combinado_sin_carreras(db, user, monkeypatch)
    monkeypatch.setattr(seed, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    seed.backfill_race_days()
    assert db.query(Workout).filter(Workout.type == WorkoutType.race).count() == 2
    # si el cálculo explota, el arranque sigue (solo avisa)
    monkeypatch.setattr(plan_generator, "backfill_race_days", lambda _db: (_ for _ in ()).throw(RuntimeError("boom")))
    seed.backfill_race_days()
