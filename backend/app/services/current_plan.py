"""Qué plan está en vigor: UNO solo, combinado o individual.

Generar un plan (de la clase que sea) sustituye todo lo planificado, así que el
plan en vigor se deduce de los datos: los objetivos de los entrenos que quedan
por hacer. Dos o más objetivos = plan combinado; uno = plan individual. Lo
completado de planes anteriores (otros objetivos) no forma parte de él.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.workout import Workout, WorkoutStatus

# Si no queda nada por hacer (plan terminado o todo completado), el plan en
# vigor es el de lo más reciente.
RECENT_DAYS = 14


def plan_goals(user_id: int, db: Session, today: date) -> list[Goal]:
    """Objetivos del plan en vigor, por fecha de carrera (sin fecha, al final)."""
    base = db.query(Workout.goal_id).filter(Workout.user_id == user_id, Workout.goal_id.isnot(None))
    ids = {r[0] for r in base.filter(Workout.status == WorkoutStatus.planned).distinct().all()}
    if not ids:
        ids = {r[0] for r in base.filter(Workout.date >= today - timedelta(days=RECENT_DAYS)).distinct().all()}
    if not ids:
        return []
    goals = db.query(Goal).filter(Goal.user_id == user_id, Goal.id.in_(ids)).all()
    return sorted(goals, key=lambda g: (g.target_race_date is None, g.target_race_date or date.max, g.id))


def plan_kind(goals: list[Goal]) -> str:
    if len(goals) >= 2:
        return "combined"
    return "single" if goals else "none"
