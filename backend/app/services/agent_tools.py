"""Tools que el agente Goggins puede invocar para mutar el plan.

Cada tool tiene:
- Una definición JSONSchema que se le pasa a Claude
- Una función Python que la ejecuta sobre la base de datos del usuario

El executor SIEMPRE valida que el workout pertenece al usuario activo
antes de modificarlo. Devuelve dicts serializables.
"""
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.strava_activity import StravaActivity

logger = logging.getLogger(__name__)


VALID_TYPES = [t.value for t in WorkoutType]
VALID_STATUSES = [s.value for s in WorkoutStatus]


# ────────────────────────────────────────────────────────────────────
# Definiciones de tools para Claude
# ────────────────────────────────────────────────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_workouts",
        "description": (
            "Lista los workouts del atleta en un rango de fechas. Usa esto si "
            "necesitas encontrar workouts que no estén ya en el contexto inicial. "
            "Devuelve id, fecha, tipo, distancia, duración y estado de cada uno."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Fecha de inicio inclusiva en formato YYYY-MM-DD. Por defecto hoy.",
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha de fin inclusiva en formato YYYY-MM-DD. Por defecto +14 días.",
                },
            },
        },
    },
    {
        "name": "move_workout",
        "description": (
            "Mueve un workout planificado a otra fecha. Úsalo cuando el atleta "
            "te pida reprogramar un entreno (p.ej. 'mueve la tirada larga del "
            "sábado al domingo')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "integer", "description": "ID del workout"},
                "new_date": {
                    "type": "string",
                    "description": "Nueva fecha en formato YYYY-MM-DD",
                },
            },
            "required": ["workout_id", "new_date"],
        },
    },
    {
        "name": "update_workout",
        "description": (
            "Modifica las propiedades de un workout: tipo, distancia, duración, "
            "zona cardíaca, instrucciones. Solo cambia los campos que pases."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "integer"},
                "type": {
                    "type": "string",
                    "enum": VALID_TYPES,
                    "description": "Nuevo tipo de workout",
                },
                "distance_km": {"type": "number"},
                "duration_min": {"type": "integer"},
                "hr_zone": {"type": "string", "description": "Z1..Z5 o rango como Z3-Z4"},
                "instructions": {"type": "string"},
            },
            "required": ["workout_id"],
        },
    },
    {
        "name": "delete_workout",
        "description": "Elimina un workout del plan. Úsalo si el atleta quiere descartarlo del todo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "integer"},
            },
            "required": ["workout_id"],
        },
    },
    {
        "name": "add_workout",
        "description": (
            "Crea un nuevo workout en el plan en la fecha indicada. Úsalo cuando "
            "el atleta pida añadir un entreno extra."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Fecha del workout en formato YYYY-MM-DD",
                },
                "type": {"type": "string", "enum": VALID_TYPES},
                "distance_km": {"type": "number"},
                "duration_min": {"type": "integer"},
                "hr_zone": {"type": "string"},
                "instructions": {"type": "string"},
                "goal_id": {
                    "type": "integer",
                    "description": "ID del objetivo al que asociar el workout (opcional)",
                },
            },
            "required": ["date", "type"],
        },
    },
    {
        "name": "add_recurring_workout",
        "description": (
            "Crea el MISMO workout repetido en MUCHAS fechas de una sola vez. "
            "Úsalo SIEMPRE que el atleta pida algo recurrente en vez de llamar a "
            "add_workout una y otra vez: 'mete movilidad todos los días', "
            "'fuerza de tren superior los lunes y jueves', 'core 3 días/semana'. "
            "Indica el rango (start_date/end_date) y, opcionalmente, los días de "
            "la semana. Si no pasas days_of_week, lo crea TODOS los días del rango. "
            "No duplica si ya existe un workout del mismo tipo ese día."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": VALID_TYPES},
                "start_date": {"type": "string", "description": "Inicio del rango YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "Fin del rango YYYY-MM-DD (incluido)"},
                "days_of_week": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 6},
                    "description": "Días de la semana (0=lunes..6=domingo). Si se omite, TODOS los días.",
                },
                "distance_km": {"type": "number"},
                "duration_min": {"type": "integer"},
                "hr_zone": {"type": "string"},
                "instructions": {"type": "string"},
                "goal_id": {"type": "integer"},
            },
            "required": ["type", "start_date", "end_date"],
        },
    },
    {
        "name": "mark_workout_status",
        "description": (
            "Marca un workout como planificado, completado o saltado. Usa "
            "'completed' si el atleta dice que ya lo hizo, 'skipped' si lo saltó."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workout_id": {"type": "integer"},
                "status": {"type": "string", "enum": VALID_STATUSES},
            },
            "required": ["workout_id", "status"],
        },
    },
    {
        "name": "shift_plan",
        "description": (
            "Desplaza TODOS los workouts futuros del plan N días o semanas. "
            "Úsalo cuando el atleta no pueda entrenar un periodo (p.ej. 'no puedo "
            "entrenar esta semana', 'me voy de viaje 3 días') y haya que correr "
            "todo el plan hacia adelante en bloque, en vez de mover entrenos uno "
            "a uno. Pasa 'days' O 'weeks' (uno de los dos)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Nº de días a desplazar (positivo = hacia adelante). Alternativa a 'weeks'.",
                },
                "weeks": {
                    "type": "integer",
                    "description": "Nº de semanas a desplazar (positivo = hacia adelante). Alternativa a 'days'.",
                },
                "from_date": {
                    "type": "string",
                    "description": (
                        "Fecha inclusiva desde la que desplazar (YYYY-MM-DD). "
                        "Por defecto hoy: solo se mueven los workouts en o posteriores a esa fecha."
                    ),
                },
            },
        },
    },
    {
        "name": "adjust_week_load",
        "description": (
            "Escala la distancia y la duración planificadas de TODOS los workouts "
            "de una semana por un factor. Úsalo para subir o bajar la carga: "
            "0.8 = bajar 20% ('me veo flojo/cansado'), 1.15 = subir 15% ('me veo "
            "fuerte/sobrado'). No toca los workouts de descanso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "week_start_date": {
                    "type": "string",
                    "description": (
                        "Fecha de inicio de la semana a ajustar (YYYY-MM-DD). Se "
                        "ajustan los 7 días desde esa fecha inclusive."
                    ),
                },
                "factor": {
                    "type": "number",
                    "description": "Factor multiplicador (>0). 0.8 baja 20%, 1.15 sube 15%.",
                },
            },
            "required": ["week_start_date", "factor"],
        },
    },
    {
        "name": "get_strava_summary",
        "description": (
            "Devuelve un resumen agregado de lo realmente hecho en Strava en los "
            "últimos N días: km totales, tiempo, nº de sesiones y FC media, "
            "desglosado por disciplina (Run, Ride, Swim...). Úsalo para responder "
            "con datos reales a '¿cómo voy?', '¿puedo mejorar?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Ventana en días hacia atrás desde hoy. Por defecto 14.",
                },
            },
        },
    },
    {
        "name": "compare_planned_vs_actual",
        "description": (
            "Compara lo planificado con lo realmente hecho (Strava) en un rango de "
            "fechas. Devuelve km y duración planificados vs reales, y el ratio de "
            "cumplimiento. Úsalo para detectar desfases y justificar subir o bajar "
            "la carga."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Fecha de inicio inclusiva (YYYY-MM-DD).",
                },
                "end_date": {
                    "type": "string",
                    "description": "Fecha de fin inclusiva (YYYY-MM-DD).",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _get_user_workout(workout_id: int, user: User, db: Session) -> Workout | None:
    return (
        db.query(Workout)
        .filter(Workout.id == workout_id, Workout.user_id == user.id)
        .first()
    )


def _serialize_workout(w: Workout) -> dict[str, Any]:
    return {
        "id": w.id,
        "date": w.date.isoformat() if w.date else None,
        "type": w.type.value if hasattr(w.type, "value") else w.type,
        "status": w.status.value if hasattr(w.status, "value") else w.status,
        "distance_km": w.planned_distance_km,
        "duration_min": w.planned_duration_min,
        "hr_zone": w.planned_heart_rate_zone,
        "instructions": w.instructions,
    }


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


# ────────────────────────────────────────────────────────────────────
# Implementaciones
# ────────────────────────────────────────────────────────────────────

def _tool_list_workouts(input: dict, user: User, db: Session) -> dict:
    today = date.today()
    start = _parse_date(input["start_date"]) if input.get("start_date") else today
    end = _parse_date(input["end_date"]) if input.get("end_date") else today + timedelta(days=14)
    workouts = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date >= start,
            Workout.date <= end,
        )
        .order_by(Workout.date.asc())
        .all()
    )
    return {
        "ok": True,
        "count": len(workouts),
        "workouts": [_serialize_workout(w) for w in workouts],
    }


