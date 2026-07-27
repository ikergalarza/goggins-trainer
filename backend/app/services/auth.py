"""Autenticación: hash de contraseñas (bcrypt) y tokens JWT."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """Devuelve el user_id de un token de LOGIN, o None si es inválido/expirado.

    Rechaza tokens con `purpose` (p. ej. el `state` del OAuth de Strava): ese
    token viaja por la URL y queda en logs de terceros, así que NO debe servir
    como credencial de acceso a la API.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("purpose") is not None:
            return None
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


# --- Estado firmado para el OAuth de Strava -------------------------------
# El callback de Strava llega como una redirección del navegador, sin cabecera
# Authorization, así que no se puede autenticar con get_current_user. El `state`
# firmado ES la autenticación: va firmado con JWT_SECRET y caduca en minutos, de
# modo que nadie puede forzar `state=<otro_user_id>` para secuestrar la conexión.
_STATE_PURPOSE = "strava_oauth"


def create_state_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "purpose": _STATE_PURPOSE,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_state_token(token: str) -> int | None:
    """user_id del state de Strava, o None si es inválido/caducado/no es de OAuth."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("purpose") != _STATE_PURPOSE:
            return None
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
