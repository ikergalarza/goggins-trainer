"""Dependencias de autenticación/autorización para las rutas."""
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.services import auth


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Extrae el usuario del token Bearer. 401 si falta o es inválido."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
    token = authorization.split(" ", 1)[1].strip()
    user_id = auth.decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user


def require_master(current: User = Depends(get_current_user)) -> User:
    if not current.is_master:
        raise HTTPException(status_code=403, detail="Requiere permisos de maestro")
    return current


def authorize_user(user_id: int, current: User) -> None:
    """Permite acceso a los datos de `user_id` solo si es el propio usuario o el maestro."""
    if current.is_master or current.id == user_id:
        return
    raise HTTPException(status_code=403, detail="No tienes acceso a estos datos")
