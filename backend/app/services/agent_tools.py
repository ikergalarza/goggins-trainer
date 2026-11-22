"""Tools que el agente Goggins puede invocar para mutar el plan.

Cada tool tiene:
- Una definición JSONSchema que se le pasa a Claude
- Una función Python que la ejecuta sobre la base de datos del usuario

El executor SIEMPRE valida que el workout pertenece al usuario activo
antes de modificarlo. Devuelve dicts serializables.
"""
import copy
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import current_plan as plan_svc, wod_duration, wod_structure
from app.services.clock import today_madrid, weekday_es
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.strava_activity import StravaActivity
from app.models.goal import Goal

logger = logging.getLogger(__name__)


VALID_TYPES = [t.value for t in WorkoutType]


def _goal_id_for_date(user: User, db: Session, d: date, explicit: Any = None) -> int | None:
    """Objetivo al que pertenece un workout de la fecha `d`.

    Antes se asociaba al "último objetivo creado": en un plan combinado eso lo
    dejaba en el objetivo equivocado (y fuera de la vista de su bloque). Ahora
    manda la fecha: el objetivo del plan en vigor cuya carrera aún no ha pasado
    en `d` (o el último si `d` es posterior a todas). Un `goal_id` del modelo
    solo se respeta si es de este usuario.
    """
    if explicit:
        try:
            own = db.query(Goal.id).filter(Goal.id == int(explicit), Goal.user_id == user.id).first()
        except (TypeError, ValueError):
            own = None
        if own:
            return own[0]
    goals = plan_svc.plan_goals(user.id, db, today_madrid())
    if not goals:
        goals = (
            db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active.is_(True)).all()
        )
        goals.sort(key=lambda g: (g.target_race_date is None, g.target_race_date or date.max, g.id))
    dated = [g for g in goals if g.target_race_date]
    for g in dated:
        if g.target_race_date >= d:
            return g.id
    if dated:
        return dated[-1].id
    return max(goals, key=lambda g: g.id).id if goals else None


# Fechas razonables para tocar el plan: hasta 2 semanas atrás (apuntar lo de
# ayer) y hasta 2 años adelante. Lo demás casi seguro es un día/año mal resuelto.
_PAST_TOLERANCE_DAYS = 14
_FUTURE_LIMIT_DAYS = 730