def _tool_move_workout(input: dict, user: User, db: Session) -> dict:
    w = _get_user_workout(int(input["workout_id"]), user, db)
    if not w:
        return {"ok": False, "error": "Workout no encontrado"}
    new_date = _parse_date(input["new_date"])
    old_date = w.date.isoformat() if w.date else None
    w.date = new_date
    w.day_of_week = new_date.weekday()
    w.modified_by = "user"
    db.add(w)
    db.commit()
    db.refresh(w)
    return {
        "ok": True,
        "mutation": "move_workout",
        "workout_id": w.id,
        "from_date": old_date,
        "to_date": new_date.isoformat(),
        "summary": f"Movido workout {w.id} de {old_date} a {new_date.isoformat()}",
    }


def _tool_update_workout(input: dict, user: User, db: Session) -> dict:
    w = _get_user_workout(int(input["workout_id"]), user, db)
    if not w:
        return {"ok": False, "error": "Workout no encontrado"}

    changes: dict[str, Any] = {}
    if "type" in input and input["type"]:
        try:
            w.type = WorkoutType(input["type"])
            changes["type"] = input["type"]
        except ValueError:
            return {"ok": False, "error": f"Tipo inválido: {input['type']}"}
    if "distance_km" in input and input["distance_km"] is not None:
        w.planned_distance_km = float(input["distance_km"])
        changes["distance_km"] = w.planned_distance_km
    if "duration_min" in input and input["duration_min"] is not None:
        w.planned_duration_min = int(input["duration_min"])
        changes["duration_min"] = w.planned_duration_min
    if "hr_zone" in input and input["hr_zone"]:
        w.planned_heart_rate_zone = input["hr_zone"]
        changes["hr_zone"] = w.planned_heart_rate_zone
    if "instructions" in input and input["instructions"]:
        w.instructions = input["instructions"]
        changes["instructions"] = w.instructions

    w.modified_by = "user"
    db.add(w)
    db.commit()
    db.refresh(w)
    return {
        "ok": True,
        "mutation": "update_workout",
        "workout_id": w.id,
        "changes": changes,
        "summary": f"Actualizado workout {w.id}: {', '.join(changes.keys())}",
    }


