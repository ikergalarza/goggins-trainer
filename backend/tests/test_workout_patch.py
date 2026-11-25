"""Regresión: PATCH /api/plans/workout/{id} debe persistir cambios (status, date, type)."""
from datetime import date
from app.api.routes.plans import update_workout, WorkoutUpdate
from app.models.workout import Workout, WorkoutType, WorkoutStatus


def _mk(db, user):
    w = Workout(user_id=user.id, date=date(2026, 6, 1), type=WorkoutType.easy_run,
                status=WorkoutStatus.planned)
    db.add(w); db.commit(); db.refresh(w)
    return w


def test_patch_status_persiste(db, user):
    w = _mk(db, user)
    out = update_workout(w.id, WorkoutUpdate(status="completed"), current=user, db=db)
    assert out["status"] == "completed"
    db.expire_all()
    assert db.query(Workout).get(w.id).status == WorkoutStatus.completed


def test_patch_date_persiste_y_recalcula_dow(db, user):
    w = _mk(db, user)
    out = update_workout(w.id, WorkoutUpdate(date=date(2026, 6, 3)), current=user, db=db)  # miércoles
    assert out["date"] == "2026-06-03"
    db.expire_all()
    stored = db.query(Workout).get(w.id)
    assert stored.date == date(2026, 6, 3)
    assert stored.day_of_week == 2


def test_patch_type_mobility(db, user):
    w = _mk(db, user)
    out = update_workout(w.id, WorkoutUpdate(type="mobility"), current=user, db=db)
    assert out["type"] == "mobility"


def _lunes_que_viene():
    """Próximo lunes (hora española): las sesiones recurrentes no se planifican en el pasado."""
    from datetime import timedelta
    from app.services.clock import today_madrid
    t = today_madrid()
    return t + timedelta(days=7 - t.weekday())


def _rango(dias: int):
    from datetime import timedelta
    lunes = _lunes_que_viene()
    return lunes.isoformat(), (lunes + timedelta(days=dias - 1)).isoformat()


def test_add_recurring_mobility_todos_los_dias(db, user):
    from app.services.agent_tools import _tool_add_recurring_workout
    out = _tool_add_recurring_workout(
        {"type": "mobility", "start_date": _rango(7)[0], "end_date": _rango(7)[1],
         "duration_min": 15, "instructions": "Movilidad articular 15'"},
        user, db,
    )
    assert out["ok"] is True
    assert out["created"] == 7  # 7 días seguidos
    assert out["mutation"] == "add_recurring_workout"
    rows = db.query(Workout).filter(Workout.type == WorkoutType.mobility).all()
    assert len(rows) == 7
    assert all(r.modified_by == "user" for r in rows)


def test_add_recurring_solo_dias_concretos_y_sin_duplicar(db, user):
    from app.services.agent_tools import _tool_add_recurring_workout
    # Lunes(0) y jueves(3) de una semana -> 2 sesiones
    out = _tool_add_recurring_workout(
        {"type": "strength_upper", "start_date": _rango(7)[0], "end_date": _rango(7)[1],
         "days_of_week": [0, 3]},
        user, db,
    )
    assert out["created"] == 2
    # Repetir no duplica
    out2 = _tool_add_recurring_workout(
        {"type": "strength_upper", "start_date": _rango(7)[0], "end_date": _rango(7)[1],
         "days_of_week": [0, 3]},
        user, db,
    )
    assert out2["created"] == 0


def test_recurring_se_asocia_al_objetivo_activo(db, user):
    """Si no se pasa goal_id, los workouts deben asociarse al objetivo activo
    para que aparezcan en la vista de Plan (regresión: movilidad invisible)."""
    from app.models.goal import Goal, GoalType
    from app.services.agent_tools import _tool_add_recurring_workout
    g = Goal(user_id=user.id, type=GoalType.race, description="Tri", sport="triathlon", is_active=True)
    db.add(g); db.commit(); db.refresh(g)

    out = _tool_add_recurring_workout(
        {"type": "mobility", "start_date": _rango(3)[0], "end_date": _rango(3)[1]},
        user, db,
    )
    assert out["created"] == 3
    rows = db.query(Workout).filter(Workout.type == WorkoutType.mobility).all()
    assert all(r.goal_id == g.id for r in rows)


def test_editar_el_wod_recalcula_la_duracion(db, user, make_workout):
    from app.api.routes.plans import update_workout, WorkoutUpdate
    w = make_workout(user, planned_duration_min=99)
    st = {"warmup": {"duration_min": 10}, "blocks": [{"format": "rounds", "rounds": 4, "rest_s": 60,
          "items": [{"exercise": "run", "distance_m": 400, "pace": "4:40/km"}]}]}
    out = update_workout(w.id, WorkoutUpdate(structure=st), current=user, db=db)
    assert out["structure"]["estimate"]["total_min"] == out["planned_duration_min"] != 99
    # si además se pide una duración concreta, se respeta
    out = update_workout(w.id, WorkoutUpdate(structure=st, planned_duration_min=70), current=user, db=db)
    assert out["planned_duration_min"] == 70
