import time
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.strava_activity import StravaActivity

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
    # Si el token no ha expirado, no hacemos nada
    if user.strava_token_expires_at and user.strava_token_expires_at > time.time():
        return user

    # Si no tenemos credenciales de la app Strava, no podemos refrescar
    if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
        return user  # usar el token actual y esperar que funcione

    if not user.strava_refresh_token:
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
    response = httpx.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": per_page, "page": page},
    )
    response.raise_for_status()
    return response.json()


def fetch_athlete(access_token: str) -> dict:
    """Obtiene el perfil del atleta."""
    response = httpx.get(
        f"{STRAVA_API_BASE}/athlete",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()


def sync_activities(user: User, db: Session, pages: int = 2) -> int:
    """
    Sincroniza las actividades de Strava del usuario.
    Refresca el token si es necesario.
    Devuelve el número de actividades nuevas guardadas.
    """
    user = refresh_token(user, db)

    new_count = 0
    for page in range(1, pages + 1):
        activities = fetch_activities(user.strava_access_token, per_page=50, page=page)
        if not activities:
            break

        for act in activities:
            exists = db.query(StravaActivity).filter_by(strava_id=act["id"]).first()
            if exists:
                continue

            record = StravaActivity(
                user_id=user.id,
                strava_id=act["id"],
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

    return new_count