def _tool_delete_workout(input: dict, user: User, db: Session) -> dict:
    w = _get_user_workout(int(input["workout_id"]), user, db)
    if not w:
        return {"ok": False, "error": "Workout no encontrado"}
    wid = w.id
    wdate = w.date.isoformat() if w.date else None
    db.delete(w)
    db.commit()
    return {
        "ok": True,
        "mutation": "delete_workout",
        "workout_id": wid,
        "summary": f"Eliminado workout {wid} ({wdate})",
    }


def _tool_add_workout(input: dict, user: User, db: Session) -> dict:
    type_str = input.get("type", "easy_run")
    if type_str not in [t.value for t in WorkoutType]:
        return {"ok": False, "error": f"Tipo inválido: {type_str}"}
    try:
        d = _parse_date(input["date"])
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}

    w = Workout(
        user_id=user.id,
        goal_id=input.get("goal_id"),
        date=d,
        day_of_week=d.weekday(),
        type=WorkoutType(type_str),
        status=WorkoutStatus.planned,
        planned_distance_km=input.get("distance_km"),
        planned_duration_min=input.get("duration_min"),
        planned_heart_rate_zone=input.get("hr_zone"),
        instructions=input.get("instructions"),
        modified_by="user",
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return {
        "ok": True,
        "mutation": "add_workout",
        "workout_id": w.id,
        "workout": _serialize_workout(w),
        "summary": f"Añadido workout {type_str} el {d.isoformat()}",
    }


def _tool_mark_workout_status(input: dict, user: User, db: Session) -> dict:
    w = _get_user_workout(int(input["workout_id"]), user, db)
    if not w:
        return {"ok": False, "error": "Workout no encontrado"}
    try:
        w.status = WorkoutStatus(input["status"])
    except ValueError:
        return {"ok": False, "error": f"Status inválido: {input['status']}"}
    w.modified_by = "user"
    db.add(w)
    db.commit()
    db.refresh(w)
    return {
        "ok": True,
        "mutation": "mark_workout_status",
        "workout_id": w.id,
        "status": w.status.value if hasattr(w.status, "value") else w.status,
        "summary": f"Workout {w.id} marcado como {input['status']}",
    }


def _tool_shift_plan(input: dict, user: User, db: Session) -> dict:
    days = input.get("days")
    weeks = input.get("weeks")
    if days is None and weeks is None:
        return {"ok": False, "error": "Indica 'days' o 'weeks'"}
    delta_days = int(days) if days is not None else 0
    if weeks is not None:
        delta_days += int(weeks) * 7
    if delta_days == 0:
        return {"ok": False, "error": "El desplazamiento no puede ser 0"}

    from_date = _parse_date(input["from_date"]) if input.get("from_date") else date.today()
    workouts = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date >= from_date)
        .order_by(Workout.date.asc())
        .all()
    )
    shift = timedelta(days=delta_days)
    for w in workouts:
        w.date = w.date + shift
        w.day_of_week = w.date.weekday()
        w.modified_by = "user"
        db.add(w)
    db.commit()
    return {
        "ok": True,
        "mutation": "shift_plan",
        "shifted_count": len(workouts),
        "shift_days": delta_days,
        "from_date": from_date.isoformat(),
        "summary": (
            f"Desplazados {len(workouts)} workouts {delta_days} días "
            f"desde {from_date.isoformat()}"
        ),
    }


