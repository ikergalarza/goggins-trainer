"""Regresiones de los arreglos de Strava (revisión adversarial)."""
import httpx
import pytest

from app.services import auth, strava


def _http_error(status: int, body: dict) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://www.strava.com/api/v3/athlete/activities")
    resp = httpx.Response(status, json=body, request=req)
    return httpx.HTTPStatusError("x", request=req, response=resp)


# --- El state de OAuth NO debe valer como token de login (fuga por URL) ---

def test_state_token_no_sirve_como_login():
    state = auth.create_state_token(7)
    assert auth.decode_state_token(state) == 7      # sí como state
    assert auth.decode_token(state) is None          # NO como credencial de acceso


def test_login_token_no_sirve_como_state():
    login = auth.create_access_token(7)
    assert auth.decode_token(login) == 7
    assert auth.decode_state_token(login) is None


# --- El clasificador no debe confundir rate-limit con app-inactive ---

def test_rate_limit_no_es_app_inactive():
    # Strava manda el 429 con resource="Application", igual que app-inactive.
    e = _http_error(429, {"message": "Rate Limit Exceeded",
                          "errors": [{"resource": "Application", "field": "rate limit", "code": "exceeded"}]})
    assert isinstance(strava._classify_http_error(e), strava.StravaRateLimited)


def test_app_inactive_se_detecta():
    e = _http_error(403, {"message": "Forbidden",
                          "errors": [{"resource": "Application", "field": "Status", "code": "Inactive"}]})
    assert isinstance(strava._classify_http_error(e), strava.StravaAppInactive)


def test_token_invalido_es_auth_error():
    e = _http_error(401, {"message": "Authorization Error",
                          "errors": [{"resource": "Athlete", "field": "access_token", "code": "invalid"}]})
    assert isinstance(strava._classify_http_error(e), strava.StravaAuthError)


def test_403_por_scope_es_auth_error():
    e = _http_error(403, {"message": "Forbidden",
                          "errors": [{"resource": "Activity", "field": "access_token", "code": "insufficient"}]})
    assert isinstance(strava._classify_http_error(e), strava.StravaAuthError)
