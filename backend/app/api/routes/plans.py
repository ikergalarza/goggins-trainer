"""Rutas para planes de entrenamiento."""
import json
import logging
import datetime as _dt
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user, authorize_user
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
        "modified_by": w.modified_by,
    }


@router.post("/generate/{user_id}/{goal_id}")
def generate(user_id: int, goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Genera (o regenera) un plan de entrenamiento para un objetivo (no streaming)."""
    authorize_user(user_id, current)
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


@router.post("/generate_stream/{user_id}/{goal_id}")
def generate_stream(user_id: int, goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stream Server-Sent Events con eventos de progreso de la generación."""
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")

    def event_generator():
        try:
            for event in plan_generator.generate_plan_stream(user, goal, db):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.exception(f"[plans] stream error: {e}")
            yield f"data: {json.dumps({'phase': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{user_id}")
def list_plan_workouts(
    user_id: int,
    goal_id: Optional[int] = Query(default=None),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los workouts del plan (opcionalmente filtrados por objetivo)."""
    authorize_user(user_id, current)
    q = db.query(Workout).filter(Workout.user_id == user_id)
    if goal_id is not None:
        # Incluye también los workouts sin objetivo asignado (p.ej. añadidos por
        # Goggins sin goal_id), para que no queden "huérfanos" e invisibles.
        q = q.filter((Workout.goal_id == goal_id) | (Workout.goal_id.is_(None)))
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
    planned_heart_rate_zone: Optional[str] = None
    instructions: Optional[str] = None
    # OJO: el campo se llama 'date' igual que el tipo datetime.date. Si se anota
    # como Optional[date], Pydantic resuelve el nombre al propio campo (None) y
    # rechaza cualquier fecha ("Input should be None") -> el PATCH de mover
    # entrenos fallaba con 422. Usamos _dt.date (no se solapa con el nombre).
    date: Optional[_dt.date] = None


@router.patch("/workout/{workout_id}")
def update_workout(workout_id: int, body: WorkoutUpdate, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workout = db.query(Workout).filter(Workout.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout no encontrado")
    authorize_user(workout.user_id, current)

    was_completed = workout.status == WorkoutStatus.completed
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
    if "date" in data:
        new_date = data.pop("date")
        workout.date = new_date
        if new_date is not None:
            workout.day_of_week = new_date.weekday()
    for k, v in data.items():
        setattr(workout, k, v)

    # Edición manual desde la app: marca el workout como modificado por el usuario
    # para que Goggins respete los cambios y no los pise en regeneraciones.
    workout.modified_by = "user"

    db.add(workout)
    db.commit()
    db.refresh(workout)

    # Si se acaba de marcar como completado (y no lo estaba), Goggins deja
    # feedback en el chat (import diferido para evitar ciclos).
    if workout.status == WorkoutStatus.completed and not was_completed:
        try:
            from app.services import workout_feedback
            workout_feedback.generate_for_completed(current, [workout], db)
        except Exception as e:
            logger.warning(f"[plans] feedback de completado falló: {e}")

    return _serialize_workout(workout)


@router.delete("/workout/{workout_id}")
def delete_workout(workout_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    workout = db.query(Workout).filter(Workout.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout no encontrado")
    authorize_user(workout.user_id, current)
    db.delete(workout)
    db.commit()
    return {"message": "Workout eliminado"}


@router.delete("/by_goal/{user_id}/{goal_id}")
def delete_plan(user_id: int, goal_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Borra todos los workouts planificados (no completados) de un objetivo."""
    authorize_user(user_id, current)
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
def match_strava(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Empareja workouts planificados con actividades de Strava del mismo día."""
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    matched = plan_generator.match_strava_to_workouts(user, db)
    return {"matched": matched}
