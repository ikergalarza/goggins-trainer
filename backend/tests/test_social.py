"""Ranking social del grupo: agregados por usuario y disciplina, nada más.

Reglas:
- Solo agregados (km, min, sesiones por disciplina). Nunca actividades sueltas
  ni datos físicos/email de otros.
- Por disciplina: no se mezclan km de bici con km de carrera.
- Ventanas: semana actual y últimas 4 semanas.
- Quien no tiene actividad sale con ceros (no desaparece del grupo).
"""
from datetime import datetime, timedelta, timezone

from app.models.strava_activity import StravaActivity
from app.models.user import User
from app.services import social


def _u(db, name, email):
    u = User(name=name, email=email); db.add(u); db.commit(); db.refresh(u); return u


def _act(db, user, sid, type_, km, mins, days_ago):
    a = StravaActivity(user_id=user.id, strava_id=sid, name=f"{type_}", type=type_,
                       distance_m=km * 1000, moving_time_s=mins * 60,
                       start_date=datetime.now(timezone.utc) - timedelta(days=days_ago))
    db.add(a); db.commit(); return a


def test_ranking_por_disciplina_no_mezcla_deportes(db, user):
    other = _u(db, "Unai", "unai@x.com")
    _act(db, user, 1, "Run", 10, 50, days_ago=0)     # yo: 10 km carrera
    _act(db, other, 2, "Ride", 40, 80, days_ago=0)   # Unai: 40 km bici

    board = social.leaderboard(db, weeks=1)
    run = {r["user_id"]: r for r in board["disciplines"]["run"]}
    bike = {r["user_id"]: r for r in board["disciplines"]["bike"]}
    # En carrera mando yo; Unai no suma km de carrera aunque haya hecho 40 de bici.
    assert run[user.id]["km"] == 10.0
    assert run[other.id]["km"] == 0.0
    assert bike[other.id]["km"] == 40.0
    assert bike[user.id]["km"] == 0.0
    # Solo nombre de pila (sin apellidos) hacia los demás.
    assert run[user.id]["name"] == "Test"


def test_orden_descendente_y_posicion(db, user):
    a = _u(db, "Asier", "a@x.com"); b = _u(db, "Unai", "u@x.com")
    _act(db, a, 1, "Run", 30, 150, 0); _act(db, b, 2, "Run", 20, 100, 0); _act(db, user, 3, "Run", 25, 120, 0)
    run = social.leaderboard(db, weeks=1)["disciplines"]["run"]
    assert [r["name"] for r in run[:3]] == ["Asier", "Test", "Unai"]
    assert [r["rank"] for r in run[:3]] == [1, 2, 3]


def test_ventana_4_semanas_excluye_lo_viejo(db, user):
    _act(db, user, 1, "Run", 10, 50, days_ago=3)
    _act(db, user, 2, "Run", 99, 500, days_ago=40)   # fuera de 4 semanas
    run = social.leaderboard(db, weeks=4)["disciplines"]["run"]
    me = next(r for r in run if r["user_id"] == user.id)
    assert me["km"] == 10.0


def test_solo_agregados_sin_datos_sensibles(db, user):
    _act(db, user, 1, "Run", 5, 25, 0)
    board = social.leaderboard(db, weeks=1)
    row = board["disciplines"]["run"][0]
    assert set(row.keys()) <= {"user_id", "name", "km", "min", "sessions", "rank", "is_me"}
    assert "email" not in row and "weight_kg" not in row


def test_fuerza_cuenta_sesiones_y_minutos(db, user):
    _act(db, user, 1, "WeightTraining", 0, 45, 0)
    strength = social.leaderboard(db, weeks=1)["disciplines"]["strength"]
    me = next(r for r in strength if r["user_id"] == user.id)
    assert me["sessions"] == 1 and me["min"] == 45


def test_roast_context_es_compacto_y_anonimo(db, user):
    other = _u(db, "Unai", "unai@x.com")
    _act(db, user, 1, "Run", 10, 50, 0); _act(db, other, 2, "Ride", 40, 80, 0)
    ctx = social.roast_context(social.leaderboard(db, weeks=1))
    # Solo nombres de pila y números; nada de emails ni ids.
    assert "unai@x.com" not in ctx and "user_id" not in ctx
    assert "Unai" in ctx and "40" in ctx


# --- hallazgos de la revisión adversarial ------------------------------------

def test_handle_de_email_no_se_publica(db):
    # create_user guarda name = parte local del email si no se da nombre.
    u = _u(db, "ikergalarza1999", "ikergalarza1999@gmail.com")
    assert social.display_name(u) == f"Atleta {u.id}"
    # Un nombre real que coincide con el email sí vale.
    assert social.display_name(_u(db, "Unai", "unai@x.com")) == "Unai"
    # Solo nombre de pila, sin apellidos.
    assert social.display_name(_u(db, "Helene Menayo", "h@x.com")) == "Helene"


def test_empate_exacto_comparte_puesto(db, user):
    a = _u(db, "Asier", "a@x.com")
    _act(db, user, 1, "Run", 10, 50, 0); _act(db, a, 2, "Run", 10, 50, 0)
    run = social.leaderboard(db, weeks=1)["disciplines"]["run"]
    assert [r["rank"] for r in run[:2]] == [1, 1]


def test_cache_por_huella_no_se_pisa_entre_periodos(db, user, monkeypatch):
    from app.services import ai_client
    calls = {"n": 0}
    def fake(*a, **k):
        calls["n"] += 1
        return f"roast {calls['n']}"
    monkeypatch.setattr(ai_client, "complete", fake)
    _act(db, user, 1, "Run", 10, 50, 0)
    b1 = social.leaderboard(db, weeks=1); b4 = social.leaderboard(db, weeks=4)
    social.get_roast(db, b1); social.get_roast(db, b4)
    social.get_roast(db, b1); social.get_roast(db, b4); social.get_roast(db, b1)
    # Dos huellas distintas -> exactamente 2 llamadas, el resto caché.
    assert calls["n"] == 2


def test_fallo_de_ia_no_reintenta_en_cada_carga(db, user, monkeypatch):
    from app.services import ai_client
    calls = {"n": 0}
    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("sin clave")
    monkeypatch.setattr(ai_client, "complete", boom)
    _act(db, user, 1, "Run", 10, 50, 0)
    b = social.leaderboard(db, weeks=1)
    for _ in range(5):
        assert social.get_roast(db, b) is None
    assert calls["n"] == 1  # caché negativa
