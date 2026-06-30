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
    out = update_workout(w.id, WorkoutUpdate(status="completed"), db)
    assert out["status"] == "completed"
    db.expire_all()
    assert db.query(Workout).get(w.id).status == WorkoutStatus.completed


def test_patch_date_persiste_y_recalcula_dow(db, user):
    w = _mk(db, user)
    out = update_workout(w.id, WorkoutUpdate(date=date(2026, 6, 3)), db)  # miércoles
    assert out["date"] == "2026-06-03"
    db.expire_all()
    stored = db.query(Workout).get(w.id)
    assert stored.date == date(2026, 6, 3)
    assert stored.day_of_week == 2


def test_patch_type_mobility(db, user):
    w = _mk(db, user)
    out = update_workout(w.id, WorkoutUpdate(type="mobility"), db)
    assert out["type"] == "mobility"


def test_add_recurring_mobility_todos_los_dias(db, user):
    from app.services.agent_tools import _tool_add_recurring_workout
    out = _tool_add_recurring_workout(
        {"type": "mobility", "start_date": "2026-06-01", "end_date": "2026-06-07",
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
        {"type": "strength_upper", "start_date": "2026-06-01", "end_date": "2026-06-07",
         "days_of_week": [0, 3]},
        user, db,
    )
    assert out["created"] == 2
    # Repetir no duplica
    out2 = _tool_add_recurring_workout(
        {"type": "strength_upper", "start_date": "2026-06-01", "end_date": "2026-06-07",
         "days_of_week": [0, 3]},
        user, db,
    )
    assert out2["created"] == 0
