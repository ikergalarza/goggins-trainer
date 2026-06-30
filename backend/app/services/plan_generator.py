"""Generación de planes de entrenamiento usando Claude.

Toma un objetivo activo (carrera o Hyrox) + perfil + estado actual del atleta y
pide a Claude un plan semana a semana, día a día, con tipo de entreno,
distancia, duración, zona cardíaca y descripción.
"""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.goal import Goal
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.services import ai_client
from app.services.triathlon import get_triathlon_distance

logger = logging.getLogger(__name__)


def _is_triathlon(goal: Goal) -> bool:
    """True si el objetivo es un triatlón (sport=triathlon)."""
    sport = goal.sport.value if hasattr(goal.sport, "value") else goal.sport
    return (sport or "").lower() == "triathlon"


SYSTEM_PROMPT = """Eres un entrenador personal experto en running y Hyrox. Tu trabajo es generar planes de entrenamiento periodizados, realistas y específicos para el objetivo del atleta.

Reglas estrictas:
- Responde SIEMPRE en español.
- Devuelve EXCLUSIVAMENTE un JSON válido dentro de un bloque ```json ... ```. Después puedes añadir un párrafo corto de resumen del enfoque.
- Periodiza el plan: base → construcción → específico → tapering antes de la fecha objetivo (si la hay).
- IMPORTANTE: Si hay una fecha de carrera, el plan DEBE generar EXACTAMENTE el número de semanas indicado en `plan_target_weeks` y la última semana DEBE ser la semana de la competición. Incluye el día de la carrera como un workout específico (tipo `rest` o el más adecuado) con instrucciones de calentamiento y estrategia.
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


TRIATHLON_SYSTEM_PROMPT = """Eres un entrenador experto en triatlón. Tu trabajo es generar planes MULTIDEPORTE periodizados, realistas y específicos para la distancia y la fecha de carrera del atleta, repartiendo la carga entre natación, ciclismo y carrera, e incluyendo sesiones brick (bici→carrera encadenadas) y práctica de transiciones.

Reglas estrictas:
- Responde SIEMPRE en español.
- Devuelve EXCLUSIVAMENTE un JSON válido dentro de un bloque ```json ... ```. Después puedes añadir un párrafo corto de resumen del enfoque.
- Periodiza de verdad y reparte por disciplina en cada fase:
  - BASE: volumen aeróbico en las tres disciplinas (Z2), mucha técnica de natación (swim_technique/drills) y rodajes suaves; brick corto y ocasional.
  - BUILD (construcción): sube volumen y mete intensidad específica (umbral en bici y carrera, series de natación), bricks más largos, primeras transiciones.
  - PEAK (específico): sesiones a ritmo de carrera, brick clave que simula la distancia objetivo, open_water si la carrera es en aguas abiertas, transiciones afinadas.
  - TAPER: baja volumen ~40-60% manteniendo algo de intensidad corta; descarga antes de la competición.
- ESCALA la carga a la distancia objetivo (sprint < olympic < half < ironman) y a las semanas disponibles (`plan_target_weeks`). A más distancia, sesiones más largas, más bricks y mayor volumen de bici.
- IMPORTANTE: Si hay fecha de carrera, el plan DEBE generar EXACTAMENTE `plan_target_weeks` semanas y la ÚLTIMA semana DEBE ser la semana de la competición. Incluye el día de la carrera como un workout (tipo `rest` o `brick`) con instrucciones de calentamiento, nutrición y estrategia de transiciones.
- Frecuencia por disciplina realista: normalmente natación 2-3x, bici 2-3x, carrera 2-3x por semana, ajustando a los días disponibles del atleta. No superes los días/semana que puede entrenar (puede haber 2 sesiones el mismo día en distancias largas si tiene sentido).
- Calibra cada disciplina con el volumen reciente del atleta por deporte (run/bike/swim). Si faltan datos de natación o bici, asume nivel principiante en esa disciplina y progresa con prudencia.
- Cada sesión debe llevar la disciplina correcta en `discipline` (swim|bike|run|brick|transition) coherente con su `type`.
- Usa SOLO estos `type` válidos: swim, swim_technique, open_water, bike, brick, transition, easy_run, tempo, intervals, long_run, recovery, fartlek, hill_repeats, strength_full, strength_lower, cross_training, rest.
  - Natación: swim (series/aeróbico), swim_technique (técnica/drills), open_water (aguas abiertas).
  - Ciclismo: bike. Combinado: brick. Transiciones: transition.
  - Carrera: easy_run, tempo, intervals, long_run, recovery, fartlek, hill_repeats.