def _tool_adjust_week_load(input: dict, user: User, db: Session) -> dict:
    try:
        factor = float(input["factor"])
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "error": "Factor inválido"}
    if factor <= 0:
        return {"ok": False, "error": "El factor debe ser > 0"}

    try:
        week_start = _parse_date(input["week_start_date"])
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}
    week_end = week_start + timedelta(days=6)

    workouts = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date >= week_start,
            Workout.date <= week_end,
        )
        .order_by(Workout.date.asc())
        .all()
    )
    adjusted = 0
    for w in workouts:
        if w.type == WorkoutType.rest:
            continue
        touched = False
        if w.planned_distance_km is not None:
            w.planned_distance_km = round(w.planned_distance_km * factor, 2)
            touched = True
        if w.planned_duration_min is not None:
            w.planned_duration_min = max(1, round(w.planned_duration_min * factor))
            touched = True
        if touched:
            w.modified_by = "user"
            db.add(w)
            adjusted += 1
    db.commit()
    pct = round((factor - 1) * 100)
    return {
        "ok": True,
        "mutation": "adjust_week_load",
        "adjusted_count": adjusted,
        "factor": factor,
        "week_start_date": week_start.isoformat(),
        "summary": (
            f"Ajustada la carga de {adjusted} workouts de la semana del "
            f"{week_start.isoformat()} ({'+' if pct >= 0 else ''}{pct}%)"
        ),
    }


