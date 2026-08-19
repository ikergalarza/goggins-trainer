"""Emparejamiento Strava <-> workouts planificados, por disciplina.

Lo que tiene que cumplir:
- Una carrera de Strava NO se empareja con una sesión de movilidad/fuerza.
- Con dos workouts el mismo día (natación + carrera), cada actividad va al
  suyo; una misma actividad nunca se engancha a dos workouts.
- Si ese día no hay nada del mismo deporte, el workout se queda sin emparejar
  (mejor vacío que mal).
- Lo que se hace fuera del plan se puede listar (actividades no vinculadas).
"""
from datetime import date, datetime, timezone

from app.models.strava_activity import StravaActivity
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.services import plan_generator
from app.services.discipline import discipline_for_workout_type


def _activity(db, user, strava_id, type_, km, day=date(2026, 8, 18), hour=8):
    a = StravaActivity(
        user_id=user.id, strava_id=strava_id, name=f"{type_} {km}k", type=type_,
        distance_m=km * 1000, moving_time_s=int(km * 360),
        start_date=datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc),
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _workout(db, user, type_, day=date(2026, 8, 18)):
    w = Workout(user_id=user.id, date=day, type=type_, status=WorkoutStatus.planned)
    db.add(w); db.commit(); db.refresh(w)
    return w


# --- disciplina del workout planificado ------------------------------------

def test_disciplina_de_tipos_de_workout():
    assert discipline_for_workout_type("easy_run") == "run"
    assert discipline_for_workout_type("intervals") == "run"
    assert discipline_for_workout_type("swim") == "swim"
    assert discipline_for_workout_type("open_water") == "swim"
    assert discipline_for_workout_type("bike") == "bike"
    assert discipline_for_workout_type("strength_full") == "strength"
    assert discipline_for_workout_type("hyrox_sim") == "strength"
    assert discipline_for_workout_type("mobility") == "strength"
    assert discipline_for_workout_type("brick") == "brick"
    assert discipline_for_workout_type("rest") is None


# --- emparejamiento ----------------------------------------------------------

def test_carrera_no_se_empareja_con_movilidad(db, user):
    _activity(db, user, 1, "Run", 10)
    mob = _workout(db, user, WorkoutType.mobility)

    matched = plan_generator.match_strava_to_workouts(user, db)

    db.refresh(mob)
    assert matched == 0
    assert mob.strava_activity_id is None
    assert mob.status == WorkoutStatus.planned


def test_dos_workouts_mismo_dia_cada_uno_con_su_actividad(db, user):
    run = _activity(db, user, 1, "Run", 10, hour=7)
    swim = _activity(db, user, 2, "Swim", 1.5, hour=19)
    w_run = _workout(db, user, WorkoutType.easy_run)
    w_swim = _workout(db, user, WorkoutType.swim)

    matched = plan_generator.match_strava_to_workouts(user, db)

    db.refresh(w_run); db.refresh(w_swim)
    assert matched == 2
    assert w_run.strava_activity_id == str(run.strava_id)
    assert w_swim.strava_activity_id == str(swim.strava_id)
    assert w_run.actual_distance_km == 10.0
    assert w_swim.actual_distance_km == 1.5


def test_una_actividad_no_se_engancha_a_dos_workouts(db, user):
    _activity(db, user, 1, "Run", 10)
    w1 = _workout(db, user, WorkoutType.easy_run)
    w2 = _workout(db, user, WorkoutType.intervals)

    matched = plan_generator.match_strava_to_workouts(user, db)

    db.refresh(w1); db.refresh(w2)
    linked = [w for w in (w1, w2) if w.strava_activity_id]
    assert matched == 1
    assert len(linked) == 1


def test_brick_acepta_bici_o_carrera(db, user):
    _activity(db, user, 1, "Ride", 30)
    brick = _workout(db, user, WorkoutType.brick)

    plan_generator.match_strava_to_workouts(user, db)

    db.refresh(brick)
    assert brick.strava_activity_id == "1"


def test_ya_vinculada_no_se_reutiliza(db, user):
    a = _activity(db, user, 1, "Run", 10)
    w_prev = _workout(db, user, WorkoutType.easy_run, day=date(2026, 8, 17))
    w_prev.strava_activity_id = str(a.strava_id); w_prev.status = WorkoutStatus.completed
    db.commit()
    # Un workout de carrera el mismo día de la actividad, pero esta ya está usada.
    w_today = _workout(db, user, WorkoutType.easy_run)

    # La actividad es del 18, w_prev del 17: simulamos vínculo manual previo.
    plan_generator.match_strava_to_workouts(user, db)

    db.refresh(w_today)
    assert w_today.strava_activity_id is None


# --- actividades fuera del plan ---------------------------------------------

def test_unlinked_activities_lista_lo_no_emparejado(db, user):
    run = _activity(db, user, 1, "Run", 10, hour=7)
    _activity(db, user, 2, "Swim", 1.5, hour=19)  # sin workout -> fuera de plan
    w_run = _workout(db, user, WorkoutType.easy_run)

    plan_generator.match_strava_to_workouts(user, db)
    unlinked = plan_generator.unlinked_activities(user, db, since=date(2026, 8, 1))

    ids = {a.strava_id for a in unlinked}
    assert ids == {2}
    db.refresh(w_run)
    assert w_run.strava_activity_id == str(run.strava_id)


# --- endpoints: vincular / desvincular a mano -------------------------------

from app.api.routes.plans import link_workout, unlink_workout, LinkBody, unlinked as unlinked_route


def test_link_manual_de_otro_dia_y_unlink(db, user):
    a = _activity(db, user, 1, "Run", 12, day=date(2026, 8, 18))
    w = _workout(db, user, WorkoutType.long_run, day=date(2026, 8, 17))  # el día antes

    out = link_workout(w.id, LinkBody(strava_id=a.strava_id), current=user, db=db)
    assert out["status"] == "completed"
    assert out["strava_activity_id"] == "1"
    assert out["actual_distance_km"] == 12.0

    out2 = unlink_workout(w.id, current=user, db=db)
    assert out2["status"] == "planned"
    assert out2["strava_activity_id"] is None
    assert out2["actual_distance_km"] is None


def test_link_mueve_la_actividad_si_estaba_en_otro_workout(db, user):
    a = _activity(db, user, 1, "Run", 10)
    w1 = _workout(db, user, WorkoutType.easy_run)
    w2 = _workout(db, user, WorkoutType.tempo)
    link_workout(w1.id, LinkBody(strava_id=a.strava_id), current=user, db=db)

    link_workout(w2.id, LinkBody(strava_id=a.strava_id), current=user, db=db)

    db.expire_all()
    assert db.get(Workout, w1.id).strava_activity_id is None
    assert db.get(Workout, w1.id).status == WorkoutStatus.planned
    assert db.get(Workout, w2.id).strava_activity_id == "1"


def test_endpoint_unlinked(db, user):
    _activity(db, user, 1, "Swim", 2, day=date.today())
    rows = unlinked_route(user.id, days=7, current=user, db=db)
    assert [r["strava_id"] for r in rows] == [1]
    assert rows[0]["distance_km"] == 2.0
