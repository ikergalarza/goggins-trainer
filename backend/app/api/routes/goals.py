from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.goal import Goal, GoalType

router = APIRouter(prefix="/api/goals", tags=["goals"])


class GoalIn(BaseModel):
    sport: Optional[str] = None       # running | hyrox
    type: str                         # race | hyrox | weekly_km | fitness | custom
    description: str
    target_race_distance_km: Optional[float] = None
    target_race_date: Optional[date] = None
    target_time_seconds: Optional[int] = None
    hyrox_division: Optional[str] = None
    target_weekly_km: Optional[float] = None
    notes: Optional[str] = None
    is_active: bool = True


def _serialize(goal: Goal) -> dict:
    return {
        "id": goal.id,
        "sport": goal.sport,
        "type": goal.type.value if hasattr(goal.type, "value") else goal.type,
        "description": goal.description,
        "target_race_distance_km": goal.target_race_distance_km,
        "target_race_date": goal.target_race_date.isoformat() if goal.target_race_date else None,
        "target_time_seconds": goal.target_time_seconds,
        "hyrox_division": goal.hyrox_division,
        "target_weekly_km": goal.target_weekly_km,
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
    try:
        goal_type = GoalType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Tipo de objetivo inválido: {body.type}")

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
            try:
                value = GoalType(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Tipo inválido: {value}")
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