def _activity_dt(a: StravaActivity) -> datetime | None:
    if not a.start_date:
        return None
    if isinstance(a.start_date, datetime):
        return a.start_date
    try:
        return datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
    except Exception:
        return None


def _tool_get_strava_summary(input: dict, user: User, db: Session) -> dict:
    days = int(input.get("days") or 14)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user.id)
        .order_by(StravaActivity.start_date.desc())
        .limit(200)
        .all()
    )

    by_disc: dict[str, dict[str, float]] = defaultdict(
        lambda: {"sessions": 0, "km": 0.0, "min": 0.0, "_hr_sum": 0.0, "_hr_n": 0}
    )
    total_km = 0.0
    total_min = 0.0
    total_sessions = 0
    for a in activities:
        dt = _activity_dt(a)
        if not dt or dt < since:
            continue
        disc = a.type or "Other"
        km = (a.distance_m or 0) / 1000
        mins = (a.moving_time_s or 0) / 60
        d = by_disc[disc]
        d["sessions"] += 1
        d["km"] += km
        d["min"] += mins
        if a.average_heartrate:
            d["_hr_sum"] += a.average_heartrate
            d["_hr_n"] += 1
        total_km += km
        total_min += mins
        total_sessions += 1

    per_discipline = {}
    for disc, d in by_disc.items():
        per_discipline[disc] = {
            "sessions": int(d["sessions"]),
            "km": round(d["km"], 1),
            "min": round(d["min"], 1),
            "avg_hr": round(d["_hr_sum"] / d["_hr_n"]) if d["_hr_n"] else None,
        }

    return {
        "ok": True,
        "days": days,
        "totals": {
            "sessions": total_sessions,
            "km": round(total_km, 1),
            "min": round(total_min, 1),
        },
        "by_discipline": per_discipline,
        "summary": (
            f"{total_sessions} sesiones, {round(total_km, 1)} km en {days} días"
        ),
    }


def _tool_compare_planned_vs_actual(input: dict, user: User, db: Session) -> dict:
    try:
        start = _parse_date(input["start_date"])
        end = _parse_date(input["end_date"])
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}

    workouts = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date >= start,
            Workout.date <= end,
        )
        .all()
    )
    planned_km = 0.0
    planned_min = 0.0
    planned_count = 0
    completed_count = 0
    skipped_count = 0
    for w in workouts:
        if w.type == WorkoutType.rest:
            continue
        planned_count += 1
        planned_km += w.planned_distance_km or 0
        planned_min += w.planned_duration_min or 0
        if w.status == WorkoutStatus.completed:
            completed_count += 1
        elif w.status == WorkoutStatus.skipped:
            skipped_count += 1

    # Real: actividades de Strava dentro del rango (límites de día completos)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user.id)
        .order_by(StravaActivity.start_date.desc())
        .limit(200)
        .all()
    )
    actual_km = 0.0
    actual_min = 0.0
    actual_count = 0
    for a in activities:
        dt = _activity_dt(a)
        if not dt or dt < start_dt or dt >= end_dt:
            continue
        actual_km += (a.distance_m or 0) / 1000
        actual_min += (a.moving_time_s or 0) / 60
        actual_count += 1

    km_ratio = round(actual_km / planned_km, 2) if planned_km else None
    min_ratio = round(actual_min / planned_min, 2) if planned_min else None

    return {
        "ok": True,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "planned": {
            "workouts": planned_count,
            "km": round(planned_km, 1),
            "min": round(planned_min, 1),
            "completed": completed_count,
            "skipped": skipped_count,
        },
        "actual": {
            "sessions": actual_count,
            "km": round(actual_km, 1),
            "min": round(actual_min, 1),
        },
        "km_completion_ratio": km_ratio,
        "duration_completion_ratio": min_ratio,
        "summary": (
            f"Plan: {round(planned_km, 1)} km / Real: {round(actual_km, 1)} km "
            f"(ratio {km_ratio if km_ratio is not None else 'n/a'})"
        ),
    }