- `day_of_week`: 0=lunes, 1=martes, ..., 6=domingo.
- Cada workout DEBE tener instructions claras (calentamiento + bloque principal + vuelta a la calma) en 1-3 frases, con referencias a ritmo/potencia/zona cuando aplique.
- En natación usa `distance_km` en km (p.ej. 1.5 = 1500 m) y duración en minutos.

Formato JSON exacto:
{
  "plan_name": "string",
  "weeks": <int>,
  "discipline_split": {"swim": "string", "bike": "string", "run": "string"},
  "phases": [{"name": "base|build|peak|taper", "weeks": <int>, "focus": "string"}],
  "weekly_plan": [
    {
      "week": 1,
      "focus": "string",
      "target_km": <float>,
      "workouts": [
        {
          "day_of_week": 0,
          "discipline": "swim",
          "type": "swim_technique",
          "distance_km": 1.5,
          "duration_min": 45,
          "hr_zone": "Z2",
          "instructions": "Calentamiento 300m suave. 8x50m drills de técnica con 20'' descanso. 200m vuelta a la calma."
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


def _discipline_for_strava_type(strava_type: str | None) -> str | None:
    """Mapea el `type` de una actividad de Strava a una disciplina de triatlón.

    Devuelve 'swim' | 'bike' | 'run' | None (None = no relevante para triatlón).
    """
    if not strava_type:
        return None
    t = strava_type.lower()
    if "swim" in t:
        return "swim"
    if t in ("run", "trailrun", "virtualrun") or "run" in t:
        return "run"
    if t in ("ride", "virtualride", "ebikeride", "gravelride", "mountainbikeride") or "ride" in t or "bike" in t:
        return "bike"
    return None


# Defaults conservadores (nivel principiante) por disciplina cuando no hay datos
# recientes de Strava de esa disciplina. Sirven para que Claude no sobreestime
# la carga inicial. weekly_km / weekly_min orientativos por semana.
_DISCIPLINE_DEFAULTS: dict[str, dict[str, dict[str, float]]] = {
    "sprint": {
        "swim": {"weekly_km": 1.5, "weekly_min": 45},
        "bike": {"weekly_km": 40.0, "weekly_min": 90},
    },
    "olympic": {
        "swim": {"weekly_km": 2.5, "weekly_min": 70},
        "bike": {"weekly_km": 70.0, "weekly_min": 150},
    },
    "half": {
        "swim": {"weekly_km": 3.5, "weekly_min": 100},
        "bike": {"weekly_km": 120.0, "weekly_min": 270},
    },
    "ironman": {
        "swim": {"weekly_km": 5.0, "weekly_min": 140},
        "bike": {"weekly_km": 200.0, "weekly_min": 420},
    },
}


def _build_discipline_volume(
    activities: list[StravaActivity], since: datetime, weeks_window: int = 8
) -> dict[str, dict[str, Any]]:
    """Agrega volumen/frecuencia reciente por disciplina (run/bike/swim).

    Devuelve, por disciplina, los km y minutos totales y MEDIA semanal, además
    de la frecuencia (sesiones por semana). Sirve para que Claude calibre la
    carga de cada deporte por separado en un plan de triatlón.
    """
    agg: dict[str, dict[str, float]] = {
        "swim": {"km": 0.0, "min": 0.0, "n": 0},
        "bike": {"km": 0.0, "min": 0.0, "n": 0},
        "run": {"km": 0.0, "min": 0.0, "n": 0},
    }
    for a in activities:
        if not a.start_date:
            continue
        try:
            dt = a.start_date if isinstance(a.start_date, datetime) else datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < since:
            continue
        disc = _discipline_for_strava_type(a.type)
        if disc is None:
            continue
        bucket = agg[disc]
        bucket["km"] += (a.distance_m or 0) / 1000
        bucket["min"] += (a.moving_time_s or 0) / 60
        bucket["n"] += 1

    out: dict[str, dict[str, Any]] = {}
    for disc, b in agg.items():
        out[disc] = {
            "total_km": round(b["km"], 1),
            "total_min": round(b["min"]),
            "sessions": int(b["n"]),
            "avg_km_per_week": round(b["km"] / weeks_window, 1),
            "avg_min_per_week": round(b["min"] / weeks_window),
            "sessions_per_week": round(b["n"] / weeks_window, 1),
            "has_data": b["n"] > 0,
        }
    return out


def _build_context(user: User, goal: Goal, db: Session) -> dict[str, Any]:
    # Volumen reciente — últimas 8 semanas
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

    goal_ctx: dict[str, Any] = {
        "type": goal.type.value if hasattr(goal.type, "value") else goal.type,
        "sport": goal.sport.value if hasattr(goal.sport, "value") else goal.sport,
        "description": goal.description,
        "race_distance_km": goal.target_race_distance_km,
        "race_date": goal.target_race_date.isoformat() if goal.target_race_date else None,
        "days_until_race": days_until_goal,
        "target_time": _format_seconds(goal.target_time_seconds),
        "hyrox_division": goal.hyrox_division,
        "weekly_km_target": goal.target_weekly_km,
        "notes": goal.notes,
    }

    current_volume: dict[str, Any] = {
        "avg_km_per_week_last_8w": avg_km,
        "weekly": weekly_list,
    }

    # --- Enriquecimiento específico de triatlón ---
    if _is_triathlon(goal):
        dist_key = (goal.triathlon_distance or "").lower()
        dist_cfg = get_triathlon_distance(dist_key)
        goal_ctx["triathlon_distance"] = dist_key or None
        if dist_cfg:
            goal_ctx["triathlon_segments_km"] = {
                "swim_km": dist_cfg["swim_km"],
                "bike_km": dist_cfg["bike_km"],
                "run_km": dist_cfg["run_km"],
            }
            goal_ctx["triathlon_distance_name"] = dist_cfg["name"]
        # Splits objetivo por disciplina (si los hay)
        goal_ctx["target_swim_time"] = _format_seconds(goal.target_swim_time_seconds)
        goal_ctx["target_bike_time"] = _format_seconds(goal.target_bike_time_seconds)
        goal_ctx["target_run_time"] = _format_seconds(goal.target_run_time_seconds)

        # Volumen reciente por disciplina (run/bike/swim) desde Strava.
        by_discipline = _build_discipline_volume(activities, since, weeks_window=8)

        # Rellena con defaults conservadores por distancia donde falten datos.
        defaults = _DISCIPLINE_DEFAULTS.get(dist_key, _DISCIPLINE_DEFAULTS["olympic"])
        for disc in ("swim", "bike"):
            if not by_discipline[disc]["has_data"] and disc in defaults:
                by_discipline[disc]["assumed_default"] = True
                by_discipline[disc]["assumed_level"] = "principiante"
                by_discipline[disc]["assumed_avg_km_per_week"] = defaults[disc]["weekly_km"]
                by_discipline[disc]["assumed_avg_min_per_week"] = defaults[disc]["weekly_min"]

        current_volume["by_discipline"] = by_discipline
        current_volume["discipline_note"] = (
            "avg_*_per_week refleja el volumen REAL reciente por deporte. "
            "Si has_data=false en natación o bici, usa los valores assumed_* "
            "(nivel principiante) como punto de partida conservador."
        )

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
        "goal": goal_ctx,
        "current_volume": current_volume,
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
    """Cuántas semanas debe durar el plan, INCLUYENDO la semana de la carrera.

    Calculamos la distancia en semanas entre el lunes de esta semana y el
    lunes de la semana de la carrera, y le sumamos 1 para que la última
    semana del plan sea siempre la semana de la competición.
    """
    if not goal.target_race_date:
        return 8
    today = date.today()
    monday_this_week = today - timedelta(days=today.weekday())
    race_monday = goal.target_race_date - timedelta(days=goal.target_race_date.weekday())
    weeks_to_race = ((race_monday - monday_this_week).days // 7) + 1
    return max(1, min(30, weeks_to_race))


def generate_plan_stream(user: User, goal: Goal, db: Session) -> Iterator[dict[str, Any]]:
    """Versión streaming: yields events de progreso (phase, message, chunk, done...).

    Usa la API de streaming de Anthropic para emitir chunks de texto en
    tiempo real, de modo que el frontend pueda mostrar una barra de progreso.
    """
    weeks = _compute_weeks(goal)
    is_tri = _is_triathlon(goal)
    logger.info(
        f"[plan_generator] (stream) Generando plan goal={goal.id} weeks={weeks} "
        f"triathlon={is_tri}"
    )

    yield {"phase": "context", "message": f"Analizando tu perfil y volumen reciente ({weeks} semanas)"}
    context = _build_context(user, goal, db)
    context["plan_target_weeks"] = weeks

    if is_tri:
        system_prompt = TRIATHLON_SYSTEM_PROMPT
        user_message = (
            f"Genera un plan de triatlón MULTIDEPORTE de {weeks} semanas para este atleta. "
            "Periodízalo (base→build→peak→taper), reparte la carga entre natación, ciclismo "
            "y carrera, incluye sesiones brick y práctica de transiciones, y escala el volumen "
            "a la distancia objetivo. Respeta los días disponibles y calibra cada disciplina con "
            "el volumen reciente por deporte (current_volume.by_discipline). Devuelve el JSON en "
            "el formato especificado.\n\n"
            f"```json\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n```"
        )
    else:
        system_prompt = SYSTEM_PROMPT
        user_message = (
            f"Genera un plan de entrenamiento de {weeks} semanas para este atleta. "
            "Periodízalo correctamente, respeta los días disponibles y calibra la carga "
            "en función del volumen reciente. Devuelve el JSON en el formato especificado.\n\n"
            f"```json\n{json.dumps(context, ensure_ascii=False, indent=2, default=str)}\n```"
        )

    yield {"phase": "calling_ai", "message": "Pidiendo plan a Claude (puede tardar 30-60s)"}

    client = ai_client.get_client()
    raw_parts: list[str] = []
    try:
        with client.messages.stream(
            model=ai_client.DEFAULT_MODEL,
            max_tokens=6000,
            temperature=0.6,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text_chunk in stream.text_stream:
                if not text_chunk:
                    continue
                raw_parts.append(text_chunk)
                yield {
                    "phase": "streaming",
                    "chunk": text_chunk,
                    "chars": sum(len(p) for p in raw_parts),
                }
    except Exception as e:
        logger.exception(f"[plan_generator] stream falló: {e}")
        yield {"phase": "error", "detail": f"Error llamando a Claude: {e}"}
        return

    raw = "".join(raw_parts)
    yield {"phase": "parsing", "message": "Procesando plan generado"}

    data, summary = _parse_response(raw)
    if not data or "weekly_plan" not in data:
        yield {"phase": "error", "detail": f"Respuesta sin weekly_plan: {raw[:200]}"}
        return

    yield {"phase": "saving", "message": "Guardando entrenos en la base de datos"}

    # Borrar workouts planificados anteriores del mismo objetivo
    try:
        db.query(Workout).filter(
            Workout.goal_id == goal.id,
            Workout.status == WorkoutStatus.planned,
        ).delete(synchronize_session=False)
    except Exception as e:
        logger.warning(f"[plan_generator] no se pudo borrar workouts previos: {e}")
        db.rollback()

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
                modified_by="ai",
            )
            db.add(wk)
            created += 1

    try:
        db.commit()
    except Exception as e:
        logger.exception(f"[plan_generator] commit falló: {e}")
        db.rollback()
        yield {"phase": "error", "detail": f"Error guardando workouts: {e}"}
        return

    logger.info(f"[plan_generator] Plan generado: {created} workouts")
    done_event: dict[str, Any] = {
        "phase": "done",
        "plan_name": data.get("plan_name"),
        "weeks": data.get("weeks", weeks),
        "phases": data.get("phases", []),
        "summary": summary,
        "workouts_created": created,
        "model": ai_client.DEFAULT_MODEL,
        "is_triathlon": is_tri,
    }
    if is_tri and data.get("discipline_split"):
        done_event["discipline_split"] = data.get("discipline_split")
    yield done_event


def generate_plan(user: User, goal: Goal, db: Session) -> dict[str, Any]:
    """Wrapper no-streaming: drena el generador y devuelve el evento `done`."""
    final: dict[str, Any] | None = None
    for event in generate_plan_stream(user, goal, db):
        if event.get("phase") == "done":
            final = event
        elif event.get("phase") == "error":
            raise ValueError(event.get("detail") or "Error generando plan")
    if not final:
        raise ValueError("El generador no produjo evento final")
    return final


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
