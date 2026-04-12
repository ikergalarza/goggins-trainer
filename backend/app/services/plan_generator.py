"""Generación de planes de entrenamiento usando Claude.

Toma un objetivo activo (carrera o Hyrox) + perfil + estado actual del atleta y
pide a Claude un plan semana a semana, día a día, con tipo de entreno,
distancia, duración, zona cardíaca y descripción.
"""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.goal import Goal
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.services import ai_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Eres un entrenador personal experto en running y Hyrox. Tu trabajo es generar planes de entrenamiento periodizados, realistas y específicos para el objetivo del atleta.

Reglas estrictas:
- Responde SIEMPRE en español.
- Devuelve EXCLUSIVAMENTE un JSON válido dentro de un bloque ```json ... ```. Después puedes añadir un párrafo corto de resumen del enfoque.
- Periodiza el plan: base → construcción → específico → tapering antes de la fecha objetivo (si la hay).
- Respeta los días/semana que el atleta puede entrenar.
- Combina entrenos suaves (Z2), tempo (Z3), umbral (Z4) y series (Z4-Z5). Para Hyrox, alterna running con estaciones de fuerza/funcional.
- Usa SOLO estos `type` válidos: easy_run, tempo, intervals, long_run, recovery, fartlek, hill_repeats, hyrox_sim, hyrox_stations, strength_upper, strength_lower, strength_full, cross_training, rest.
- `day_of_week`: 0=lunes, 1=martes, ..., 6=domingo.
- Cada workout DEBE tener instructions claras: estructura del entreno (calentamiento + bloque principal + vuelta a la calma) en 1-3 frases.
- Usa la información de marcas, ritmos objetivo y volumen actual del atleta para calibrar distancias.

