"""Ritmos adaptativos (VDOT de Daniels) a partir de marcas y actividades reales.

Valores de referencia de las tablas de Daniels (tolerancia ±1 VDOT / ±5 s/km):
- 5k en 20:00  -> VDOT ~49-50 ; E ~5:05-5:30, T ~4:15, I ~3:55
- 10k en 45:00 -> VDOT ~45    ; T ~4:35
- 21.1k en 1:30:00 -> VDOT ~51
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.services import adaptive_paces as ap


def _pace_s(p: str) -> int:
    m, s = p.split(":")
    return int(m) * 60 + int(s)


# --- VDOT puro -----------------------------------------------------------------

def test_vdot_5k_20min_en_rango():
    v = ap.vdot_from_performance(5000, 20 * 60)
    assert 48.5 <= v <= 50.5


def test_vdot_10k_45min_en_rango():
    v = ap.vdot_from_performance(10000, 45 * 60)
    assert 44 <= v <= 46


def test_vdot_media_1h30_en_rango():
    v = ap.vdot_from_performance(21097, 90 * 60)
    assert 50 <= v <= 52


def test_vdot_mas_rapido_es_mayor():
    assert ap.vdot_from_performance(5000, 18 * 60) > ap.vdot_from_performance(5000, 22 * 60)


def test_ritmos_desde_vdot_ordenados_y_plausibles():
    paces = ap.paces_from_vdot(49.5)
    e, m, t, i, r = (_pace_s(paces[k]) for k in ("easy", "marathon", "threshold", "interval", "repetition"))
    # Más rápido cuanto más intenso.
    assert e > m > t > i > r
    # Umbral de un 5k en 20:00 anda por 4:15/km (±10 s).
    assert abs(t - _pace_s("4:15")) <= 10
    assert abs(i - _pace_s("3:55")) <= 10


# --- Elección de la mejor evidencia --------------------------------------------

def _rec(db, user, cat, secs, d):
    r = PersonalRecord(user_id=user.id, category=cat, value_seconds=secs, unit="seconds", date_achieved=d)
    db.add(r); db.commit(); return r


def _run(db, user, sid, km, secs, days_ago):
    a = StravaActivity(user_id=user.id, strava_id=sid, name="run", type="Run",
                       distance_m=km * 1000, moving_time_s=secs,
                       start_date=datetime.now(timezone.utc) - timedelta(days=days_ago))
    db.add(a); db.commit(); return a


def test_usa_marca_reciente_como_fuente(db, user):
    _rec(db, user, "10k", 45 * 60, date.today() - timedelta(days=20))
    res = ap.compute_for_user(user, db)
    assert res is not None
    assert res["source"]["kind"] == "record"
    assert 44 <= res["vdot"] <= 46


def test_ignora_marcas_muy_antiguas_y_usa_actividades(db, user):
    _rec(db, user, "5k", 18 * 60, date.today() - timedelta(days=400))  # vieja: no cuenta
    _run(db, user, 1, 10, 50 * 60, days_ago=5)                          # 10k en 50' reciente
    res = ap.compute_for_user(user, db)
    assert res["source"]["kind"] == "activity"
    assert 40 <= res["vdot"] <= 42.5


def test_sin_datos_devuelve_none(db, user):
    assert ap.compute_for_user(user, db) is None


def test_actividades_cortas_o_muy_lentas_no_cuentan(db, user):
    _run(db, user, 1, 1.2, 8 * 60, days_ago=3)     # <3 km: ruido
    _run(db, user, 2, 8, 90 * 60, days_ago=3)      # 11:15/km: caminata, no sirve
    assert ap.compute_for_user(user, db) is None


def test_entre_varias_actividades_gana_la_de_mayor_vdot(db, user):
    _run(db, user, 1, 10, 60 * 60, days_ago=10)    # 6:00/km
    _run(db, user, 2, 5, 22 * 60, days_ago=4)      # 4:24/km -> mejor
    res = ap.compute_for_user(user, db)
    assert res["source"]["strava_id"] == 2


def test_vam_mas_reciente_gana_sobre_actividad_vieja(db, user):
    user.vam_ms = 5.0  # ~3:20/km de VAM -> VDOT alto (~55)
    user.vam_updated_at = datetime.now(timezone.utc)
    db.commit()
    _run(db, user, 1, 10, 60 * 60, days_ago=40)
    res = ap.compute_for_user(user, db)
    assert res["source"]["kind"] == "vam"
    assert res["vdot"] >= 52
