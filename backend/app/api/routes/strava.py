import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.user import User
from app.services import strava as strava_service

logger = logging.getLogger(__name__)

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
        user = User(id=user_id, name="Atleta", email=f"user{user_id}@goggins.local")
        db.add(user)
        db.flush()

    try:
        token_data = strava_service.exchange_code(code)
    except Exception as e:
        logger.exception(f"[callback] Error al intercambiar código: {e}")
        raise HTTPException(status_code=400, detail=f"Error al obtener tokens: {e}")

    athlete = token_data.get("athlete", {})
    user.strava_athlete_id = str(athlete.get("id", ""))
    user.strava_access_token = token_data["access_token"]
    user.strava_refresh_token = token_data["refresh_token"]
    user.strava_token_expires_at = token_data["expires_at"]

    db.add(user)
    db.commit()
    logger.info(f"[callback] Strava conectado para user={user_id}, athlete={athlete.get('firstname')}")
    return RedirectResponse(url="/")


@router.post("/sync/{user_id}")
def sync_strava(
    user_id: int,
    all: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Sincroniza actividades. Con all=true descarga todo el historial."""
    max_pages = 50 if all else 2
    logger.info(f"[sync] Petición de sync para user_id={user_id}, all={all}, max_pages={max_pages}")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"[sync] Usuario {user_id} no encontrado")
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.strava_access_token:
        logger.error(f"[sync] Usuario {user_id} sin token de Strava")
        raise HTTPException(status_code=400, detail="No hay token de Strava. Ve a Perfil y conecta.")

    logger.info(f"[sync] Usuario encontrado: {user.name}, athlete_id={user.strava_athlete_id}")

    try:
        new_count = strava_service.sync_activities(user, db, pages=max_pages)
    except Exception as e:
        logger.exception(f"[sync] Error durante sync: {e}")
        raise HTTPException(status_code=500, detail=f"Error de Strava: {e}")

    logger.info(f"[sync] Sync completada: {new_count} nuevas actividades")
    return {"message": "Sincronización completada", "new_activities": new_count}


@router.get("/activities/{user_id}")
def get_activities(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=5000),
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


@router.get("/weekly_stats/{user_id}")
def weekly_stats(
    user_id: int,
    weeks: int = Query(default=12, ge=1, le=52),
    db: Session = Depends(get_db),
):
    """Devuelve estadísticas semanales agregadas para las últimas N semanas."""
    from datetime import datetime, timedelta, timezone
    from app.models.strava_activity import StravaActivity

    since = datetime.now(timezone.utc) - timedelta(weeks=weeks + 1)

    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user_id)
        .order_by(StravaActivity.start_date.desc())
        .limit(500)
        .all()
    )

    # Agrupar por lunes de la semana (ISO week starts Monday)
    buckets: dict[str, dict] = {}
    for a in activities:
        if not a.start_date:
            continue
        try:
            dt = a.start_date if isinstance(a.start_date, datetime) else datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < since:
            continue
        # Lunes de la semana
        monday = dt - timedelta(days=dt.weekday())
        key = monday.strftime("%Y-%m-%d")
        b = buckets.setdefault(key, {
            "week_start": key,
            "km": 0.0,
            "time_min": 0.0,
            "activities": 0,
            "elevation_m": 0.0,
            "hr_sum": 0.0,
            "hr_count": 0,
        })
        b["km"] += (a.distance_m or 0) / 1000
        b["time_min"] += (a.moving_time_s or 0) / 60
        b["activities"] += 1
        b["elevation_m"] += a.elevation_gain_m or 0
        if a.average_heartrate:
            b["hr_sum"] += a.average_heartrate
            b["hr_count"] += 1

    # Asegurar que las últimas `weeks` semanas existen aunque estén vacías
    now = datetime.now(timezone.utc)
    current_monday = now - timedelta(days=now.weekday())
    for i in range(weeks):
        monday = current_monday - timedelta(weeks=i)
        key = monday.strftime("%Y-%m-%d")
        buckets.setdefault(key, {
            "week_start": key,
            "km": 0.0,
            "time_min": 0.0,
            "activities": 0,
            "elevation_m": 0.0,
            "hr_sum": 0.0,
            "hr_count": 0,
        })

    # Ordenar ascendente por fecha
    result = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        result.append({
            "week_start": b["week_start"],
            "km": round(b["km"], 1),
            "time_min": round(b["time_min"]),
            "activities": int(b["activities"]),
            "elevation_m": round(b["elevation_m"]),
            "avg_hr": round(b["hr_sum"] / b["hr_count"]) if b["hr_count"] > 0 else None,
        })

    # Limitamos al número pedido (por si hay más)
    return result[-weeks:]


@router.get("/status/{user_id}")
def strava_status(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"connected": False, "athlete_id": None}

    return {
        "connected": bool(user.strava_access_token),
        "athlete_id": user.strava_athlete_id,
    }
