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
from app.services import current_plan as plan_svc, hyrox_knowledge, hyrox_wods, plan_overview as po, wod_duration, wod_structure
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
            "Lista los workouts del atleta en un rango de fechas (compacto: id, fecha, día, tipo, "
            "estado, distancia, duración y si lleva WOD). Úsala para encontrar ids. Para CONTAR "
            "sesiones por semana NO la uses: llama a plan_overview. `include_details` trae el WOD "
            "completo, solo para unas pocas sesiones (máx. 8)."
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
                "include_details": {
                    "type": "boolean",
                    "description": "Incluye instrucciones y WOD completo. Solo para pocas sesiones (máx. 8).",
                },
            },
        },
    },
    {
        "name": "plan_overview",
        "description": (
            "Resumen del plan POR SEMANAS (lunes-domingo) CONTADO POR EL SERVIDOR: sesiones por categoría "
            "(hyrox, run, fuerza...), total, días libres y las sesiones con su id. Úsala SIEMPRE para contar "
            "o comprobar semanas ('¿tengo 2 Hyrox cada semana?', '¿cuántas sesiones esta semana?'): NUNCA "
            "cuentes a mano. Sin fechas: de hoy a la última carrera."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto hoy."},
                "end_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto la última carrera."},
            },
        },
    },
    {
        "name": "adapt_weekly_plan",
        "description": (
            "Aplica una REGLA SEMANAL a todo el plan en UNA sola llamada: '2 sesiones de Hyrox a la semana', "
            "'quita el gym/la fuerza', 'sin gimnasio hasta la carrera'. Cuenta cada semana, quita lo que "
            "sobra (solo sesiones planificadas, nunca lo hecho) y añade las sesiones de Hyrox que falten con "
            "su WOD completo (pesos de su división) en los mejores días libres; no toca el pasado y, por "
            "defecto, deja intacta la semana de carrera. Úsala SIEMPRE que la petición afecte a varias "
            "semanas: NO llames a add_workout/delete_workout en bucle (se queda a medias). Devuelve el "
            "informe semana a semana (antes→después): confirma al atleta con ESOS números."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hyrox_per_week": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Sesiones de Hyrox por semana (hyrox_stations + hyrox_sim). Añade las que falten.",
                },
                "remove_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tipos de sesión a quitar. 'strength' o 'gym' = toda la fuerza (strength_upper/lower/full); también tipos concretos.",
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto hoy."},
                "end_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD. Por defecto la última carrera del plan. Para 'hasta el Hyrox', pon la fecha de ESE Hyrox.",
                },
                "skip_race_week": {
                    "type": "boolean",
                    "description": "Por defecto true: no se añaden sesiones en la semana de carrera (taper).",
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

# list_workouts devolvía el WOD entero (structure) de cada sesión: 41 sesiones eran
# decenas de miles de tokens y el modelo acababa hojeándolas. Por defecto va
# compacto; el detalle solo se pide para pocas sesiones.
_MAX_LIST = 120
_MAX_DETAIL = 8


def _brief_workout(w: Workout) -> dict[str, Any]:
    return {
        "id": w.id,
        "date": w.date.isoformat() if w.date else None,
        "weekday": weekday_es(w.date) if w.date else None,
        "type": w.type.value if hasattr(w.type, "value") else w.type,
        "status": w.status.value if hasattr(w.status, "value") else w.status,
        "distance_km": w.planned_distance_km,
        "duration_min": w.planned_duration_min,
        "has_wod": bool(w.structure),
        "modified_by": w.modified_by,
    }


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
        .order_by(Workout.date.asc(), Workout.id.asc())
        .all()
    )
    if input.get("include_details"):
        if len(workouts) > _MAX_DETAIL:
            return {"ok": False, "error": f"include_details solo para {_MAX_DETAIL} sesiones como máximo (hay {len(workouts)}). Acota el rango."}
        return {"ok": True, "count": len(workouts), "workouts": [_serialize_workout(w) for w in workouts]}
    truncated = len(workouts) > _MAX_LIST
    return {
        "ok": True,
        "count": len(workouts),
        "workouts": [_brief_workout(w) for w in workouts[:_MAX_LIST]],
        **({"truncated": True, "note": f"Solo las {_MAX_LIST} primeras; acota el rango o usa plan_overview."} if truncated else {}),
    }


