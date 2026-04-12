import time
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import User
from app.services import strava as strava_service

router = APIRouter(prefix="/api/strava", tags=["strava"])


class TokenInput(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int = 0


@router.post("/tokens/{user_id}")
def set_tokens(user_id: int, body: TokenInput, db: Session = Depends(get_db)):
    """Guarda los tokens de Strava directamente.
    Si el usuario no existe, lo crea automáticamente."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, name="Atleta", email=f"user{user_id}@goggins.local")
        db.add(user)
        db.flush()

    user.strava_access_token = body.access_token
    user.strava_refresh_token = body.refresh_token
    # Si no se pasa expires_at, asumimos que el token es válido 6h
    user.strava_token_expires_at = body.expires_at if body.expires_at > 0 else int(time.time()) + 21600

    # Verificar que el token funciona
    athlete_name = None
    try:
        athlete = strava_service.fetch_athlete(body.access_token)
        user.strava_athlete_id = str(athlete.get("id", ""))
        athlete_name = athlete.get("firstname", "")
    except Exception as e:
        db.add(user)
        db.commit()
        return {
            "message": "Tokens guardados pero no se pudo verificar con Strava",
            "warning": str(e),
        }

    db.add(user)
    db.commit()

    return {
        "message": f"Conectado como {athlete_name}",
        "athlete": athlete_name,
    }


@router.get("/auth")
def strava_auth(user_id: int = Query(...)):
    url = strava_service.get_auth_url(user_id)
    return RedirectResponse(url)


@router.get("/callback")
def strava_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    user_id = int(state)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        token_data = strava_service.exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al obtener tokens: {e}")

    athlete = token_data.get("athlete", {})
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]

    db.add(user)
    db.commit()
    return {"message": "Strava conectado correctamente", "athlete": athlete.get("firstname")}


@router.post("/sync/{user_id}")
def sync_strava(
    user_id: int,
    pages: int = Query(default=1, ge=1, le=5),  # máx 5 páginas para respetar rate limits
    db: Session = Depends(get_db),
):
    """Sincroniza las últimas actividades (máx 50 por página, 5 páginas)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.strava_access_token:
        raise HTTPException(status_code=400, detail="No hay token de Strava. Ve a Perfil y conecta.")

    try:
        new_count = strava_service.sync_activities(user, db, pages=pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de Strava: {e}")

    return {"message": "Sincronización completada", "new_activities": new_count}


@router.get("/activities/{user_id}")
def get_activities(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.models.strava_activity import StravaActivity

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []  # no 404 — el frontend puede seguir funcionando

    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user_id)
        .order_by(StravaActivity.start_date.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": a.id,
            "strava_id": a.strava_id,
            "name": a.name,
            "type": a.type,
            "distance_km": round(a.distance_m / 1000, 2) if a.distance_m else None,
            "moving_time_min": round(a.moving_time_s / 60, 1) if a.moving_time_s else None,
            "elevation_gain_m": a.elevation_gain_m,
            "average_heartrate": a.average_heartrate,
            "max_heartrate": a.max_heartrate,
            "start_date": a.start_date,
        }
        for a in activities
    ]


@router.get("/status/{user_id}")
def strava_status(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"connected": False, "athlete_id": None}

    return {
        "connected": bool(user.strava_access_token),
        "athlete_id": user.strava_athlete_id,
    }
