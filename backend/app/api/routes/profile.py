from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.services.hr_zones import compute_hr_zones, compute_paces_from_vam

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileIn(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    resting_heart_rate: Optional[int] = None
    max_heart_rate: Optional[int] = None
    years_training: Optional[int] = None
    experience_level: Optional[str] = None
    training_days_per_week: Optional[int] = None
    vam_ms: Optional[float] = None


def _user_or_create(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, name="Atleta", email=f"user{user_id}@goggins.local")
        db.add(user)
        db.flush()
    return user


@router.get("/{user_id}")
def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = _user_or_create(db, user_id)
    db.commit()
    hr_data = compute_hr_zones(user.age, user.max_heart_rate, user.resting_heart_rate, user.sex)
    paces = compute_paces_from_vam(user.vam_ms) if user.vam_ms else None
    return {
        "id": user.id,
        "name": user.name,
        "age": user.age,
        "sex": user.sex,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
        "resting_heart_rate": user.resting_heart_rate,
        "max_heart_rate": user.max_heart_rate,
        "years_training": user.years_training,
        "experience_level": user.experience_level,
        "training_days_per_week": user.training_days_per_week,
        "vam_ms": user.vam_ms,
        "hr_zones": hr_data,
        "target_paces": paces,
    }


@router.put("/{user_id}")
def update_profile(user_id: int, body: ProfileIn, db: Session = Depends(get_db)):
    user = _user_or_create(db, user_id)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)

    hr_data = compute_hr_zones(user.age, user.max_heart_rate, user.resting_heart_rate, user.sex)
    paces = compute_paces_from_vam(user.vam_ms) if user.vam_ms else None
    return {
        "message": "Perfil actualizado",
        "hr_zones": hr_data,
        "target_paces": paces,
    }
