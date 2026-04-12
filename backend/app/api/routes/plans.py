"""Rutas para planes de entrenamiento."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.models.goal import Goal
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.services import plan_generator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plans", tags=["plans"])


def _serialize_workout(w: Workout) -> dict:
    return {
        "id": w.id,
        "goal_id": w.goal_id,
        "date": w.date.isoformat() if w.date else None,
        "week_index": w.week_index,
        "day_of_week": w.day_of_week,
        "type": w.type.value if hasattr(w.type, "value") else w.type,
        "status": w.status.value if hasattr(w.status, "value") else w.status,
        "planned_distance_km": w.planned_distance_km,
        "planned_duration_min": w.planned_duration_min,
        "planned_heart_rate_zone": w.planned_heart_rate_zone,
        "instructions": w.instructions,
        "actual_distance_km": w.actual_distance_km,
        "actual_duration_min": w.actual_duration_min,
        "actual_avg_heart_rate": w.actual_avg_heart_rate,
        "actual_max_heart_rate": w.actual_max_heart_rate,
        "perceived_effort": w.perceived_effort,
        "notes": w.notes,
        "strava_activity_id": w.strava_activity_id,
        "ai_feedback": w.ai_feedback,
    }


@router.post("/generate/{user_id}/{goal_id}")
def generate(user_id: int, goal_id: int, db: Session = Depends(get_db)):
    """Genera (o regenera) un plan de entrenamiento para un objetivo."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")

    try:
        result = plan_generator.generate_plan(user, goal, db)
    except Exception as e:
        logger.exception(f"[plans] Error generando plan: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando plan: {e}")

    return result


@router.get("/{user_id}")
def list_plan_workouts(
    user_id: int,
    goal_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Lista los workouts del plan (opcionalmente filtrados por objetivo)."""
    q = db.query(Workout).filter(Workout.user_id == user_id)
    if goal_id is not None:
        q = q.filter(Workout.goal_id == goal_id)
    workouts = q.order_by(Workout.date.asc()).all()
    return [_serialize_workout(w) for w in workouts]


class WorkoutUpdate(BaseModel):
    status: Optional[str] = None
    perceived_effort: Optional[int] = None
    notes: Optional[str] = None
    actual_distance_km: Optional[float] = None
    actual_duration_min: Optional[int] = None
    type: Optional[str] = None
    planned_distance_km: Optional[float] = None
    planned_duration_min: Optional[int] = None
    instructions: Optional[str] = None


@router.patch("/workout/{workout_id}")
def update_workout(workout_id: int, body: WorkoutUpdate, db: Session = Depends(get_db)):
    workout = db.query(Workout).filter(Workout.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout no encontrado")

    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        try:
            workout.status = WorkoutStatus(data.pop("status"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Status inválido: {e}")
    if "type" in data:
        try:
            workout.type = WorkoutType(data.pop("type"))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Tipo inválido: {e}")
    for k, v in data.items():
        setattr(workout, k, v)

    db.add(workout)
    db.commit()
    db.refresh(workout)
    return _serialize_workout(workout)


@router.delete("/workout/{workout_id}")
def delete_workout(workout_id: int, db: Session = Depends(get_db)):
    workout = db.query(Workout).filter(Workout.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout no encontrado")
    db.delete(workout)
    db.commit()
    return {"message": "Workout eliminado"}


@router.delete("/by_goal/{user_id}/{goal_id}")
def delete_plan(user_id: int, goal_id: int, db: Session = Depends(get_db)):
    """Borra todos los workouts planificados (no completados) de un objetivo."""
    deleted = (
        db.query(Workout)
        .filter(
            Workout.user_id == user_id,
            Workout.goal_id == goal_id,
            Workout.status == WorkoutStatus.planned,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.post("/match_strava/{user_id}")
def match_strava(user_id: int, db: Session = Depends(get_db)):
    """Empareja workouts planificados con actividades de Strava del mismo día."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    matched = plan_generator.match_strava_to_workouts(user, db)
    return {"matched": matched}
