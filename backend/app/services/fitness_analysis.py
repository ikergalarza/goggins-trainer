"""Análisis del estado físico usando Claude.

Junta perfil + marcas + objetivos + histórico reciente de Strava y pide a
Claude una evaluación estructurada en JSON + resumen en español.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.goal import Goal
from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.services import ai_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un entrenador personal de running y Hyrox experto, con conocimientos de fisiología del ejercicio, periodización y análisis de datos deportivos.

Tu tarea: analizar el histórico reciente, marcas y datos físicos del atleta y devolver un diagnóstico objetivo de su estado físico actual, volumen, tendencia y ritmos recomendados.

Reglas:
- Responde SIEMPRE en español.
- Tono directo, profesional, honesto. Sin florituras.
- Basa TODAS las afirmaciones en los datos que te paso. Si faltan datos, dilo explícitamente.
- NUNCA inventes métricas ni hagas suposiciones sin fundamento.
- Devuelve un JSON válido dentro de un bloque ```json ... ``` seguido de un resumen en texto plano.

Formato exacto del JSON:
{
  "fitness_level": "principiante|intermedio|avanzado|elite",
  "current_form": "descanso|base|construcción|pico|fatigado",
  "weekly_km_current": <float>,
  "weekly_km_recommended": <float>,
  "trend": "mejorando|estancado|cansado|detraining",
  "estimated_vdot": <int o null>,
  "target_paces": {
    "easy": "mm:ss",
    "tempo": "mm:ss",
    "threshold": "mm:ss",
    "vo2max": "mm:ss"
  },
  "strengths": ["..."],
  "weaknesses": ["..."],
  "observations": ["..."],
  "next_focus": "..."
}

Después del JSON, añade 2-3 párrafos de resumen explicando tu análisis.
"""


def _format_seconds_to_pace(seconds: int | None) -> str | None:
    if not seconds:
        return None
    m = seconds // 60
    s = seconds % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_context(user: User, db: Session) -> dict[str, Any]:
    """Recolecta toda la información del atleta para pasarla a Claude."""
    # Últimas 12 semanas de actividades
    since = datetime.now(timezone.utc) - timedelta(weeks=12)
    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user.id)
        .order_by(StravaActivity.start_date.desc())
        .limit(200)
        .all()
    )

    # Resumen por semana
    weekly: dict[str, dict[str, float]] = {}
    recent_list = []
    for a in activities:
        if not a.start_date:
            continue
        try:
            dt = a.start_date if isinstance(a.start_date, datetime) else datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
        except Exception:
            continue
        week_key = dt.strftime("%Y-W%V")
        w = weekly.setdefault(week_key, {"km": 0.0, "time_min": 0.0, "activities": 0, "hr_sum": 0.0, "hr_count": 0})
        w["km"] += (a.distance_m or 0) / 1000
        w["time_min"] += (a.moving_time_s or 0) / 60
        w["activities"] += 1
        if a.average_heartrate:
            w["hr_sum"] += a.average_heartrate
            w["hr_count"] += 1

        if len(recent_list) < 30:  # últimas 30 para detalle
            recent_list.append({
                "date": dt.strftime("%Y-%m-%d"),
                "type": a.type,
                "name": a.name,
                "km": round((a.distance_m or 0) / 1000, 2),
                "min": round((a.moving_time_s or 0) / 60, 1),
                "elev_m": round(a.elevation_gain_m or 0),
                "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
                "max_hr": round(a.max_heartrate) if a.max_heartrate else None,
            })

    # Pasar weekly ordenado descendente y con HR medio
    weekly_list = []
    for week, data in sorted(weekly.items(), reverse=True)[:12]:
        avg_hr = round(data["hr_sum"] / data["hr_count"]) if data["hr_count"] > 0 else None
        weekly_list.append({
            "week": week,
            "km": round(data["km"], 1),
            "time_min": round(data["time_min"]),
            "activities": int(data["activities"]),
            "avg_hr": avg_hr,
        })

    # Marcas
    records = db.query(PersonalRecord).filter(PersonalRecord.user_id == user.id).all()
    records_list = []
    for r in records:
        entry = {
            "category": r.category,
            "date": r.date_achieved.isoformat() if r.date_achieved else None,
            "notes": r.notes,
        }
        if r.value_seconds:
            entry["time"] = _format_seconds_to_pace(r.value_seconds)
        if r.value_numeric is not None:
            entry["value"] = r.value_numeric
            entry["unit"] = r.unit
        records_list.append(entry)

    # Objetivos activos
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active == True).all()  # noqa
    goals_list = []
    for g in goals:
        goals_list.append({
            "type": g.type.value if hasattr(g.type, "value") else g.type,
            "sport": g.sport,
            "description": g.description,
            "race_distance_km": g.target_race_distance_km,
            "race_date": g.target_race_date.isoformat() if g.target_race_date else None,
            "target_time": _format_seconds_to_pace(g.target_time_seconds),
            "hyrox_division": g.hyrox_division,
            "weekly_km": g.target_weekly_km,
        })

    return {
        "profile": {
            "name": user.name,
            "age": user.age,
            "sex": user.sex,
            "weight_kg": user.weight_kg,
            "height_cm": user.height_cm,
            "resting_hr": user.resting_heart_rate,
            "max_hr": user.max_heart_rate,
            "years_training": user.years_training,
            "experience_level": user.experience_level,
            "training_days_per_week": user.training_days_per_week,
            "vam_ms": user.vam_ms,
        },
        "personal_records": records_list,
        "active_goals": goals_list,
        "weekly_summary_last_12w": weekly_list,
        "recent_activities": recent_list,
    }


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_response(text: str) -> tuple[dict | None, str]:
    """Extrae JSON y texto resumen de la respuesta de Claude."""
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None, text
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"[fitness_analysis] JSON inválido: {e}")
        return None, text
    summary = text[match.end():].strip()
    return data, summary


def analyze(user: User, db: Session) -> dict[str, Any]:
    """Pide a Claude un análisis del estado físico del usuario.

    Devuelve: { "data": {...}, "summary": "...", "model": "...", "context": {...} }
    """
    logger.info(f"[fitness_analysis] Analizando user={user.id}")
    context = _build_context(user, db)

    user_message = (
        "Analiza a este atleta y devuelve el diagnóstico en el formato especificado.\n\n"
        f"```json\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n```"
    )

    raw = ai_client.complete(
        system=SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=2500,
    )
    data, summary = _parse_response(raw)
    logger.info(f"[fitness_analysis] Análisis listo, data_keys={list(data.keys()) if data else None}")

    return {
        "data": data,
        "summary": summary,
        "raw": raw,
        "model": ai_client.DEFAULT_MODEL,
        "context_size": len(user_message),
    }