def _check_read_date(d: date) -> str | None:
    """Para LEER vale el pasado reciente (la comprobación estricta de _check_date es para editar)."""
    today = today_madrid()
    delta = (d - today).days
    if delta < -400 or delta > _FUTURE_LIMIT_DAYS:
        return (
            f"La fecha {d.isoformat()} ({weekday_es(d)}) queda muy lejos de hoy ({weekday_es(today)} {today.isoformat()}). "
            "Búscala en `calendar` del contexto y repite con la fecha correcta."
        )
    return None


def _tool_plan_overview(input: dict, user: User, db: Session) -> dict:
    """Resumen por semanas CONTADO POR EL SERVIDOR (lun-dom). Aquí se cuenta; el modelo no cuenta a mano."""
    today = today_madrid()
    goals = plan_svc.plan_goals(user.id, db, today)
    races = sorted(g.target_race_date for g in goals if g.target_race_date and g.target_race_date >= today)
    try:
        start = _parse_date(input["start_date"]) if input.get("start_date") else today
        end = _parse_date(input["end_date"]) if input.get("end_date") else (races[-1] if races else start + timedelta(weeks=8))
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}
    bad = _check_read_date(start) or _check_read_date(end)
    if bad:
        return {"ok": False, "error": bad}
    if end < start:
        return {"ok": False, "error": "end_date debe ser >= start_date"}
    if (end - start).days > 366:
        return {"ok": False, "error": "Rango demasiado largo (máx. 1 año)"}
    weeks = po.overview(db, user.id, start, end)
    return {
        "ok": True,
        "weeks": weeks,
        "summary_lines": [po.week_line(w) for w in weeks],
        "summary": f"{len(weeks)} semanas, del {weeks[0]['week_start']} al {weeks[-1]['week_end']}",
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
        "workout": _brief_workout(w),
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


_STRENGTH_ALIASES = {"strength", "gym", "fuerza", "gimnasio"}
# Para elegir el mejor día libre: se evita juntar sesiones duras y el día antes de la tirada larga.
_HARD_TYPES = {
    "tempo", "intervals", "long_run", "hill_repeats", "fartlek", "hyrox_sim", "hyrox_stations",
    "strength_upper", "strength_lower", "strength_full", "race",
}
_ADAPT_WEEKDAY_SCORE = {0: 2, 1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 3}      # mejor entre semana (menos = mejor)


def _expand_remove_types(raw: Any) -> tuple[set[str], str | None]:
    if raw is None:
        return set(), None
    if not isinstance(raw, list):
        return set(), "remove_types debe ser una lista de tipos"
    out: set[str] = set()
    for t in raw:
        t = str(t).strip().lower()
        if t in _STRENGTH_ALIASES:
            out |= po.STRENGTH_TYPES
        elif t in ("race", "rest"):
            return set(), f"No se puede quitar el tipo '{t}'"
        elif t in VALID_TYPES:
            out.add(t)
        else:
            return set(), f"Tipo inválido en remove_types: {t}"
    return out, None


def _day_score(d: date, occupied: dict[date, list[str]], freed: set[date]) -> int:
    """Menor = mejor día para una sesión de Hyrox nueva."""
    score = _ADAPT_WEEKDAY_SCORE[d.weekday()]
    for nb in (d - timedelta(days=1), d + timedelta(days=1)):
        types = occupied.get(nb) or []
        if any(t in po.HYROX_TYPES for t in types):
            score += 6
        elif any(t in _HARD_TYPES for t in types):
            score += 4
        elif types:
            score += 1
    if "long_run" in (occupied.get(d + timedelta(days=1)) or []):
        score += 6                          # nunca el día antes de la tirada larga si hay otra opción
    if d in freed:
        score -= 5                          # el hueco que deja el gym es el sitio natural
    return score


def _hyrox_division_key(user: User, goals: list[Goal], d: date) -> str:
    hy = [g for g in goals if hyrox_knowledge.is_hyrox_goal(g)]
    goal = next((g for g in sorted(hy, key=lambda g: g.target_race_date or date.max)
                 if g.target_race_date and g.target_race_date >= d), None) or (hy[0] if hy else None)
    if goal:
        return hyrox_knowledge.division_key(goal, user)
    return "open_women" if (user.sex or "").upper() == "F" else "open_men"


def _tool_adapt_weekly_plan(input: dict, user: User, db: Session) -> dict:
    today = today_madrid()
    goals = plan_svc.plan_goals(user.id, db, today) or (
        db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active.is_(True)).all()
    )
    races = sorted(g.target_race_date for g in goals if g.target_race_date and g.target_race_date >= today)

    hpw = input.get("hyrox_per_week")
    if hpw is not None:
        try:
            hpw = None if isinstance(hpw, bool) else int(hpw)
        except (TypeError, ValueError):
            hpw = None
        if hpw is None or not 1 <= hpw <= 5:
            return {"ok": False, "error": "hyrox_per_week debe ser un número entre 1 y 5"}
    remove, err = _expand_remove_types(input.get("remove_types"))
    if err:
        return {"ok": False, "error": err}
    if hpw is None and not remove:
        return {"ok": False, "error": "Indica hyrox_per_week (cuántas sesiones de Hyrox por semana) y/o remove_types (qué quitar)."}

    # Sin fecha de fin: "Hyrox por semana" llega hasta el último HYROX del plan (no hasta una
    # media maratón posterior); quitar sesiones, hasta la última carrera.
    hyrox_races = sorted(g.target_race_date for g in goals
                         if hyrox_knowledge.is_hyrox_goal(g) and g.target_race_date and g.target_race_date >= today)
    default_end = (hyrox_races[-1] if hyrox_races else None) if hpw is not None else None
    default_end = default_end or (races[-1] if races else today + timedelta(weeks=12))
    try:
        start = _parse_date(input["start_date"]) if input.get("start_date") else today
        end = _parse_date(input["end_date"]) if input.get("end_date") else default_end
    except Exception as e:
        return {"ok": False, "error": f"Fecha inválida: {e}"}
    bad = _check_date(start) or _check_date(end)
    if bad:
        return {"ok": False, "error": bad}
    if end < start:
        return {"ok": False, "error": "end_date debe ser >= start_date"}
    lo = max(start, today)                      # el pasado no se toca
    if end < lo:
        return {"ok": False, "error": "Todo el rango queda en el pasado"}
    skip_race_week = input.get("skip_race_week", True) is not False

    first_monday, last_monday = po.week_monday(lo), po.week_monday(end)
    rows = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date >= first_monday - timedelta(days=1),
            Workout.date <= last_monday + timedelta(days=7),
        )
        .all()
    )
    live = [w for w in rows if w.status != WorkoutStatus.skipped and po.category_of(w.type) != "rest"]
    occupied: dict[date, list[str]] = {}
    for w in live:
        occupied.setdefault(w.date, []).append(po.type_value(w.type))

    # 1) Qué se quita: solo lo PLANIFICADO del rango (lo hecho es historia).
    removed = [w for w in live if w.status == WorkoutStatus.planned and po.type_value(w.type) in remove and lo <= w.date <= end]
    for w in removed:
        occupied[w.date].remove(po.type_value(w.type))
        if not occupied[w.date]:
            del occupied[w.date]

    race_days = set(races)
    race_weeks = {po.week_monday(r) for r in races}
    thr = ((user.adaptive_paces or {}).get("paces") or {}).get("threshold") if isinstance(user.adaptive_paces, dict) else None

    # 2) Semana a semana: cuántas sesiones de Hyrox hay y cuántas faltan.
    added: list[Workout] = []
    per_week: list[dict[str, Any]] = []
    no_room: list[str] = []
    race_skipped: list[str] = []
    variant = 0
    monday = first_monday
    while monday <= last_monday:
        sunday = monday + timedelta(days=6)
        in_week = [w for w in live if monday <= w.date <= sunday]
        rem_here = [w for w in removed if monday <= w.date <= sunday]
        kept = [w for w in in_week if w not in rem_here]
        new_here: list[Workout] = []
        deficit = False
        if hpw is not None:
            if skip_race_week and monday in race_weeks:
                race_skipped.append(monday.isoformat())
            else:
                hyrox_now = sum(1 for w in kept if po.category_of(w.type) == "hyrox")
                freed = {w.date for w in rem_here}
                for _ in range(max(0, hpw - hyrox_now)):
                    cands = [
                        monday + timedelta(days=i) for i in range(7)
                        if lo <= monday + timedelta(days=i) <= end
                        and (monday + timedelta(days=i)) not in race_days
                        and (monday + timedelta(days=i)) not in occupied
                    ]
                    if not cands:
                        deficit = True
                        no_room.append(monday.isoformat())
                        break
                    d = min(cands, key=lambda c: (_day_score(c, occupied, freed), c))
                    next_race = next((r for r in races if r >= d), None)
                    weeks_to_race = (po.week_monday(next_race) - po.week_monday(d)).days // 7 if next_race else None
                    session = hyrox_wods.build_session(
                        _hyrox_division_key(user, goals, d), variant=variant, weeks_to_race=weeks_to_race, threshold_pace=thr,
                    )
                    variant += 1
                    w = Workout(
                        user_id=user.id,
                        goal_id=_goal_id_for_date(user, db, d),
                        date=d,
                        day_of_week=d.weekday(),
                        type=WorkoutType(session["type"]),
                        status=WorkoutStatus.planned,
                        instructions=session["instructions"],
                        structure=wod_structure.sanitize(session["structure"]),
                        modified_by="user",
                    )
                    wod_duration.apply_to_workout(w)
                    occupied.setdefault(d, []).append(session["type"])
                    new_here.append(w)
        if rem_here or new_here or deficit:
            per_week.append({"monday": monday, "before": in_week, "removed": rem_here, "kept": kept, "added": new_here})
        added.extend(new_here)
        monday += timedelta(days=7)

    if not removed and not added:
        return {
            "ok": True,
            "added": 0,
            "removed": 0,
            "range": {"from": lo.isoformat(), "to": end.isoformat()},
            "weeks": [],
            "weeks_without_room": no_room,
            "weeks_race_skipped": race_skipped,
            "summary": "Ya estaba así: no hay nada que quitar ni añadir en ese rango"
                       + (f" (sin hueco en {', '.join(no_room)})" if no_room else ""),
        }

    for w in removed:
        db.delete(w)
    for w in added:
        db.add(w)
    db.flush()                                   # ids de las nuevas para el informe
    db.commit()

    def counts(ws: list[Workout]) -> dict[str, int]:
        c = {k: 0 for k in po.CATEGORIES}
        for w in ws:
            k = po.category_of(w.type)
            if k in c:
                c[k] += 1
        return c

    lines = []
    for wk in per_week:
        b, a = counts(wk["before"]), counts(wk["kept"] + wk["added"])
        cambios = [f"+{weekday_es(w.date)} {w.date.day} {po.type_value(w.type)} (id {w.id})" for w in wk["added"]]
        cambios += [f"-{weekday_es(w.date)} {w.date.day} {po.type_value(w.type)}" for w in wk["removed"]]
        lines.append(
            f"{wk['monday'].isoformat()} · hyrox {b['hyrox']}→{a['hyrox']} · fuerza {b['strength']}→{a['strength']} · run {a['run']}"
            + (f" · {', '.join(cambios)}" if cambios else "")
            + (" · SIN HUECO para completar" if wk["monday"].isoformat() in no_room else "")
        )
    partes = []
    if removed:
        partes.append(f"Quitadas {len(removed)} sesiones ({', '.join(sorted({po.type_value(w.type) for w in removed}))})")
    if added:
        partes.append(f"añadidas {len(added)} de Hyrox")
    resumen = " y ".join(partes) + f": del {lo.isoformat()} al {end.isoformat()}"
    if hpw is not None:
        resumen += f", cada semana con {hpw} Hyrox por semana"
        if race_skipped:
            resumen += " (semana de carrera sin tocar)"
    if no_room:
        resumen += f". SIN HUECO en las semanas {', '.join(no_room)}: todos sus días tienen sesión"
    return {
        "ok": True,
        "mutation": "adapt_weekly_plan",
        "added": len(added),
        "removed": len(removed),
        "range": {"from": lo.isoformat(), "to": end.isoformat()},
        "weeks": lines,
        "weeks_without_room": no_room,
        "weeks_race_skipped": race_skipped,
        "summary": resumen,
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
    "adapt_weekly_plan": _tool_adapt_weekly_plan,
    "plan_overview": _tool_plan_overview,
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
