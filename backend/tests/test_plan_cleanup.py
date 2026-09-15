"""Semanas zombis: filtro estricto por objetivo, borrado en cascada y purga al generar."""
from datetime import date

from app.api.routes.goals import delete_goal
from app.api.routes.plans import list_plan_workouts
from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutType, WorkoutStatus


def _goal(db, user, desc="Hyrox", active=True):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description=desc, is_active=active)
    db.add(g); db.commit(); db.refresh(g)
    return g


def _w(db, user, goal_id, day, status=WorkoutStatus.planned):
    w = Workout(user_id=user.id, goal_id=goal_id, date=day, type=WorkoutType.easy_run, status=status)
    db.add(w); db.commit(); db.refresh(w)
    return w


def test_filtro_por_objetivo_no_cuela_huerfanos(db, user):
    g = _goal(db, user)
    _w(db, user, g.id, date(2026, 9, 16))
    _w(db, user, None, date(2026, 7, 1))   # huérfano de un plan viejo
    rows = list_plan_workouts(user.id, goal_id=g.id, current=user, db=db)
    assert len(rows) == 1 and rows[0]["goal_id"] == g.id
    # Sin filtro se sigue viendo todo (vista global).
    assert len(list_plan_workouts(user.id, goal_id=None, current=user, db=db)) == 2


def test_borrar_objetivo_se_lleva_sus_workouts(db, user):
    g = _goal(db, user)
    _w(db, user, g.id, date(2026, 9, 16))
    _w(db, user, g.id, date(2026, 9, 17), status=WorkoutStatus.completed)
    out = delete_goal(user.id, g.id, current=user, db=db)
    assert out["workouts_deleted"] == 2
    assert db.query(Workout).filter(Workout.user_id == user.id).count() == 0


def test_generar_purga_planificados_del_goal_y_huerfanos(db, user):
    from app.services.plan_generator import _purge_planned_before_generate
    g = _goal(db, user)
    keep_done = _w(db, user, g.id, date(2026, 9, 10), status=WorkoutStatus.completed)
    _w(db, user, g.id, date(2026, 9, 20))          # planificado del goal -> fuera
    _w(db, user, None, date(2026, 8, 1))           # huérfano planificado -> fuera
    other = _goal(db, user, "10k")
    keep_other = _w(db, user, other.id, date(2026, 9, 21))  # de OTRO goal -> se queda

    n = _purge_planned_before_generate(user, g, db)

    assert n == 2
    ids = {w.id for w in db.query(Workout).filter(Workout.user_id == user.id).all()}
    assert ids == {keep_done.id, keep_other.id}