def _check_date(d: date) -> str | None:
    """None si la fecha es razonable; si no, el error que ve el modelo para corregirla."""
    today = today_madrid()
    delta = (d - today).days
    if delta < -_PAST_TOLERANCE_DAYS or delta > _FUTURE_LIMIT_DAYS:
        return (
            f"La fecha {d.isoformat()} ({weekday_es(d)}) queda muy lejos de hoy ({weekday_es(today)} {today.isoformat()}). "
            "Búscala en `calendar` del contexto y repite con la fecha correcta."
        )
    return None


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
                "structure": {
                    "type": "object",
                    "description": "WOD estructurado (objetivo, warmup{duration_min,steps}, blocks[{title,format,rounds,rest_s,items[{exercise,reps,distance_m,duration_s,weight_kg,pace}]}], cooldown, notes). OBLIGATORIO en workouts Hyrox/fuerza: pesos y dosis concretos en cada item.",
                },
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
                "structure": {
                    "type": "object",
                    "description": "WOD estructurado (objetivo, warmup{duration_min,steps}, blocks[{title,format,rounds,rest_s,items[{exercise,reps,distance_m,duration_s,weight_kg,pace}]}], cooldown, notes). OBLIGATORIO en workouts Hyrox/fuerza: pesos y dosis concretos en cada item.",
                },
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
                "structure": {
                    "type": "object",
                    "description": "WOD estructurado (mismo formato que en add_workout); se aplica a todas las fechas. OBLIGATORIO en Hyrox/fuerza.",
                },
                "goal_id": {"type": "integer", "description": "Opcional: normalmente se deduce de cada fecha."},
            },
            "required": ["type", "start_date", "end_date"],
        },
    },
    {
        "name": "add_weekly_session",
        "description": (
            "Añade UNA sesión más por semana durante todo el plan (o el tramo indicado): "
            "'un día más de entreno a la semana', 'una sesión de X cada semana'. Si no pasas "
            "`weekday`, elige el día de la semana más libre. Se salta los días pasados y las "
            "semanas de carrera, y asocia cada sesión al objetivo de su fecha. Para Hyrox/fuerza "
            "pasa `structure` (el mismo WOD se repite cada semana). Sin end_date, llega hasta la "
            "última carrera."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": VALID_TYPES},
                "weekday": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 6,
                    "description": "Día de la semana (0=lunes ... 6=domingo). Si se omite, se elige el más libre.",
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto mañana."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD (incluido). Por defecto, la última carrera."},
                "distance_km": {"type": "number"},
                "duration_min": {"type": "integer"},
                "hr_zone": {"type": "string"},
                "instructions": {"type": "string"},
                "structure": {
                    "type": "object",
                    "description": "WOD estructurado (objetivo, warmup{duration_min,steps}, blocks[{title,format,rounds,rest_s,items[{exercise,reps,distance_m,duration_s,weight_kg,pace}]}], cooldown, notes). OBLIGATORIO en Hyrox/fuerza.",
                },
                "skip_race_week": {
                    "type": "boolean",
                    "description": "Por defecto true: no añade nada en la semana de cada carrera.",
                },
                "goal_id": {"type": "integer", "description": "Opcional: normalmente se deduce de la fecha. Solo un id de `active_goals`."},
            },
            "required": ["type"],
        },
    },
    {
        "name": "set_training_days_per_week",
        "description": (
            "Guarda cuántos días a la semana entrena el atleta (1-7) para que los planes futuros "
            "lo respeten. Llámala cuando pida entrenar un día más o menos de forma permanente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 7}},
            "required": ["days"],
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
    {
        "name": "set_training_feedback",
        "description": (
            "Guarda dónde va FUERTE o FLOJO el atleta en un área o estación "
            "(p. ej. sled_push, wall_balls, running, remo, agarre). Úsala SIEMPRE "
            "que el atleta te cuente sensaciones estables ('voy fatal en sled push', "
            "'el remo lo llevo sobrado') para que los próximos WODs lo tengan en cuenta. "
            "rating: 'fuerte' | 'normal' | 'flojo'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {"type": "string", "description": "Estación o área (slug corto: sled_push, wall_balls, running, ski_erg, row, farmers_carry, sandbag_lunges, burpee_broad_jump, fuerza, agarre...)"},
                "rating": {"type": "string", "enum": ["fuerte", "normal", "flojo"]},
                "note": {"type": "string", "description": "Detalle opcional en palabras del atleta"},
            },
            "required": ["area", "rating"],
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
        "structure": w.structure,
    }


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


# ────────────────────────────────────────────────────────────────────
# Implementaciones
# ────────────────────────────────────────────────────────────────────

def _tool_list_workouts(input: dict, user: User, db: Session) -> dict:
    today = today_madrid()
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
    bad = _check_date(new_date)
    if bad:
        return {"ok": False, "error": bad}
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
    if "structure" in input and input["structure"] is not None:
        w.structure = wod_structure.sanitize(input["structure"])
        changes["structure"] = "actualizado" if w.structure else "vacío/inválido"
        # La duración sale del WOD nuevo; un `duration_min` suelto (sin tocar el
        # WOD) sí se respeta: es el atleta pidiendo otra duración expresamente.
        if wod_duration.apply_to_workout(w):
            changes["duration_min"] = w.planned_duration_min

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
    bad = _check_date(d)
    if bad:
        return {"ok": False, "error": bad}

    w = Workout(
        user_id=user.id,
        goal_id=_goal_id_for_date(user, db, d, input.get("goal_id")),
        date=d,
        day_of_week=d.weekday(),
        type=WorkoutType(type_str),
        status=WorkoutStatus.planned,
        planned_distance_km=input.get("distance_km"),
        planned_duration_min=input.get("duration_min"),
        planned_heart_rate_zone=input.get("hr_zone"),
        instructions=input.get("instructions"),
        structure=wod_structure.sanitize(input.get("structure")),
        modified_by="user",
    )
    wod_duration.apply_to_workout(w)
    otros = [
        {"id": o.id, "type": o.type.value if hasattr(o.type, "value") else o.type}
        for o in db.query(Workout).filter(Workout.user_id == user.id, Workout.date == d).all()
    ]
    db.add(w)
    db.commit()
    db.refresh(w)
    return {
        "ok": True,
        "mutation": "add_workout",
        "workout_id": w.id,
        "workout": _serialize_workout(w),
        "weekday": weekday_es(d),
        "goal_id": w.goal_id,
        "same_day_other_workouts": otros,
        "summary": f"Añadido workout {type_str} el {weekday_es(d)} {d.isoformat()}",
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

    from_date = _parse_date(input["from_date"]) if input.get("from_date") else today_madrid()
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


def _new_session(user: User, db: Session, d: date, wtype: WorkoutType, input: dict, structure: dict | None) -> Workout:
    """Workout planificado de una sesión recurrente/semanal, con su objetivo y su duración calculada."""
    w = Workout(
        user_id=user.id,
        goal_id=_goal_id_for_date(user, db, d, input.get("goal_id")),
        date=d,
        day_of_week=d.weekday(),
        type=wtype,
        status=WorkoutStatus.planned,
        planned_distance_km=input.get("distance_km"),
        planned_duration_min=input.get("duration_min"),
        planned_heart_rate_zone=input.get("hr_zone"),
        instructions=input.get("instructions"),
        structure=copy.deepcopy(structure),
        modified_by="user",
    )
    wod_duration.apply_to_workout(w)
    return w


# Orden de preferencia cuando varios días de la semana están igual de libres:
# miércoles, viernes, sábado... (los extremos de la semana, al final).
_WEEKDAY_PREFERENCE = [2, 4, 5, 1, 3, 6, 0]


def _freest_weekday(existing: list[Workout]) -> int:
    """Día de la semana con menos entrenos (y con vecinos menos cargados)."""
    count = [0] * 7
    for w in existing:
        if w.type != WorkoutType.rest:
            count[w.date.weekday()] += 1
    return min(
        _WEEKDAY_PREFERENCE,
        key=lambda wd: (count[wd] * 10 + count[(wd - 1) % 7] + count[(wd + 1) % 7], _WEEKDAY_PREFERENCE.index(wd)),
    )


def _tool_add_weekly_session(input: dict, user: User, db: Session) -> dict:
    type_str = input.get("type")
    if type_str not in VALID_TYPES or type_str in ("race", "rest"):
        return {"ok": False, "error": f"Tipo inválido para una sesión semanal: {type_str}"}
    today = today_madrid()
    goals = plan_svc.plan_goals(user.id, db, today) or (
        db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active.is_(True)).all()
    )
    races = sorted(g.target_race_date for g in goals if g.target_race_date and g.target_race_date >= today)

    try:
        start = _parse_date(input["start_date"]) if input.get("start_date") else today + timedelta(days=1)
        end = _parse_date(input["end_date"]) if input.get("end_date") else (races[-1] if races else start + timedelta(weeks=12))
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}
    bad = _check_date(start) or _check_date(end)
    if bad:
        return {"ok": False, "error": bad}
    if end < start:
        return {"ok": False, "error": "end_date debe ser >= start_date"}
    start = max(start, today)                    # no se planifica en el pasado
    if end < start:
        return {"ok": False, "error": "Todo el rango queda en el pasado"}

    existing = (
        db.query(Workout)
        .filter(Workout.user_id == user.id, Workout.date >= start, Workout.date <= end)
        .all()
    )
    weekday = input.get("weekday")
    if weekday is None:
        weekday = _freest_weekday(existing)
    else:
        try:
            weekday = int(weekday)
        except (TypeError, ValueError):
            weekday = -1
        if not 0 <= weekday <= 6:
            return {"ok": False, "error": "weekday debe ser 0 (lunes) .. 6 (domingo)"}

    skip_race_week = input.get("skip_race_week", True) is not False
    race_weeks = {r - timedelta(days=r.weekday()) for r in races}
    wtype = WorkoutType(type_str)
    structure = wod_structure.sanitize(input.get("structure"))
    ya = {(w.date, w.type) for w in existing}
    busy = {w.date for w in existing if w.type != WorkoutType.rest}

    new_sessions: list[Workout] = []
    skipped_races: set[date] = set()
    skipped_existing = 0
    d = start
    while d <= end:
        if d.weekday() == weekday:
            monday = d - timedelta(days=d.weekday())
            if skip_race_week and monday in race_weeks:
                skipped_races.add(monday)
            elif (d, wtype) in ya:
                skipped_existing += 1
            else:
                new_sessions.append(_new_session(user, db, d, wtype, input, structure))
                if len(new_sessions) > _MAX_RECURRING:
                    return {"ok": False, "error": f"Demasiadas sesiones (>{_MAX_RECURRING}). Acota el rango."}
        d += timedelta(days=1)

    if not new_sessions:
        why = "ya tienes esa sesión en todas esas semanas" if skipped_existing else "no hay semanas libres en ese rango"
        return {"ok": False, "error": f"No se añadió nada: {why}."}
    for w in new_sessions:
        db.add(w)
    db.commit()
    name = weekday_es(date(2026, 1, 5) + timedelta(days=weekday))
    first, last = new_sessions[0].date, new_sessions[-1].date
    return {
        "ok": True,
        "mutation": "add_weekly_session",
        "created": len(new_sessions),
        "weekday": name,
        "weekday_index": weekday,
        "first_date": first.isoformat(),
        "last_date": last.isoformat(),
        "skipped_race_weeks": len(skipped_races),
        "skipped_existing": skipped_existing,
        "days_with_other_sessions": sum(1 for w in new_sessions if w.date in busy),
        "summary": f"Añadidas {len(new_sessions)} sesiones '{type_str}' los {name} del {first.isoformat()} al {last.isoformat()}",
    }


def _tool_set_training_days_per_week(input: dict, user: User, db: Session) -> dict:
    try:
        days = int(input.get("days"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "days debe ser un número entre 1 y 7"}
    if not 1 <= days <= 7:
        return {"ok": False, "error": "days debe estar entre 1 y 7"}
    user.training_days_per_week = days
    db.add(user)
    db.commit()
    return {
        "ok": True,
        "mutation": "set_training_days_per_week",
        "days": days,
        "summary": f"Días de entreno por semana: {days}",
    }


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
    bad = _check_date(start) or _check_date(end)
    if bad:
        return {"ok": False, "error": bad}
    start = max(start, today_madrid())          # no se planifica en el pasado
    if end < start:
        return {"ok": False, "error": "Todo el rango queda en el pasado"}

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
    structure = wod_structure.sanitize(input.get("structure"))
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
        db.add(_new_session(user, db, d, wtype, input, structure))
        created += 1
    db.commit()
    return {
        "ok": True,
        "mutation": "add_recurring_workout",
        "created": created,
        "summary": f"Añadidos {created} workouts '{type_str}' entre {start.isoformat()} y {end.isoformat()}",
    }


def _tool_set_training_feedback(input: dict, user: User, db: Session) -> dict:
    from datetime import datetime, timezone
    area = (input.get("area") or "").strip().lower().replace(" ", "_")[:40]
    rating = input.get("rating")
    if not area or rating not in ("fuerte", "normal", "flojo"):
        return {"ok": False, "error": "area y rating ('fuerte'|'normal'|'flojo') son obligatorios"}
    fb = dict(user.station_feedback or {})
    entry = {"rating": rating, "updated": datetime.now(timezone.utc).date().isoformat()}
    note = (input.get("note") or "").strip()[:200]
    if note:
        entry["note"] = note
    fb[area] = entry
    # Máximo 30 áreas: si el modelo se inventa slugs sin parar, no crecemos sin límite.
    if len(fb) > 30:
        fb = dict(sorted(fb.items(), key=lambda kv: kv[1].get("updated", ""))[-30:])
    user.station_feedback = fb
    db.add(user)
    db.commit()
    return {
        "ok": True,
        "mutation": "set_training_feedback",
        "summary": f"Anotado: {area} = {rating}",
        "feedback": fb,
    }



_DISPATCH = {
    "list_workouts": _tool_list_workouts,
    "move_workout": _tool_move_workout,
    "update_workout": _tool_update_workout,
    "delete_workout": _tool_delete_workout,
    "add_workout": _tool_add_workout,
    "add_recurring_workout": _tool_add_recurring_workout,
    "add_weekly_session": _tool_add_weekly_session,
    "set_training_days_per_week": _tool_set_training_days_per_week,
    "mark_workout_status": _tool_mark_workout_status,
    "shift_plan": _tool_shift_plan,
    "adjust_week_load": _tool_adjust_week_load,
    "get_strava_summary": _tool_get_strava_summary,
    "compare_planned_vs_actual": _tool_compare_planned_vs_actual,
    "set_training_feedback": _tool_set_training_feedback,
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