_MAX_RECURRING = 200


def _tool_add_recurring_workout(input: dict, user: User, db: Session) -> dict:
    type_str = input.get("type", "mobility")
    if type_str not in VALID_TYPES:
        return {"ok": False, "error": f"Tipo inválido: {type_str}"}
    try:
        start = _parse_date(input["start_date"])
        end = _parse_date(input["end_date"])
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}
    if end < start:
        return {"ok": False, "error": "end_date debe ser >= start_date"}

    dows = input.get("days_of_week")
    if dows is not None:
        try:
            dows = {int(d) for d in dows}
        except Exception:
            return {"ok": False, "error": "days_of_week inválido"}

    # Fechas objetivo que cumplen el patrón
    target_dates: list[date] = []
    d = start
    while d <= end:
        if dows is None or d.weekday() in dows:
            target_dates.append(d)
            if len(target_dates) > _MAX_RECURRING:
                return {"ok": False, "error": f"Demasiados workouts (>{_MAX_RECURRING}). Acota el rango o los días."}
        d += timedelta(days=1)
    if not target_dates:
        return {"ok": False, "error": "Ninguna fecha coincide con los días indicados"}

    wtype = WorkoutType(type_str)
    goal_id = input.get("goal_id")
    # No duplicar si ya hay un workout del mismo tipo ese día
    existing = {
        (w.date, w.type)
        for w in db.query(Workout).filter(
            Workout.user_id == user.id,
            Workout.date >= start,
            Workout.date <= end,
        ).all()
    }
    created = 0
    for d in target_dates:
        if (d, wtype) in existing:
            continue
        db.add(Workout(
            user_id=user.id,
            goal_id=goal_id,
            date=d,
            day_of_week=d.weekday(),
            type=wtype,
            status=WorkoutStatus.planned,
            planned_distance_km=input.get("distance_km"),
            planned_duration_min=input.get("duration_min"),
            planned_heart_rate_zone=input.get("hr_zone"),
            instructions=input.get("instructions"),
            modified_by="user",
        ))
        created += 1
    db.commit()
    return {
        "ok": True,
        "mutation": "add_recurring_workout",
        "created": created,
        "summary": f"Añadidos {created} workouts '{type_str}' entre {start.isoformat()} y {end.isoformat()}",
    }


_DISPATCH = {
    "list_workouts": _tool_list_workouts,
    "move_workout": _tool_move_workout,
    "update_workout": _tool_update_workout,
    "delete_workout": _tool_delete_workout,
    "add_workout": _tool_add_workout,
    "add_recurring_workout": _tool_add_recurring_workout,
    "mark_workout_status": _tool_mark_workout_status,
    "shift_plan": _tool_shift_plan,
    "adjust_week_load": _tool_adjust_week_load,
    "get_strava_summary": _tool_get_strava_summary,
    "compare_planned_vs_actual": _tool_compare_planned_vs_actual,
}


def execute_tool(name: str, input: dict, user: User, db: Session) -> dict:
    """Ejecuta una tool. Captura excepciones para que Claude pueda adaptarse."""
    fn = _DISPATCH.get(name)
    if not fn:
        return {"ok": False, "error": f"Tool desconocida: {name}"}
    try:
        result = fn(input or {}, user, db)
        logger.info(f"[agent_tools] {name} → {result.get('summary') or result}")
        return result
    except Exception as e:
        logger.exception(f"[agent_tools] error ejecutando {name}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}
