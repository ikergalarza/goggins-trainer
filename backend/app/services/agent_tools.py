"""Tools que el agente Goggins puede invocar para mutar el plan.

Cada tool tiene:
- Una definición JSONSchema que se le pasa a Claude
- Una función Python que la ejecuta sobre la base de datos del usuario

El executor SIEMPRE valida que el workout pertenece al usuario activo
antes de modificarlo. Devuelve dicts serializables.
"""
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workout import Workout, WorkoutType, WorkoutStatus

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


_DISPATCH = {
    "list_workouts": _tool_list_workouts,
    "move_workout": _tool_move_workout,
    "update_workout": _tool_update_workout,
    "delete_workout": _tool_delete_workout,
    "add_workout": _tool_add_workout,
    "mark_workout_status": _tool_mark_workout_status,
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