Formato JSON exacto:
{
  "plan_name": "string",
  "weeks": <int>,
  "phases": [{"name": "base|build|peak|taper", "weeks": <int>, "focus": "string"}],
  "weekly_plan": [
    {
      "week": 1,
      "focus": "string",
      "target_km": <float>,
      "workouts": [
        {
          "day_of_week": 0,
          "type": "easy_run",
          "distance_km": 8.0,
          "duration_min": 50,
          "hr_zone": "Z2",
          "instructions": "Trote suave conversacional. Mantén cadencia alta."
        }
      ]
    }
  ]
}
"""


def _format_seconds(seconds: int | None) -> str | None:
    if not seconds:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_context(user: User, goal: Goal, db: Session) -> dict[str, Any]:
    # Volumen reciente — últimas 4 semanas
    since = datetime.now(timezone.utc) - timedelta(weeks=8)
    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user.id)
        .order_by(StravaActivity.start_date.desc())
        .limit(120)
        .all()
    )

    weekly: dict[str, dict[str, float]] = {}
    for a in activities:
        if not a.start_date:
            continue
        try:
            dt = a.start_date if isinstance(a.start_date, datetime) else datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < since:
            continue
        key = dt.strftime("%Y-W%V")
        w = weekly.setdefault(key, {"km": 0.0, "min": 0.0, "n": 0})
        w["km"] += (a.distance_m or 0) / 1000
        w["min"] += (a.moving_time_s or 0) / 60
        w["n"] += 1

    weekly_list = [
        {"week": k, "km": round(v["km"], 1), "min": round(v["min"]), "activities": int(v["n"])}
        for k, v in sorted(weekly.items(), reverse=True)[:8]
    ]

    avg_km = round(sum(w["km"] for w in weekly_list) / max(len(weekly_list), 1), 1) if weekly_list else 0

    records = db.query(PersonalRecord).filter(PersonalRecord.user_id == user.id).all()
    records_list = []
    for r in records:
        entry = {"category": r.category}
        if r.value_seconds:
            entry["time"] = _format_seconds(r.value_seconds)
        if r.value_numeric is not None:
            entry["value"] = r.value_numeric
            entry["unit"] = r.unit
        records_list.append(entry)

    today = date.today()
    days_until_goal = None
    if goal.target_race_date:
        days_until_goal = (goal.target_race_date - today).days

    return {
        "today": today.isoformat(),
        "profile": {
            "name": user.name,
            "age": user.age,
            "sex": user.sex,
            "weight_kg": user.weight_kg,
            "experience_level": user.experience_level,
            "years_training": user.years_training,
            "training_days_per_week": user.training_days_per_week,
            "max_hr": user.max_heart_rate,
            "resting_hr": user.resting_heart_rate,
            "vam_ms": user.vam_ms,
        },
        "goal": {
            "type": goal.type.value if hasattr(goal.type, "value") else goal.type,
            "sport": goal.sport,
            "description": goal.description,
            "race_distance_km": goal.target_race_distance_km,
            "race_date": goal.target_race_date.isoformat() if goal.target_race_date else None,
            "days_until_race": days_until_goal,
            "target_time": _format_seconds(goal.target_time_seconds),
            "hyrox_division": goal.hyrox_division,
            "weekly_km_target": goal.target_weekly_km,
            "notes": goal.notes,
        },
        "current_volume": {
            "avg_km_per_week_last_8w": avg_km,
            "weekly": weekly_list,
        },
        "personal_records": records_list,
    }


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*\})\s*```", re.DOTALL)


def _parse_response(text: str) -> tuple[dict | None, str]:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None, text
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"[plan_generator] JSON inválido: {e}")
        return None, text
    summary = text[match.end():].strip()
    return data, summary


def _compute_weeks(goal: Goal) -> int:
    """Calcula cuántas semanas tiene que durar el plan."""
    if goal.target_race_date:
        delta = goal.target_race_date - date.today()
        weeks = max(1, min(20, (delta.days + 6) // 7))
        return weeks
    return 8  # plan genérico de 8 semanas si no hay fecha


def generate_plan(user: User, goal: Goal, db: Session) -> dict[str, Any]:
    """Llama a Claude, parsea la respuesta y crea Workouts en BD.

    Borra los workouts planificados (no completados) anteriores del mismo
    objetivo antes de crear los nuevos.
    """
    weeks = _compute_weeks(goal)
    logger.info(f"[plan_generator] Generando plan goal={goal.id} weeks={weeks}")

    context = _build_context(user, goal, db)
    context["plan_target_weeks"] = weeks

    user_message = (
        f"Genera un plan de entrenamiento de {weeks} semanas para este atleta. "
        "Periodízalo correctamente, respeta los días disponibles y calibra la carga "
        "en función del volumen reciente. Devuelve el JSON en el formato especificado.\n\n"
        f"```json\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n```"
    )

    raw = ai_client.complete(
        system=SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=6000,
        temperature=0.6,
    )
    data, summary = _parse_response(raw)
    if not data or "weekly_plan" not in data:
        raise ValueError(f"Respuesta de Claude sin weekly_plan: {raw[:300]}")

    # Borrar workouts planificados anteriores del mismo objetivo
    db.query(Workout).filter(
        Workout.goal_id == goal.id,
        Workout.status == WorkoutStatus.planned,
    ).delete(synchronize_session=False)

    # Crear los nuevos workouts
    today = date.today()
    monday_this_week = today - timedelta(days=today.weekday())
    created = 0
    valid_types = {t.value for t in WorkoutType}

    for week_block in data.get("weekly_plan", []):
        week_idx = int(week_block.get("week", 1))
        for w in week_block.get("workouts", []):
            type_str = (w.get("type") or "rest").lower()
            if type_str not in valid_types:
                logger.warning(f"[plan_generator] Tipo desconocido: {type_str}, usando easy_run")
                type_str = "easy_run"
            dow = int(w.get("day_of_week", 0)) % 7
            workout_date = monday_this_week + timedelta(weeks=week_idx - 1, days=dow)

            wk = Workout(
                user_id=user.id,
                goal_id=goal.id,
                date=workout_date,
                week_index=week_idx,
                day_of_week=dow,
                type=WorkoutType(type_str),
                status=WorkoutStatus.planned,
                planned_distance_km=w.get("distance_km"),
                planned_duration_min=w.get("duration_min"),
                planned_heart_rate_zone=w.get("hr_zone"),
                instructions=w.get("instructions"),
            )
            db.add(wk)
            created += 1

    db.commit()
    logger.info(f"[plan_generator] Plan generado: {created} workouts")

    return {
        "plan_name": data.get("plan_name"),
        "weeks": data.get("weeks", weeks),
        "phases": data.get("phases", []),
        "summary": summary,
        "workouts_created": created,
        "model": ai_client.DEFAULT_MODEL,
    }


def match_strava_to_workouts(user: User, db: Session) -> int:
    """Empareja actividades de Strava con workouts planificados del mismo día.

    Para cada workout planificado sin strava_activity_id, busca una actividad
    del usuario en la misma fecha y la enlaza, marcando el workout como
    completado y guardando datos reales.
    """
    workouts = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.strava_activity_id.is_(None),
            Workout.status == WorkoutStatus.planned,
        )
        .all()
    )
    matched = 0
    for w in workouts:
        if not w.date:
            continue
        # Rango UTC del día
        start = datetime.combine(w.date, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        activity = (
            db.query(StravaActivity)
            .filter(
                StravaActivity.user_id == user.id,
                StravaActivity.start_date >= start,
                StravaActivity.start_date < end,
            )
            .order_by(StravaActivity.distance_m.desc())
            .first()
        )
        if not activity:
            continue
        w.strava_activity_id = str(activity.strava_id)
        w.actual_distance_km = round((activity.distance_m or 0) / 1000, 2) if activity.distance_m else None
        w.actual_duration_min = round((activity.moving_time_s or 0) / 60) if activity.moving_time_s else None
        w.actual_avg_heart_rate = int(activity.average_heartrate) if activity.average_heartrate else None
        w.actual_max_heart_rate = int(activity.max_heartrate) if activity.max_heartrate else None
        w.status = WorkoutStatus.completed
        matched += 1
    if matched:
        db.commit()
    logger.info(f"[plan_generator] Empareados {matched} workouts con Strava")
    return matched
