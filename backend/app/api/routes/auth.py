"""Rutas de autenticación y gestión de usuarios (alta solo por el maestro)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_db
from app.models.user import User
from app.models.goal import Goal
from app.models.workout import Workout
from app.models.strava_activity import StravaActivity
from app.services import auth
from app.api.deps import get_current_user, require_master

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class CreateUserIn(BaseModel):
    name: str
    email: str
    password: str
    is_master: bool = False


def _serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "is_master": bool(u.is_master),
        "strava_connected": bool(u.strava_access_token),
    }


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = (body.email or "").strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if not user or not auth.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    token = auth.create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": _serialize_user(user)}


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return _serialize_user(current)


@router.get("/users")
def list_users(current: User = Depends(require_master), db: Session = Depends(get_db)):
    """Lista todos los usuarios con un resumen (solo maestro)."""
    users = db.query(User).order_by(User.id.asc()).all()
    out = []
    for u in users:
        goals_count = db.query(func.count(Goal.id)).filter(Goal.user_id == u.id).scalar() or 0
        workouts_count = db.query(func.count(Workout.id)).filter(Workout.user_id == u.id).scalar() or 0
        last_activity = (
            db.query(func.max(StravaActivity.start_date))
            .filter(StravaActivity.user_id == u.id)
            .scalar()
        )
        data = _serialize_user(u)
        data.update({
            "goals_count": int(goals_count),
            "workouts_count": int(workouts_count),
            "last_activity": last_activity.isoformat() if last_activity else None,
        })
        out.append(data)
    return out


@router.post("/users")
def create_user(body: CreateUserIn, current: User = Depends(require_master), db: Session = Depends(get_db)):
    """Crea un usuario nuevo (solo maestro)."""
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email y contraseña son obligatorios")
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
    user = User(
        name=body.name or email.split("@")[0],
        email=email,
        hashed_password=auth.hash_password(body.password),
        is_master=bool(body.is_master),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize_user(user)
