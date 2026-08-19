"""Ritmos adaptativos: se recalculan solos a partir de lo que el atleta hace.

Hasta ahora los ritmos objetivo salían únicamente del test VAM que el usuario
escribe a mano en Perfil: un número estático que envejece. Aquí se derivan de
la MEJOR evidencia reciente, por este orden de frescura/fiabilidad:

  1. Marca personal de carrera reciente (5k/10k/21k/42k, últimos 180 días).
  2. VAM del perfil, si se actualizó hace poco.
  3. Mejores carreras de Strava de las últimas 8 semanas (>=3 km, ritmo
     plausible), tomando la de mayor VDOT.

Se elige la evidencia de mayor VDOT entre las que sean recientes, con la VAM
por delante de las actividades si es más nueva que ellas.

Método: VDOT de Jack Daniels (fórmulas de Daniels & Gilbert):
  VO2 demandado(v)  = -4.60 + 0.182258·v + 0.000104·v²      (v en m/min)
  %VO2max(t)        = 0.8 + 0.1894393·e^(-0.012778·t) + 0.2989558·e^(-0.1932605·t)  (t en min)
  VDOT              = VO2(v) / %VO2max(t)
Los ritmos de entreno (E/M/T/I/R) se obtienen invirtiendo VO2(v) para el %VDOT
que Daniels asigna a cada intensidad.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.models.user import User

logger = logging.getLogger(__name__)

# Distancias (m) de las categorías de marca que sirven para VDOT.
RECORD_DISTANCES_M = {"1mile": 1609.34, "5k": 5000.0, "10k": 10000.0, "21k": 21097.5, "42k": 42195.0}

RECENT_RECORD_DAYS = 180
RECENT_ACTIVITY_DAYS = 56       # 8 semanas
RECENT_VAM_DAYS = 90
MIN_ACTIVITY_M = 3000.0         # por debajo, ruido
MIN_PACE_S_PER_KM = 150         # 2:30/km: más rápido no es una carrera real
MAX_PACE_S_PER_KM = 540         # 9:00/km: más lento es caminar/trote roto

# %VDOT por intensidad (Daniels). E y M son rangos; usamos el centro para el
# ritmo "objetivo" y los extremos para el rango.
INTENSITY_PCT = {
    "easy": (0.59, 0.74),
    "marathon": (0.75, 0.84),
    "threshold": (0.83, 0.88),
    "interval": (0.95, 1.00),
    "repetition": (1.05, 1.10),
}


# --- Daniels-Gilbert ---------------------------------------------------------

def _vo2_for_velocity(v_m_per_min: float) -> float:
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min ** 2


def _pct_vo2max_for_duration(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_performance(distance_m: float, time_s: float) -> float:
    """VDOT de una marca (distancia en m, tiempo en s)."""
    t_min = time_s / 60.0
    v = distance_m / t_min
    return _vo2_for_velocity(v) / _pct_vo2max_for_duration(t_min)


def _velocity_for_vo2(vo2: float) -> float:
    """Invierte VO2(v) (cuadrática) -> v en m/min."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    disc = b * b - 4 * a * c
    return (-b + math.sqrt(disc)) / (2 * a)


def _pace_str(sec_per_km: float) -> str:
    sec = int(round(sec_per_km))
    return f"{sec // 60}:{sec % 60:02d}"


def paces_from_vdot(vdot: float) -> dict[str, str]:
    """Ritmo objetivo (min:seg/km) por intensidad, usando el centro del rango."""
    out: dict[str, str] = {}
    for key, (lo, hi) in INTENSITY_PCT.items():
        pct = (lo + hi) / 2
        v = _velocity_for_vo2(vdot * pct)        # m/min
        out[key] = _pace_str(1000.0 / v * 60.0)
    return out


def pace_ranges_from_vdot(vdot: float) -> dict[str, dict[str, str]]:
    """Rango [rápido, lento] por intensidad, para mostrar en el perfil."""
    out: dict[str, dict[str, str]] = {}
    for key, (lo, hi) in INTENSITY_PCT.items():
        v_fast = _velocity_for_vo2(vdot * hi)
        v_slow = _velocity_for_vo2(vdot * lo)
        out[key] = {"fast": _pace_str(1000.0 / v_fast * 60.0), "slow": _pace_str(1000.0 / v_slow * 60.0)}
    return out


def vdot_from_vam(vam_ms: float) -> float:
    """VAM (m/s, velocidad aeróbica máxima ~ test de 5-6 min) -> VDOT.

    Una VAM sostenida 6 min equivale a una prueba de 6 min a esa velocidad.
    """
    distance = vam_ms * 360.0
    return vdot_from_performance(distance, 360.0)


