import logging
import time
from urllib.parse import urlencode
import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.user import User
from app.models.strava_activity import StravaActivity
from app.services import auth as auth_service

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


# --- Errores tipados ------------------------------------------------------
# Distinguen la CAUSA para que la ruta pueda dar un mensaje y un status HTTP
# correctos, en vez del volcado JSON crudo de Strava.
class StravaError(Exception):
    """Base de los errores de Strava."""


class StravaNotConfigured(StravaError):
    """Faltan STRAVA_CLIENT_ID/SECRET en el servidor."""


class StravaAppInactive(StravaError):
    """La aplicación registrada está Inactive (suscripción del dueño). Afecta a todos."""


class StravaAuthError(StravaError):
    """El token del usuario es inválido/caducado/revocado: hay que reconectar."""


class StravaRateLimited(StravaError):
    """Se ha superado el límite de peticiones de Strava."""


def _classify_http_error(exc: httpx.HTTPStatusError) -> StravaError:
    """Traduce un error HTTP de Strava a una excepción tipada mirando el cuerpo.

    Strava usa 403 tanto para 'app inactiva' como (a veces) para rate limit, y
    401 para token inválido. El cuerpo trae errors[].resource/field/code, que es
    lo fiable; el status por sí solo no basta.
    """
    resp = exc.response
    status = resp.status_code
    body_text = ""
    errors = []
    try:
        body_text = resp.text[:400]
        payload = resp.json()
        errors = payload.get("errors") or []
    except Exception:
        pass

    def _has(field: str, code: str) -> bool:
        return any(
            (e.get("field") == field and e.get("code") == code) for e in errors
        )

    # Rate limit PRIMERO: Strava lo manda con resource="Application" (igual que
    # app-inactive), así que hay que descartarlo antes de mirar la app.
    if status == 429 or "rate limit" in body_text.lower() or _has("rate limit", "exceeded"):
        return StravaRateLimited(body_text)

    # App desactivada: {"resource":"Application","field":"Status","code":"Inactive"}.
    # Señal ESPECÍFICA (field=Status / code=Inactive), no cualquier resource=Application.
    if _has("Status", "Inactive") or any(e.get("code") == "Inactive" for e in errors):
        return StravaAppInactive(body_text)

    # Token inválido/caducado/revocado, o 403 por falta de scope (activity:read_all):
    # en ambos casos el usuario tiene que reconectar.
    if status in (400, 401, 403):
        return StravaAuthError(body_text)

    return StravaError(f"HTTP {status}: {body_text}")


def get_auth_url(user_id: int) -> str:
    """Genera la URL de autorización de Strava con un `state` firmado."""
    params = {
        "client_id": settings.STRAVA_CLIENT_ID,
        "redirect_uri": settings.STRAVA_REDIRECT_URI,
        "response_type": "code",
        # 'force' obliga a Strava a mostrar SIEMPRE la pantalla de consentimiento.
        # Con 'auto', si ya habías autorizado con scope 'read', no re-pregunta y el
        # nuevo scope 'activity:read_all' no se concede -> 403 al leer actividades.
        "approval_prompt": "force",
        "scope": "read,activity:read_all",
        # `state` firmado (no el user_id en claro): impide que alguien fuerce
        # state=<otro_id> y vincule su Strava a la cuenta de otro usuario.
        "state": auth_service.create_state_token(user_id),
    }
    return f"{STRAVA_AUTH_URL}?{urlencode(params)}"


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


def _clear_tokens(user: User, db: Session) -> None:
    """Borra la conexión de Strava del usuario (tokens muertos)."""
    user.strava_access_token = None
    user.strava_refresh_token = None
    user.strava_token_expires_at = None
    db.add(user)
    db.commit()


def refresh_token(user: User, db: Session) -> User:
    """Refresca el access token si está a punto de expirar.

    Lanza excepciones tipadas en lugar de devolver un token muerto en silencio.
    """
    now = int(time.time())
    logger.info(f"[refresh_token] user={user.id}, expires_at={user.strava_token_expires_at}, now={now}")

    # Margen de 60 s: no dar por válido un token que caduca dentro de segundos.
    if user.strava_token_expires_at and user.strava_token_expires_at > now + 60:
        logger.info("[refresh_token] Token aún válido, no se refresca")
        return user

    if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
        logger.error("[refresh_token] Falta STRAVA_CLIENT_ID/SECRET en el servidor")
        raise StravaNotConfigured("Strava no está configurado en el servidor")

    if not user.strava_refresh_token:
        logger.warning("[refresh_token] No hay refresh_token guardado")
        raise StravaAuthError("No hay refresh_token; hay que reconectar")

    try:
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
    except httpx.HTTPStatusError as e:
        err = _classify_http_error(e)
        # Si el refresh token ya no vale, la conexión está muerta: la limpiamos
        # para que el perfil deje de mostrar "conectado" y el usuario reconecte.
        if isinstance(err, StravaAuthError):
            logger.warning(f"[refresh_token] refresh inválido para user={user.id}, limpiando tokens")
            _clear_tokens(user, db)
        raise err

    data = response.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires = data.get("expires_at")
    if not access or not refresh:
        logger.error(f"[refresh_token] respuesta de Strava sin tokens: {str(data)[:200]}")
        raise StravaAuthError("Respuesta de refresco inválida; hay que reconectar")

    user.strava_access_token = access
    user.strava_refresh_token = refresh
    user.strava_token_expires_at = expires
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
            logger.error(f"[sync_activities] HTTP {e.response.status_code}: {e.response.text[:500]}")
            raise _classify_http_error(e)
        except StravaError:
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
            # Dedup POR USUARIO: una misma actividad puede existir para otro
            # usuario sin bloquear la del dueño legítimo.
            exists = (
                db.query(StravaActivity)
                .filter_by(user_id=user.id, strava_id=strava_id)
                .first()
            )
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
            # SAVEPOINT por inserción: si otra sincronización solapada del mismo
            # usuario ya metió esta actividad, el UNIQUE(user_id, strava_id)
            # salta aquí y solo descartamos esta fila, sin tumbar la página.
            try:
                with db.begin_nested():
                    db.add(record)
            except IntegrityError:
                logger.info(f"[sync_activities] {strava_id} ya existía (carrera), se omite")
                continue
            new_count += 1

        db.commit()
        logger.info(f"[sync_activities] Página {page} procesada, {new_count} nuevas hasta ahora")

    logger.info(f"[sync_activities] Sync completada: {new_count} actividades nuevas")
    return new_count
