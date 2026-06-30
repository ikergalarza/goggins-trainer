from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.goal import Goal, GoalType

router = APIRouter(prefix="/api/goals", tags=["goals"])


class GoalIn(BaseModel):
    sport: Optional[str] = None       # running | hyrox | triathlon
    type: str                         # race | hyrox | weekly_km | fitness | custom | triathlon (UI)
    description: str
    target_race_distance_km: Optional[float] = None
    target_race_date: Optional[date] = None
    target_time_seconds: Optional[int] = None
    hyrox_division: Optional[str] = None
    target_weekly_km: Optional[float] = None
    # Triatlón (el frontend envía type='triathlon'; se persiste como race + sport=triathlon)
    triathlon_distance: Optional[str] = None   # sprint | olympic | half | ironman
    target_swim_time_seconds: Optional[int] = None
    target_bike_time_seconds: Optional[int] = None
    target_run_time_seconds: Optional[int] = None
    notes: Optional[str] = None
    is_active: bool = True


def _resolve_goal_type(type_str: str) -> GoalType:
    """Resuelve el tipo recibido del frontend a un GoalType válido.

    El triatlón se modela como GoalType.race + sport=triathlon (ver models/goal.py),
    así que el frontend puede mandar type='triathlon' y aquí lo traducimos a race.
    """
    if type_str == "triathlon":
        return GoalType.race
    try:
        return GoalType(type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tipo de objetivo inválido: {type_str}")


def _serialize(goal: Goal) -> dict:
    sport = goal.sport.value if hasattr(goal.sport, "value") else goal.sport
    type_value = goal.type.value if hasattr(goal.type, "value") else goal.type
    # El triatlón se guarda como type=race + sport=triathlon; lo exponemos al
    # frontend como type='triathlon' para que lo distinga y pinte la distancia.
    if (sport or "").lower() == "triathlon":
        type_value = "triathlon"
    return {
        "id": goal.id,
        "sport": sport,
        "type": type_value,
        "description": goal.description,
        "target_race_distance_km": goal.target_race_distance_km,
        "target_race_date": goal.target_race_date.isoformat() if goal.target_race_date else None,
        "target_time_seconds": goal.target_time_seconds,
        "hyrox_division": goal.hyrox_division,
        "target_weekly_km": goal.target_weekly_km,
        "triathlon_distance": goal.triathlon_distance,
        "target_swim_time_seconds": goal.target_swim_time_seconds,
        "target_bike_time_seconds": goal.target_bike_time_seconds,
        "target_run_time_seconds": goal.target_run_time_seconds,
        "notes": goal.notes,
        "is_active": goal.is_active,
        "created_at": goal.created_at.isoformat() if goal.created_at else None,
    }


@router.get("/{user_id}")
def list_goals(user_id: int, active_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(Goal).filter(Goal.user_id == user_id)
    if active_only:
        q = q.filter(Goal.is_active == True)  # noqa
    goals = q.order_by(Goal.created_at.desc()).all()
    return [_serialize(g) for g in goals]


@router.post("/{user_id}")
def create_goal(user_id: int, body: GoalIn, db: Session = Depends(get_db)):
    goal_type = _resolve_goal_type(body.type)

    goal = Goal(
        user_id=user_id,
        sport=body.sport,
        type=goal_type,
        description=body.description,
        target_race_distance_km=body.target_race_distance_km,
        target_race_date=body.target_race_date,
        target_time_seconds=body.target_time_seconds,
        hyrox_division=body.hyrox_division,
        target_weekly_km=body.target_weekly_km,
        triathlon_distance=body.triathlon_distance,
        target_swim_time_seconds=body.target_swim_time_seconds,
        target_bike_time_seconds=body.target_bike_time_seconds,
        target_run_time_seconds=body.target_run_time_seconds,
        notes=body.notes,
        is_active=body.is_active,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _serialize(goal)


@router.put("/{user_id}/{goal_id}")
def update_goal(user_id: int, goal_id: int, body: GoalIn, db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "type":
            value = _resolve_goal_type(value)
        setattr(goal, field, value)

    db.add(goal)
    db.commit()
    db.refresh(goal)
    return _serialize(goal)


@router.delete("/{user_id}/{goal_id}")
def delete_goal(user_id: int, goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == user_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo no encontrado")
    db.delete(goal)
    db.commit()
    return {"message": "Objetivo eliminado"}
