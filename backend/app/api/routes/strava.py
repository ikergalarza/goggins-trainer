import logging
import time
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.database import get_db
from app.api.deps import get_current_user, authorize_user
from app.models.user import User
from app.services import strava as strava_service
from app.services import auth as auth_service


def _frontend_redirect(status: str, reason: str = "") -> RedirectResponse:
    """Redirección al frontend (Perfil) con el resultado del OAuth."""
    params = {"strava": status}
    if reason:
        params["reason"] = reason
    return RedirectResponse(url=f"{settings.frontend_base}/profile?{urlencode(params)}", status_code=302)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strava", tags=["strava"])


class TokenInput(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int = 0


@router.post("/tokens/{user_id}")
def set_tokens(user_id: int, body: TokenInput, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Guarda tokens de Strava ya obtenidos (uso manual/depuración).

    Solo persiste si el token verifica contra Strava; si no, no deja al usuario
    marcado como conectado con credenciales inválidas.
    """
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Verificar ANTES de persistir.
    try:
        athlete = strava_service.fetch_athlete(body.access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"El token no es válido para Strava: {e}")

    athlete_id = str(athlete.get("id") or "") or None
    if athlete_id:
        clash = (
            db.query(User)
            .filter(User.strava_athlete_id == athlete_id, User.id != user_id)
            .first()
        )
        if clash:
            raise HTTPException(status_code=409, detail="Esa cuenta de Strava ya está vinculada a otro usuario.")

    user.strava_access_token = body.access_token
    user.strava_refresh_token = body.refresh_token
    user.strava_token_expires_at = body.expires_at if body.expires_at > 0 else int(time.time()) + 21600
    user.strava_athlete_id = athlete_id

    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esa cuenta de Strava ya está vinculada a otro usuario.")

    return {"message": f"Conectado como {athlete.get('firstname', '')}", "athlete": athlete.get("firstname", "")}


@router.get("/auth")
def strava_auth(user_id: int = Query(...), current: User = Depends(get_current_user)):
    # La conexión de Strava es siempre sobre la cuenta propia: nadie (ni el
    # maestro) puede autorizar en Strava en nombre de otro usuario.
    if user_id != current.id:
        raise HTTPException(status_code=403, detail="Solo puedes conectar tu propia cuenta de Strava.")
    # Devolvemos la URL como JSON (en vez de redirigir) para que el frontend
    # pueda pedirla con el token Bearer y luego navegar manualmente a Strava.
    return {"url": strava_service.get_auth_url(current.id)}


@router.get("/callback")
def strava_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
):
    # El usuario puede haber cancelado en la pantalla de Strava.
    if error:
        logger.info(f"[callback] Strava devolvió error={error}")
        return _frontend_redirect("error", "cancelado")

    # El `state` firmado ES la identidad: si no valida, no seguimos.
    user_id = auth_service.decode_state_token(state)
    if user_id is None:
        logger.warning("[callback] state inválido o caducado")
        return _frontend_redirect("error", "state")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"[callback] usuario {user_id} no existe")
        return _frontend_redirect("error", "usuario")

    try:
        token_data = strava_service.exchange_code(code)
    except Exception as e:
        logger.exception(f"[callback] Error al intercambiar código: {e}")
        return _frontend_redirect("error", "intercambio")

    athlete = token_data.get("athlete") or {}
    athlete_id = str(athlete.get("id") or "") or None

    # Impedir vincular la misma cuenta de Strava a dos usuarios distintos.
    if athlete_id:
        clash = (
            db.query(User)
            .filter(User.strava_athlete_id == athlete_id, User.id != user_id)
            .first()
        )
        if clash:
            logger.warning(f"[callback] athlete {athlete_id} ya vinculado a user={clash.id}")
            return _frontend_redirect("error", "cuenta_duplicada")

    user.strava_athlete_id = athlete_id
    user.strava_access_token = token_data.get("access_token")
    user.strava_refresh_token = token_data.get("refresh_token")
    user.strava_token_expires_at = token_data.get("expires_at")

    try:
        db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning(f"[callback] IntegrityError al vincular athlete {athlete_id}")
        return _frontend_redirect("error", "cuenta_duplicada")

    logger.info(f"[callback] Strava conectado para user={user_id}, athlete={athlete.get('firstname')}")
    return _frontend_redirect("ok")


@router.post("/sync/{user_id}")
def sync_strava(
    user_id: int,
    all: bool = Query(default=False),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sincroniza actividades. Con all=true descarga todo el historial."""
    authorize_user(user_id, current)
    max_pages = 50 if all else 2
    logger.info(f"[sync] Petición de sync para user_id={user_id}, all={all}, max_pages={max_pages}")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"[sync] Usuario {user_id} no encontrado")
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.strava_access_token:
        logger.error(f"[sync] Usuario {user_id} sin token de Strava")
        raise HTTPException(status_code=409, detail="No hay conexión con Strava. Ve a Perfil y conéctala.")

    logger.info(f"[sync] Usuario encontrado: {user.name}, athlete_id={user.strava_athlete_id}")

    try:
        new_count = strava_service.sync_activities(user, db, pages=max_pages)
    except strava_service.StravaNotConfigured:
        logger.error("[sync] Strava no configurado en el servidor")
        raise HTTPException(status_code=503, detail="Strava no está configurado en el servidor. Avisa al administrador.")
    except strava_service.StravaAppInactive:
        # No es un fallo del usuario: la app de desarrollador está desactivada.
        logger.warning("[sync] Strava Application Inactive")
        raise HTTPException(status_code=403, detail=(
            "La aplicación de Strava está desactivada ahora mismo. Es un problema de la "
            "cuenta de desarrollador (Strava exige suscripción activa), no de tu cuenta. "
            "Reactívala en strava.com/settings/api."
        ))
    except strava_service.StravaAuthError:
        logger.warning("[sync] token de Strava inválido/caducado")
        raise HTTPException(status_code=409, detail=(
            "Tu conexión con Strava ha caducado o le faltan permisos. Vuelve a conectarla en Perfil."
        ))
    except strava_service.StravaRateLimited:
        raise HTTPException(status_code=429, detail="Demasiadas peticiones a Strava. Reinténtalo en unos minutos.")
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = e.response.text[:300]
        except Exception:
            pass
        logger.warning(f"[sync] HTTP {e.response.status_code}: {body}")
        raise HTTPException(status_code=502, detail="Strava no respondió correctamente. Reinténtalo en un momento.")
    except Exception as e:
        logger.exception(f"[sync] Error durante sync: {e}")
        raise HTTPException(status_code=500, detail=f"Error inesperado al sincronizar: {e}")

    # Empareja con workouts planificados (best-effort, no rompe la sync si falla)
    matched = 0
    try:
        from app.services import plan_generator
        matched = plan_generator.match_strava_to_workouts(user, db)
    except Exception as e:
        logger.warning(f"[sync] match_strava_to_workouts falló: {e}")

    logger.info(f"[sync] Sync completada: {new_count} nuevas, {matched} workouts emparejados")
    return {"message": "Sincronización completada", "new_activities": new_count, "matched_workouts": matched}


@router.get("/activities/{user_id}")
def get_activities(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=5000),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.strava_activity import StravaActivity

    authorize_user(user_id, current)
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


@router.get("/activity/{user_id}/{activity_id}")
def get_activity_detail(
    user_id: int,
    activity_id: int,
    refresh: bool = Query(default=False),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el detalle completo de una actividad: streams, laps, segmentos.

    La primera vez los descarga de Strava y los cachea en `activity_details`.
    Las siguientes llamadas usan la caché. `?refresh=true` fuerza recarga.
    """
    from app.models.strava_activity import StravaActivity
    from app.models.activity_detail import ActivityDetail

    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Acepta el id interno o el strava_id
    activity = (
        db.query(StravaActivity)
        .filter(
            (StravaActivity.id == activity_id) | (StravaActivity.strava_id == activity_id),
            StravaActivity.user_id == user_id,
        )
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    detail = (
        db.query(ActivityDetail)
        .filter(ActivityDetail.activity_id == activity.id)
        .first()
    )

    if detail is None or refresh:
        if not user.strava_access_token:
            raise HTTPException(status_code=409, detail="No hay conexión con Strava. Conéctala en Perfil.")
        try:
            user = strava_service.refresh_token(user, db)
            full = strava_service.fetch_activity_full(user.strava_access_token, activity.strava_id)
        except strava_service.StravaNotConfigured:
            raise HTTPException(status_code=503, detail="Strava no está configurado en el servidor.")
        except strava_service.StravaAppInactive:
            raise HTTPException(status_code=403, detail="La aplicación de Strava está desactivada ahora mismo (cuenta de desarrollador).")
        except strava_service.StravaAuthError:
            raise HTTPException(status_code=409, detail="Tu conexión con Strava ha caducado. Vuelve a conectarla en Perfil.")
        except strava_service.StravaRateLimited:
            raise HTTPException(status_code=429, detail="Demasiadas peticiones a Strava. Reinténtalo en unos minutos.")
        except Exception as e:
            logger.exception(f"[activity] fetch_activity_full falló: {e}")
            raise HTTPException(status_code=502, detail="Strava no respondió correctamente. Reinténtalo en un momento.")

        try:
            streams = strava_service.fetch_activity_streams(user.strava_access_token, activity.strava_id)
        except Exception as e:
            logger.warning(f"[activity] streams falló (no bloqueante): {e}")
            streams = {}

        if detail is None:
            detail = ActivityDetail(activity_id=activity.id)
        detail.streams = streams
        detail.laps = full.get("laps") or []
        detail.segment_efforts = full.get("segment_efforts") or []
        # El payload de detalle incluye campos extra (calories, description, device_name, gear_id…)
        # que la lista de actividades no devuelve. Lo guardamos para usarlo abajo.
        activity.raw_data = full
        db.add(activity)
        db.add(detail)
        db.commit()
        db.refresh(detail)
        db.refresh(activity)

    # Strava devuelve muchos campos extra en raw_data y en el full fetch.
    # Los exponemos sin tocar el schema. Para cadencia en carrera Strava devuelve
    # revoluciones de una sola pierna por minuto: se duplica para obtener spm reales.
    raw = activity.raw_data or {}
    is_run = (activity.type or "").lower().startswith("run")
    avg_cadence_raw = raw.get("average_cadence")
    max_cadence_raw = raw.get("max_cadence")
    avg_cadence_spm = (avg_cadence_raw * 2) if (avg_cadence_raw and is_run) else avg_cadence_raw
    max_cadence_spm = (max_cadence_raw * 2) if (max_cadence_raw and is_run) else max_cadence_raw

    # Zancada media (m) = velocidad media (m/s) * 60 / cadencia (pasos/min)
    avg_stride_m = None
    if avg_cadence_spm and activity.average_speed_ms:
        avg_stride_m = round((activity.average_speed_ms * 60) / avg_cadence_spm, 2)

    return {
        "activity": {
            "id": activity.id,
            "strava_id": activity.strava_id,
            "name": activity.name,
            "type": activity.type,
            "distance_km": round(activity.distance_m / 1000, 2) if activity.distance_m else None,
            "moving_time_min": round(activity.moving_time_s / 60, 1) if activity.moving_time_s else None,
            "elapsed_time_s": activity.elapsed_time_s,
            "elevation_gain_m": activity.elevation_gain_m,
            "average_heartrate": activity.average_heartrate,
            "max_heartrate": activity.max_heartrate,
            "average_speed_ms": activity.average_speed_ms,
            "max_speed_ms": activity.max_speed_ms,
            "start_date": activity.start_date,
            # Extras derivados del payload completo
            "average_cadence_spm": avg_cadence_spm,
            "max_cadence_spm": max_cadence_spm,
            "average_stride_m": avg_stride_m,
            "calories": raw.get("calories"),
            "suffer_score": raw.get("suffer_score"),
            "relative_effort": raw.get("relative_effort") or raw.get("perceived_exertion"),
            "average_temp_c": raw.get("average_temp"),
            "average_watts": raw.get("average_watts"),
            "max_watts": raw.get("max_watts"),
            "weighted_average_watts": raw.get("weighted_average_watts"),
            "kilojoules": raw.get("kilojoules"),
            "device_name": raw.get("device_name"),
            "gear_id": raw.get("gear_id"),
            "pr_count": raw.get("pr_count"),
            "achievement_count": raw.get("achievement_count"),
            "kudos_count": raw.get("kudos_count"),
            "description": raw.get("description"),
            "is_run": is_run,
        },
        "streams": detail.streams or {},
        "laps": detail.laps or [],
        "segment_efforts": detail.segment_efforts or [],
        "fetched_at": detail.fetched_at.isoformat() if detail.fetched_at else None,
    }


@router.get("/weekly_stats/{user_id}")
def weekly_stats(
    user_id: int,
    weeks: int = Query(default=12, ge=1, le=52),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve estadísticas semanales agregadas para las últimas N semanas."""
    from datetime import datetime, timedelta, timezone
    from app.models.strava_activity import StravaActivity

    authorize_user(user_id, current)
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
def strava_status(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"connected": False, "athlete_id": None}

    return {
        "connected": bool(user.strava_access_token),
        "athlete_id": user.strava_athlete_id,
    }
