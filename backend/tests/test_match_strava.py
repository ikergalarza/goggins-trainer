"""Tests de match_strava_to_workouts.

Verifica que una actividad de Strava se enlaza con un workout planificado del
MISMO día, copiando los datos reales y marcándolo como completado.
"""
from datetime import date, datetime, timezone

import pytest

from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.services.plan_generator import match_strava_to_workouts


def test_enlaza_actividad_y_workout_por_fecha(db, user, make_workout, make_strava_activity):
    w = make_workout(user, date=date(2026, 1, 5), status=WorkoutStatus.planned)
    act = make_strava_activity(
        user,
        start_date=datetime(2026, 1, 5, 7, 30, tzinfo=timezone.utc),
        distance_m=8200.0,
        moving_time_s=2900,
        average_heartrate=150.0,
        max_heartrate=175.0,
    )

    matched = match_strava_to_workouts(user, db)
    assert matched == 1

    db.refresh(w)
    assert w.strava_activity_id == str(act.strava_id)
    assert w.status == WorkoutStatus.completed
    assert w.actual_distance_km == 8.2
    assert w.actual_duration_min == 48
    assert w.actual_avg_heart_rate == 150
    assert w.actual_max_heart_rate == 175


def test_no_enlaza_si_no_hay_actividad_ese_dia(db, user, make_workout, make_strava_activity):
    w = make_workout(user, date=date(2026, 1, 5), status=WorkoutStatus.planned)
    make_strava_activity(user, start_date=datetime(2026, 1, 6, 7, 0, tzinfo=timezone.utc))
    matched = match_strava_to_workouts(user, db)
    assert matched == 0
    db.refresh(w)
    assert w.strava_activity_id is None
    assert w.status == WorkoutStatus.planned


def test_elige_la_actividad_mas_larga_del_dia(db, user, make_workout, make_strava_activity):
    make_workout(user, date=date(2026, 1, 5), status=WorkoutStatus.planned)
    make_strava_activity(
        user, start_date=datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc), distance_m=3000.0
    )
    larga = make_strava_activity(
        user, start_date=datetime(2026, 1, 5, 18, 0, tzinfo=timezone.utc), distance_m=12000.0
    )
    matched = match_strava_to_workouts(user, db)
    assert matched == 1
    w = db.query(Workout).filter(Workout.user_id == user.id).first()
    assert w.strava_activity_id == str(larga.strava_id)
    assert w.actual_distance_km == 12.0


def test_no_reenlaza_workouts_ya_enlazados(db, user, make_workout, make_strava_activity):
    make_workout(
        user,
        date=date(2026, 1, 5),
        status=WorkoutStatus.planned,
        strava_activity_id="ya-enlazado",
    )
    make_strava_activity(user, start_date=datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc))
    matched = match_strava_to_workouts(user, db)
    assert matched == 0


def test_no_enlaza_actividad_de_otro_usuario(db, user, other_user, make_workout, make_strava_activity):
    w = make_workout(user, date=date(2026, 1, 5), status=WorkoutStatus.planned)
    make_strava_activity(other_user, start_date=datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc))
    matched = match_strava_to_workouts(user, db)
    assert matched == 0
    db.refresh(w)
    assert w.strava_activity_id is None
