import logging
import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.strava_activity import StravaActivity

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_auth_url(user_id: int) -> str:
    """Genera la URL de autorización de Strava."""
    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "redirect_uri": settings.STRAVA_REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all",
        "state": str(user_id),
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRAVA_AUTH_URL}?{query}"


def exchange_code(code: str) -> dict:
    """Intercambia el código de autorización por tokens."""
    response = httpx.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    return response.json()


def refresh_token(user: User, db: Session) -> User:
    """Refresca el access token si ha expirado.
    Si no hay client_id/secret configurados, usa el token actual tal cual."""
    now = int(time.time())
    logger.info(f"[refresh_token] user={user.id}, expires_at={user.strava_token_expires_at}, now={now}")

    # Si el token no ha expirado, no hacemos nada
    if user.strava_token_expires_at and user.strava_token_expires_at > time.time():
        logger.info("[refresh_token] Token aún válido, no se refresca")
        return user

    # Si no tenemos credenciales de la app Strava, no podemos refrescar
    if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
        logger.warning("[refresh_token] No hay STRAVA_CLIENT_ID/SECRET, usando token actual")
        return user  # usar el token actual y esperar que funcione

    if not user.strava_refresh_token:
        logger.warning("[refresh_token] No hay refresh_token guardado")
        return user

    response = httpx.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": user.strava_refresh_token,
        },
    )
    response.raise_for_status()
    data = response.json()

    user.strava_access_token = data["access_token"]
    user.strava_refresh_token = data["refresh_token"]
    user.strava_token_expires_at = data["expires_at"]
    db.add(user)
    db.commit()
    return user


def fetch_activities(access_token: str, per_page: int = 30, page: int = 1) -> list[dict]:
    """Obtiene las actividades del atleta desde la API de Strava."""
    logger.info(f"[fetch_activities] page={page}, per_page={per_page}")
    response = httpx.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": per_page, "page": page},
    )
    logger.info(f"[fetch_activities] status={response.status_code}")
    if response.status_code != 200:
        logger.error(f"[fetch_activities] Error body: {response.text[:500]}")
    response.raise_for_status()
    data = response.json()
    logger.info(f"[fetch_activities] Recibidas {len(data)} actividades")
    return data


def fetch_activity_full(access_token: str, activity_id: int) -> dict:
    """Devuelve la actividad completa incluyendo laps y segment_efforts."""
    logger.info(f"[fetch_activity_full] activity_id={activity_id}")
    response = httpx.get(
        f"{STRAVA_API_BASE}/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"include_all_efforts": "true"},
        timeout=30.0,
    )
    if response.status_code != 200:
        logger.error(f"[fetch_activity_full] {response.status_code} {response.text[:300]}")
    response.raise_for_status()
    return response.json()


def fetch_activity_streams(access_token: str, activity_id: int) -> dict:
    """Devuelve los streams (series temporales) de una actividad.

    Pedimos los más útiles para análisis de carrera/Hyrox: distance, time,
    heartrate, altitude, velocity_smooth, cadence.
    """
    logger.info(f"[fetch_activity_streams] activity_id={activity_id}")
    types = "distance,time,heartrate,altitude,velocity_smooth,cadence"
    response = httpx.get(
        f"{STRAVA_API_BASE}/activities/{activity_id}/streams",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"keys": types, "key_by_type": "true"},
        timeout=30.0,
    )
    if response.status_code != 200:
        logger.error(f"[fetch_activity_streams] {response.status_code} {response.text[:300]}")
    response.raise_for_status()
    return response.json()


def fetch_athlete(access_token: str) -> dict:
    """Obtiene el perfil del atleta."""
    logger.info("[fetch_athlete] Consultando perfil del atleta...")
    response = httpx.get(
        f"{STRAVA_API_BASE}/athlete",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    logger.info(f"[fetch_athlete] status={response.status_code}")
    if response.status_code != 200:
        logger.error(f"[fetch_athlete] Error body: {response.text[:500]}")
    response.raise_for_status()
    data = response.json()
    logger.info(f"[fetch_athlete] Atleta: {data.get('firstname')} {data.get('lastname')} (id={data.get('id')})")
    return data


def sync_activities(user: User, db: Session, pages: int = 2) -> int:
    """
    Sincroniza las actividades de Strava del usuario.
    Refresca el token si es necesario.
    Devuelve el número de actividades nuevas guardadas.
    """
    logger.info(f"[sync_activities] Iniciando sync para user={user.id}, pages={pages}")
    logger.info(f"[sync_activities] Token present: {bool(user.strava_access_token)}, token length: {len(user.strava_access_token or '')}")

    user = refresh_token(user, db)

    new_count = 0
    for page in range(1, pages + 1):
        try:
            activities = fetch_activities(user.strava_access_token, per_page=50, page=page)
        except httpx.HTTPStatusError as e:
            logger.error(f"[sync_activities] HTTP error al obtener actividades: {e.response.status_code} - {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"[sync_activities] Error inesperado: {type(e).__name__}: {e}")
            raise

        if not activities:
            logger.info(f"[sync_activities] Página {page} vacía, terminando")
            break

        logger.info(f"[sync_activities] Página {page}: {len(activities)} actividades")
        for act in activities:
            strava_id = act["id"]
            exists = db.query(StravaActivity).filter_by(strava_id=strava_id).first()
            if exists:
                continue

            record = StravaActivity(
                user_id=user.id,
                strava_id=strava_id,
                name=act.get("name"),
                type=act.get("type") or act.get("sport_type"),
                distance_m=act.get("distance"),
                moving_time_s=act.get("moving_time"),
                elapsed_time_s=act.get("elapsed_time"),
                elevation_gain_m=act.get("total_elevation_gain"),
                average_speed_ms=act.get("average_speed"),
                max_speed_ms=act.get("max_speed"),
                average_heartrate=act.get("average_heartrate"),
                max_heartrate=act.get("max_heartrate"),
                start_date=act.get("start_date"),
                raw_data=act,
            )
            db.add(record)
            new_count += 1

        db.commit()
        logger.info(f"[sync_activities] Página {page} procesada, {new_count} nuevas hasta ahora")

    logger.info(f"[sync_activities] Sync completada: {new_count} actividades nuevas")
    return new_count