# --- Evidencia del usuario -----------------------------------------------------

def _best_record(user: User, db: Session, today: date) -> Optional[dict[str, Any]]:
    since = today - timedelta(days=RECENT_RECORD_DAYS)
    rows = (
        db.query(PersonalRecord)
        .filter(
            PersonalRecord.user_id == user.id,
            PersonalRecord.category.in_(list(RECORD_DISTANCES_M)),
            PersonalRecord.value_seconds.isnot(None),
            PersonalRecord.date_achieved >= since,
        )
        .all()
    )
    best = None
    for r in rows:
        dist = RECORD_DISTANCES_M[r.category]
        v = vdot_from_performance(dist, r.value_seconds)
        if best is None or v > best["vdot"]:
            best = {"kind": "record", "vdot": v, "category": r.category, "time_s": r.value_seconds,
                    "date": r.date_achieved.isoformat(), "record_id": r.id}
    return best


def _best_activity(user: User, db: Session, now: datetime) -> Optional[dict[str, Any]]:
    since = now - timedelta(days=RECENT_ACTIVITY_DAYS)
    rows = (
        db.query(StravaActivity)
        .filter(
            StravaActivity.user_id == user.id,
            StravaActivity.start_date >= since,
            StravaActivity.distance_m.isnot(None),
            StravaActivity.moving_time_s.isnot(None),
        )
        .all()
    )
    best = None
    for a in rows:
        t = (a.type or "").lower()
        if "run" not in t:
            continue
        if not a.distance_m or a.distance_m < MIN_ACTIVITY_M or not a.moving_time_s:
            continue
        pace = a.moving_time_s / (a.distance_m / 1000.0)
        if pace < MIN_PACE_S_PER_KM or pace > MAX_PACE_S_PER_KM:
            continue
        v = vdot_from_performance(a.distance_m, a.moving_time_s)
        if best is None or v > best["vdot"]:
            best = {"kind": "activity", "vdot": v, "strava_id": a.strava_id, "name": a.name,
                    "distance_m": a.distance_m, "time_s": a.moving_time_s,
                    "date": a.start_date.date().isoformat() if a.start_date else None}
    return best


def _vam_evidence(user: User, now: datetime) -> Optional[dict[str, Any]]:
    if not user.vam_ms:
        return None
    upd = getattr(user, "vam_updated_at", None)
    if upd is None:
        return None  # VAM sin fecha: no sabemos si es fresca; no la preferimos
    if upd.tzinfo is None:
        upd = upd.replace(tzinfo=timezone.utc)
    if now - upd > timedelta(days=RECENT_VAM_DAYS):
        return None
    return {"kind": "vam", "vdot": vdot_from_vam(user.vam_ms), "vam_ms": user.vam_ms,
            "date": upd.date().isoformat()}


def compute_for_user(user: User, db: Session, now: Optional[datetime] = None) -> Optional[dict[str, Any]]:
    """Calcula VDOT + ritmos del usuario a partir de su mejor evidencia reciente.

    Devuelve None si no hay nada utilizable. No persiste: ver `refresh_for_user`.
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()

    candidates = []
    rec = _best_record(user, db, today)
    if rec:
        candidates.append(rec)
    vam = _vam_evidence(user, now)
    if vam:
        candidates.append(vam)
    act = _best_activity(user, db, now)
    if act:
        # Una VAM reciente manda sobre una actividad más antigua que ella.
        if vam and act.get("date") and vam.get("date") and act["date"] < vam["date"]:
            pass
        else:
            candidates.append(act)
    if not candidates:
        return None

    # Entre evidencias recientes, la de mayor VDOT (la mejor forma demostrada).
    best = max(candidates, key=lambda c: c["vdot"])
    vdot = round(best["vdot"], 1)
    return {
        "vdot": vdot,
        "paces": paces_from_vdot(vdot),
        "ranges": pace_ranges_from_vdot(vdot),
        "source": best,
        "computed_at": now.isoformat(),
    }


def refresh_for_user(user: User, db: Session) -> Optional[dict[str, Any]]:
    """Recalcula y guarda en el usuario (adaptive_paces JSON). Best-effort."""
    try:
        res = compute_for_user(user, db)
    except Exception as e:
        logger.warning(f"[adaptive_paces] cálculo falló para user={user.id}: {e}")
        return None
    if res is None:
        return None
    user.adaptive_paces = res
    db.add(user)
    db.commit()
    logger.info(f"[adaptive_paces] user={user.id} VDOT={res['vdot']} fuente={res['source']['kind']}")
    return res
