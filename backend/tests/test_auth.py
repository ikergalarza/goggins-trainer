"""Tests del sistema de auth: hash, tokens, login, autorización y alta de usuarios."""
import pytest
from fastapi import HTTPException

from app.services import auth
from app.api import deps
from app.api.routes import auth as auth_routes
from app.models.user import User


def _mk_user(db, email, password, is_master=False, name="U"):
    u = User(name=name, email=email, hashed_password=auth.hash_password(password), is_master=is_master)
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_hash_y_verify():
    h = auth.hash_password("una-clave-de-prueba")
    assert h != "una-clave-de-prueba"
    assert auth.verify_password("una-clave-de-prueba", h) is True
    assert auth.verify_password("malo", h) is False
    assert auth.verify_password("x", None) is False


def test_token_roundtrip():
    t = auth.create_access_token(42)
    assert auth.decode_token(t) == 42
    assert auth.decode_token("no-es-un-token") is None


def test_login_ok_y_ko(db):
    _mk_user(db, "a@b.com", "secreta")
    out = auth_routes.login(auth_routes.LoginIn(email="A@B.com", password="secreta"), db)
    assert out["access_token"]
    assert out["user"]["email"] == "a@b.com"
    with pytest.raises(HTTPException) as exc:
        auth_routes.login(auth_routes.LoginIn(email="a@b.com", password="mala"), db)
    assert exc.value.status_code == 401


def test_get_current_user(db):
    u = _mk_user(db, "c@b.com", "x")
    token = auth.create_access_token(u.id)
    got = deps.get_current_user(authorization=f"Bearer {token}", db=db)
    assert got.id == u.id
    with pytest.raises(HTTPException):
        deps.get_current_user(authorization=None, db=db)
    with pytest.raises(HTTPException):
        deps.get_current_user(authorization="Bearer basura", db=db)


def test_authorize_user(db):
    normal = _mk_user(db, "n@b.com", "x")
    master = _mk_user(db, "m@b.com", "x", is_master=True)
    # propio: ok
    deps.authorize_user(normal.id, normal)
    # ajeno: 403
    with pytest.raises(HTTPException) as exc:
        deps.authorize_user(normal.id + 999, normal)
    assert exc.value.status_code == 403
    # maestro accede a cualquiera
    deps.authorize_user(normal.id, master)


def test_create_user_solo_maestro(db):
    master = _mk_user(db, "boss@b.com", "x", is_master=True)
    created = auth_routes.create_user(
        auth_routes.CreateUserIn(name="Nuevo", email="nuevo@b.com", password="pw"),
        current=master, db=db,
    )
    assert created["email"] == "nuevo@b.com"
    # email duplicado -> 400
    with pytest.raises(HTTPException) as exc:
        auth_routes.create_user(
            auth_routes.CreateUserIn(name="x", email="nuevo@b.com", password="pw"),
            current=master, db=db,
        )
    assert exc.value.status_code == 400


def test_require_master_bloquea_normales(db):
    normal = _mk_user(db, "reg@b.com", "x")
    with pytest.raises(HTTPException) as exc:
        deps.require_master(current=normal)
    assert exc.value.status_code == 403


# ────────────────────────────────────────────────────────────────────
# Integración HTTP real (TestClient) — valida el stack completo:
# inyección de Header, cadena de Depends y autorización por ruta.
# ────────────────────────────────────────────────────────────────────

def test_http_flow_login_y_proteccion(db, user):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.database import get_db

    user.hashed_password = auth.hash_password("pw")
    db.add(user); db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)  # sin 'with' -> no corre lifespan (no toca Postgres)

        # login OK
        r = client.post("/api/auth/login", json={"email": user.email, "password": "pw"})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # /me sin token -> 401
        assert client.get("/api/auth/me").status_code == 401
        # /me con token -> 200
        assert client.get("/api/auth/me", headers=headers).json()["email"] == user.email

        # datos propios -> 200
        assert client.get(f"/api/goals/{user.id}", headers=headers).status_code == 200
        # datos ajenos (no master) -> 403
        assert client.get("/api/goals/999999", headers=headers).status_code == 403
        # endpoint protegido sin token -> 401
        assert client.get(f"/api/goals/{user.id}").status_code == 401
    finally:
        app.dependency_overrides.clear()
