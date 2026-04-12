from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import User
from app.services import strava as strava_service

router = APIRouter(prefix="/api/strava", tags=["strava"])


@router.get("/auth")
def strava_auth(user_id: int = Query(..., description="ID del usuario")):
    """
    Redirige al usuario a la página de autorización de Strava.
    Uso: GET /api/strava/auth?user_id=1
    """
    url = strava_service.get_auth_url(user_id)
    return RedirectResponse(url)


@router.get("/callback")
def strava_callback(
    code: str = Query(...),
    state: str = Query(...),  # user_id que enviamos en el auth
    db: Session = Depends(get_db),
):
    """
    Callback de Strava tras la autorización. Guarda los tokens en la DB.
    """
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
    pages: int = Query(default=2, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """
    Sincroniza las últimas actividades de Strava del usuario.
    Cada página trae 50 actividades (máx 10 páginas = 500 actividades).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not user.strava_access_token:
        raise HTTPException(status_code=400, detail="Usuario no tiene Strava conectado")

    try:
        new_count = strava_service.sync_activities(user, db, pages=pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sincronizando Strava: {e}")

    return {"message": f"Sincronización completada", "new_activities": new_count}


@router.get("/activities/{user_id}")
def get_activities(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Devuelve las actividades de Strava guardadas en la DB."""
    from app.models.strava_activity import StravaActivity

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

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
    """Indica si el usuario tiene Strava conectado."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {
        "connected": bool(user.strava_access_token),
        "athlete_id": user.strava_athlete_id,
    }
