"""Agente Goggins — chat conversacional con persona David Goggins en español.

Combina:
- Persona Goggins (duro-motivador, sin insultos personales ni palabrotas)
- Contexto auto-inyectado del atleta (perfil, plan actual, marcas, últimas
  actividades, último análisis IA) para que las respuestas sean específicas
- Streaming en tiempo real
- Memoria persistente vía ChatMessage
"""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.goal import Goal
from app.models.workout import Workout, WorkoutStatus
from app.models.personal_record import PersonalRecord
from app.models.strava_activity import StravaActivity
from app.models.ai_insight import AiInsight
from app.models.chat_message import ChatMessage
from app.services import ai_client, agent_tools, current_plan, hyrox_knowledge, plan_overview, record_labels, wod_structure
from app.services import strava as strava_service
from app.services.clock import now_madrid, to_madrid, today_madrid, weekday_es

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Eres David Goggins, ex-Navy SEAL, ultramaratoniano y mentalidad de hierro, hablando directamente con tu atleta en ESPAÑOL.

PERSONA:
- Duro, directo, sin rodeos. Cero excusas aceptadas, cero compasión barata.
- Tono militar, intenso, motivador. Habla en segunda persona ("tú", "tu cuerpo", "tu mente").
- NO usas palabrotas ni insultos personales. La intensidad viene del contenido y la honestidad, no de las groserías.
- Frases cortas, contundentes, ritmo de impacto. Mezclas frases motivacionales icónicas tuyas: "Stay hard", "Who's gonna carry the boats?", "Take souls", "The 40% rule", "Callus the mind".
- Asumes que el atleta puede más de lo que cree. Tu trabajo: empujarlo a su próximo nivel.

REGLAS DE COACHING:
- SIEMPRE basas tus consejos en los DATOS REALES del atleta que te paso en el contexto. Cita números concretos: km, ritmos, FC, fechas, marcas. Si no hay datos, dilo: "No tienes datos de X. Mide. Ahora."
- Las cifras de actividad (km, días sin correr, sesiones hechas) salen SOLO del contexto de AHORA (`last_14_days`). NUNCA repitas cifras de mensajes anteriores del historial: pueden haber quedado viejas.
- Si `strava_data` dice "NO actualizado" o "sin Strava", di que te faltan datos recientes; no afirmes que no ha entrenado.
- Cuando el atleta se queje, valida 1 segundo y luego empuja. Nunca te quedes en la queja.
- Si pregunta sobre técnica, fisiología o periodización, das respuesta correcta y específica — eres entrenador real, no solo motivación vacía.
- Si pregunta algo fuera del entrenamiento (vida, mente, hábitos), respondes con la mentalidad Goggins: disciplina sobre motivación, accountability mirror, callus the mind.

PROACTIVIDAD (analiza carga real vs plan):
- COMPARA siempre lo realmente hecho (Strava, `last_14_days`) con lo planificado. Si lo ves desfasado, dilo y propón un ajuste concreto con una tool.
- Si el atleta lleva varias sesiones por debajo del plan (volumen bajo, FC alta, saltos), sugiere BAJAR la carga de la próxima semana (`adjust_week_load` con factor < 1, p.ej. 0.85). Si va sobrado (cumple y con FC controlada), sugiere SUBIR (factor 1.1-1.15).
- Cuando el atleta pregunte "¿puedo mejorar?", "¿cómo voy?", "¿voy bien?" → NO respondas con motivación vacía. Llama a `get_strava_summary` y/o `compare_planned_vs_actual`, lee los números y responde con datos: qué está bien, qué falla, y la acción concreta.
- Cuando el atleta diga "no puedo entrenar esta semana / estos días", usa `shift_plan` para desplazar todo el plan futuro, no muevas workouts uno a uno.
- Cuando diga "me veo flojo/cansado" o "me veo fuerte/sobrado", usa `adjust_week_load` sobre la semana en cuestión.
- RESPETA los cambios manuales del atleta: en el contexto tienes `user_edited_workouts` (workouts con `modified_by='user'`). Esos los tocó él a mano — no los machaques sin avisar. Si tu ajuste los afecta, menciónalo y respeta su intención salvo que sea claramente contraproducente (y entonces explícale por qué).

LONGITUD Y FORMATO (CRÍTICO):
- BREVE por defecto: 2-4 frases. NUNCA más de 6 frases salvo que la pregunta exija explicación técnica detallada.
- Saludos ("hola", "qué tal") → MÁX 2 frases. Una de impacto + una pregunta directa para arrancar la sesión.
- Frases cortas. Punto. Sin párrafos largos.
- Usa **negrita** solo para 2-3 datos clave (km, ritmo, fecha). No uses negrita en frases enteras ni para énfasis emocional.
- Cierres motivacionales ("Stay hard", "No excuses") solo en 1 de cada 3 respuestas. No los uses en cada mensaje.
- NO uses listas con guiones salvo que enumeres ≥3 ítems concretos (ej. workouts, marcas).

NO HAGAS:
- No te disculpes nunca por ser duro.
- No inventes datos. Si no están en el contexto, dilo.
- No salgas del personaje Goggins.
- No uses emojis (excepto 💀 ⚡ ocasionalmente para impacto).

HERRAMIENTAS DISPONIBLES (tool use):
Tienes acceso a herramientas para EDITAR el plan de entrenamiento del atleta. Úsalas cuando el atleta te pida cambiar algo:
- `move_workout(workout_id, new_date)` — para reprogramar un entreno a otra fecha.
- `update_workout(workout_id, ...)` — para cambiar tipo, distancia, duración, zona o instrucciones.
- `delete_workout(workout_id)` — para eliminar un entreno.
- `add_workout(date, type, ...)` — para añadir UN entreno nuevo en una fecha concreta.
- `add_recurring_workout(type, start_date, end_date, days_of_week?, ...)` — para añadir el MISMO entreno repetido en muchas fechas DE UNA VEZ. Úsalo SIEMPRE para peticiones recurrentes ("movilidad todos los días", "fuerza tren superior los lunes y jueves", "core 3x/semana"). NO llames a add_workout en bucle: usa esta. Si no pasas days_of_week, lo crea todos los días del rango. Tipos útiles: `mobility` (movilidad), `strength_upper` (tren superior), `strength_lower` (tren inferior), `strength_full`.
- `add_weekly_session(type, weekday?, start_date?, end_date?, structure?, ...)` — UNA sesión más por semana durante todo el plan (o el tramo que indiques). Si el atleta no dice el día, ELIGE ella el día libre. Úsala para "un día más de entreno a la semana", "añade una sesión de X cada semana". Ya se salta los días pasados y las semanas de carrera, y asocia cada sesión al objetivo de su fecha.
- `plan_overview(start_date?, end_date?)` — resumen del plan POR SEMANAS (lun-dom) CONTADO POR EL SERVIDOR: sesiones de hyrox, running, fuerza..., días libres y los ids. Úsala SIEMPRE para contar o comprobar semanas.
- `adapt_weekly_plan(hyrox_per_week?, remove_types?, start_date?, end_date?)` — aplica una REGLA SEMANAL a todo el plan en UNA llamada ("2 sesiones de Hyrox a la semana", "quita el gym/la fuerza"): cuenta cada semana, quita lo que sobra y añade las sesiones de Hyrox que falten con su WOD completo y los pesos de su división. Para peticiones sobre VARIAS semanas es la ÚNICA forma fiable.
- `set_training_days_per_week(days)` — guarda cuántos días a la semana entrena el atleta, para que los planes futuros lo respeten. Llámala TAMBIÉN cuando pida entrenar un día más o menos de forma permanente.
- `mark_workout_status(workout_id, status)` — para marcar como completado o saltado.
- `list_workouts(start_date, end_date)` — si necesitas buscar workouts fuera del contexto inicial.
- `shift_plan(days|weeks, from_date)` — desplaza TODOS los workouts futuros del plan N días o semanas. Úsalo para "no puedo entrenar esta semana / estos días": muévelo todo de golpe en vez de uno a uno.
- `adjust_week_load(week_start_date, factor)` — escala distancia y duración de los workouts de esa semana por un factor (0.8 = bajar 20%, 1.15 = subir 15%). Úsalo para "me veo flojo" (baja) o "me veo fuerte/sobrado" (sube).
- `get_strava_summary(days)` — resumen agregado de lo realmente hecho en Strava (km, tiempo, sesiones, FC media por disciplina) en el periodo. Úsalo para responder con datos a "¿cómo voy?", "¿puedo mejorar?".
- `compare_planned_vs_actual(start_date, end_date)` — compara lo planificado con lo realmente hecho en el rango. Úsalo para detectar desfases y justificar subir/bajar la carga.

FECHAS (CRÍTICO — aquí es donde más errores se cometen):
- El campo `calendar` del contexto lista los próximos 21 días con su día de la semana y a qué semana pertenecen ("esta semana", "semana que viene"). Para convertir "el viernes" o "el jueves de la semana que viene" en fecha, BÚSCALO ahí: NUNCA calcules fechas de cabeza. `this_week` y `next_week` dan lunes y domingo de cada una.
- Cada mensaje del atleta en el historial lleva `[Enviado el ... a las ...]`: su "hoy", "mañana" o "esta semana" se refieren a ESA fecha, no a la de ahora. No copies esos corchetes en tus respuestas.
- La fecha de HOY está en `today` del contexto (date, weekday, tomorrow). Es LA ÚNICA verdad: NUNCA deduzcas qué día es por tu cuenta ni por el historial.
- "el entreno de hoy" = el workout de `upcoming_workouts` con `is_today: true` (o `date == today.date`). "mañana" = `today.tomorrow`. Si el atleta dice un día de la semana ("el del jueves"), busca el `weekday` que coincida MÁS CERCANO en el futuro.
- Las referencias relativas de mensajes ANTIGUOS del historial ("hoy", "mañana") se referían a SU día, no al actual: no las arrastres.
- Antes de mover/editar, di en tu respuesta la fecha resuelta con su día ("te muevo el de HOY, sábado 4, al lunes 6") para que el atleta detecte al instante si te equivocas.

UN DÍA MÁS (O MENOS) A LA SEMANA — receta:
1. Mira en `calendar` y `upcoming_workouts` qué días de la semana están libres.
2. Llama a `add_weekly_session` con el tipo que más le convenga según su objetivo y sus puntos flojos (si es Hyrox o fuerza, con su `structure`). NO llames a add_workout en bucle.
3. Llama a `set_training_days_per_week` con el nuevo total de días.
4. Confirma en 2 frases: qué día de la semana, desde cuándo hasta cuándo y cuántas sesiones se crearon (lo dice el resultado de la tool).

REGLAS PARA VARIAS SEMANAS (aquí es donde más se falla):
- Si la petición afecta a VARIAS semanas ("2 Hyrox a la semana", "sin gym hasta la carrera", "quita la fuerza"): UNA sola llamada a `adapt_weekly_plan`, con `end_date` = la fecha de la carrera de la que habla el atleta. NUNCA add_workout/delete_workout en bucle: la respuesta se corta, se queda a medias y el atleta se desespera.
- NUNCA cuentes sesiones por semana de cabeza: usa `plan_weeks` del contexto o `plan_overview`. El sábado 12 y el jueves 17 son de semanas distintas.
- Cuando la tool termine, confirma con SUS números (el informe semana a semana). Si devuelve `weeks_without_room`, díselo.
- Si el atleta te repite una petición es que NO se aplicó bien: mira `plan_weeks` y el "Registro del sistema" del historial (lo que de verdad se ejecutó) antes de contestar. NUNCA le digas "ya estaba hecho" sin comprobarlo con `plan_overview`.
- NO narres paso a paso antes de llamar a las tools ("ahora elimino...", "empiezo con..."): llama directamente y resume al final en pocas frases.
- En el historial, el "[Registro del sistema ...]" de tus mensajes lista lo que SE EJECUTÓ de verdad en ese turno: fíate de él, no de lo que dijiste. No lo copies en tus respuestas.

REGLAS DE TOOL USE:
- Si el atleta pide un cambio, tu PRIMERA acción es llamar a la tool (como mucho una frase corta antes). NUNCA escribas "hecho", "listo" o "metido" hasta tener el resultado con ok:true.
- Los días de carrera (type `race`) no se mueven ni se borran salvo que el atleta lo pida expresamente.
- Al añadir workouts NO pases `goal_id` salvo que lo tengas en `active_goals`: si lo omites, se asocia solo al objetivo de esa fecha.
- Los workout_ids están en el contexto que te paso (campo `id` de cada workout en `upcoming_workouts`). Úsalos.
- Si el atleta pide algo ambiguo ("muéveme el de mañana"), elige el más probable basándote en el contexto y CONFIRMA en tu respuesta qué hiciste.
- Después de ejecutar una tool, responde como Goggins: confirma el cambio en 1-2 frases con tono duro-motivador. NO listes datos crudos del JSON, escribe como humano.
- Si la tool falla, díselo al atleta sin rodeos: "Eso no funcionó. Intenta de nuevo o dime qué entreno exacto."
- NUNCA inventes workout_ids. Si no los tienes, llama a `list_workouts` primero.
- CRÍTICO: NUNCA digas que has cambiado, movido, ajustado, añadido o borrado algo del plan SIN haber llamado de verdad a la tool correspondiente en este mismo turno. El plan SOLO cambia si ejecutas la tool. Está prohibido prometer o describir un cambio sin ejecutarlo. Primero ejecuta la tool, y solo después confirma el cambio. Si solo estás recomendando (no ejecutando todavía), dilo claramente: "Si quieres lo ajusto ahora, dímelo."
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


def _build_athlete_context(user: User, db: Session) -> dict[str, Any]:
    """Compila el estado actual del atleta para inyectar como contexto."""
    today = today_madrid()

    # Perfil
    profile = {
        "name": user.name,
        "age": user.age,
        "sex": user.sex,
        "weight_kg": user.weight_kg,
        "height_cm": user.height_cm,
        "experience_level": user.experience_level,
        "years_training": user.years_training,
        "training_days_per_week": user.training_days_per_week,
        "max_hr": user.max_heart_rate,
        "resting_hr": user.resting_heart_rate,
        "vam_ms": user.vam_ms,
        # Ritmos adaptativos (VDOT) calculados de marcas/actividades reales.
        # Son la referencia de ritmos MÁS fiable: úsalos antes que la VAM.
        "adaptive_paces": _adaptive_paces_ctx(user),
        # Dónde dice el atleta que va fuerte/flojo (escrito vía set_training_feedback).
        "training_feedback": user.station_feedback or None,
    }

    # Objetivos activos
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active == True).all()  # noqa
    goals_list = []
    for g in goals:
        days_to = None
        if g.target_race_date:
            days_to = (g.target_race_date - today).days
        goals_list.append({
            "id": g.id,
            "type": g.type.value if hasattr(g.type, "value") else g.type,
            "sport": g.sport,
            "description": g.description,
            "race_distance_km": g.target_race_distance_km,
            "race_date": g.target_race_date.isoformat() if g.target_race_date else None,
            "days_until_race": days_to,
            "target_time": _format_seconds(g.target_time_seconds),
            "weekly_km_target": g.target_weekly_km,
        })

    # Marcas
    records = db.query(PersonalRecord).filter(PersonalRecord.user_id == user.id).all()
    records_list = []
    for r in records:
        entry = {"category": record_labels.label_for(r.category)}
        if r.value_seconds:
            entry["time"] = _format_seconds(r.value_seconds)
        if r.value_numeric is not None:
            entry["value"] = r.value_numeric
            entry["unit"] = r.unit
        if r.date_achieved:
            entry["date"] = r.date_achieved.isoformat()
        if r.notes:
            entry["notes"] = r.notes
        records_list.append(entry)

    # Últimos 14 días de actividad
    since = datetime.now(timezone.utc) - timedelta(days=14)
    activities = (
        db.query(StravaActivity)
        .filter(StravaActivity.user_id == user.id)
        .order_by(StravaActivity.start_date.desc())
        .limit(50)
        .all()
    )
    recent_acts = []
    last_14d_km = 0.0
    for a in activities:
        if not a.start_date:
            continue
        try:
            dt = a.start_date if isinstance(a.start_date, datetime) else datetime.fromisoformat(str(a.start_date).replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < since:
            continue
        km = (a.distance_m or 0) / 1000
        last_14d_km += km
        recent_acts.append({
            "date": dt.strftime("%Y-%m-%d"),
            "type": a.type,
            "name": a.name,
            "km": round(km, 2),
            "min": round((a.moving_time_s or 0) / 60, 1),
            "avg_hr": round(a.average_heartrate) if a.average_heartrate else None,
        })

    # Plan actual — próximos 14 días
    upcoming = (
        db.query(Workout)
        .filter(
            Workout.user_id == user.id,
            Workout.date >= today,
            Workout.date <= today + timedelta(days=14),
        )
        .order_by(Workout.date.asc())
        .limit(80)
        .all()
    )
    upcoming_list = [
        {
            "id": w.id,
            "date": w.date.isoformat(),
            "weekday": weekday_es(w.date),
            "is_today": w.date == today,
            "type": w.type.value if hasattr(w.type, "value") else w.type,
            "distance_km": w.planned_distance_km,
            "duration_min": w.planned_duration_min,
            "hr_zone": w.planned_heart_rate_zone,
            "instructions": w.instructions,
            "status": w.status.value if hasattr(w.status, "value") else w.status,
            "modified_by": w.modified_by,
            "updated_at": w.updated_at.isoformat() if w.updated_at else None,
        }
        for w in upcoming
    ]

    # Workouts editados manualmente por el atleta (modified_by='user') en los
    # próximos 14 días → Goggins debe respetar/tener en cuenta estos cambios.
    user_edited = [
        {
            "id": w["id"],
            "date": w["date"],
            "type": w["type"],
            "distance_km": w["distance_km"],
            "duration_min": w["duration_min"],
            "updated_at": w["updated_at"],
        }
        for w in upcoming_list
        if w.get("modified_by") == "user"
    ]

    # Último análisis IA cacheado
    insight = (
        db.query(AiInsight)
        .filter(AiInsight.user_id == user.id, AiInsight.kind == "fitness_state")
        .order_by(AiInsight.created_at.desc())
        .first()
    )
    fitness_snapshot = None
    if insight and insight.data:
        try:
            fitness_snapshot = json.loads(insight.data) if isinstance(insight.data, str) else insight.data
        except Exception:
            fitness_snapshot = None

    this_monday = today - timedelta(days=today.weekday())
    return {
        # Fecha REAL del atleta (hora española). "hoy"/"mañana" se resuelven
        # SIEMPRE contra esto, nunca contra el conocimiento del modelo.
        "today": {
            "date": today.isoformat(),
            "weekday": weekday_es(today),
            "tomorrow": (today + timedelta(days=1)).isoformat(),
            "tomorrow_weekday": weekday_es(today + timedelta(days=1)),
        },
        "this_week": {"monday": this_monday.isoformat(), "sunday": (this_monday + timedelta(days=6)).isoformat()},
        "next_week": {
            "monday": (this_monday + timedelta(days=7)).isoformat(),
            "sunday": (this_monday + timedelta(days=13)).isoformat(),
        },
        # Calendario ya calculado: el modelo NO debe deducir fechas de cabeza.
        "calendar": _calendar(today),
        # El plan entero por semanas, CONTADO por el servidor: el modelo no cuenta a mano.
        "plan_weeks": _plan_weeks(user, db, today),
        "profile": profile,
        "active_goals": goals_list,
        "personal_records": records_list,
        "last_14_days": {
            "total_km": round(last_14d_km, 1),
            "activities": recent_acts,
        },
        "upcoming_workouts": upcoming_list,
        "user_edited_workouts": user_edited,
        "fitness_snapshot": fitness_snapshot,
    }


def _plan_weeks(user: User, db: Session, today: date) -> list[str]:
    """Una línea por semana (desde la de HOY hasta la última carrera del plan), contada por el servidor."""
    races = [
        g.target_race_date for g in current_plan.plan_goals(user.id, db, today)
        if g.target_race_date and g.target_race_date >= today
    ]
    end = max(races) if races else today + timedelta(weeks=8)
    return [plan_overview.week_line(w) for w in plan_overview.overview(db, user.id, today, end)[:30]]


def _calendar(today: date, days: int = 21) -> list[str]:
    """Los próximos `days` días, uno por línea: fecha, día de la semana y a qué semana pertenece."""
    this_monday = today - timedelta(days=today.weekday())
    out = []
    for i in range(days):
        d = today + timedelta(days=i)
        n = (d - timedelta(days=d.weekday()) - this_monday).days // 7
        semana = "esta semana" if n == 0 else "semana que viene" if n == 1 else f"dentro de {n} semanas"
        marca = " · HOY" if i == 0 else " · MAÑANA" if i == 1 else ""
        out.append(f"{d.isoformat()} {weekday_es(d)}{marca} · {semana}")
    return out


def _stamp(dt: datetime, *, now: bool = False) -> str:
    """Etiqueta de fecha/hora (España) para anteponer a un mensaje del atleta."""
    local = to_madrid(dt)
    cuando = f"{weekday_es(local.date())} {local:%d/%m/%Y} a las {local:%H:%M}"
    return f"[Enviado ahora: {cuando}]" if now else f"[Enviado el {cuando}]"


def _load_history(user_id: int, db: Session, limit: int = 20) -> list[dict[str, str]]:
    """Carga los últimos N mensajes del historial en orden cronológico.

    Cada mensaje del atleta lleva la fecha en que lo envió: sus "hoy"/"mañana"
    se anclan a ESE día y no se arrastran como si fueran el actual.
    """
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    out = []
    for r in rows:
        content = r.content
        if r.role == "user" and r.created_at:
            content = f"{_stamp(r.created_at)}\n{content}"
        elif r.role == "assistant" and r.tool_calls:
            content += _registry(r.tool_calls)
        out.append({"role": r.role, "content": content})
    return out


# ── Registro de lo que SE EJECUTÓ ────────────────────────────────────────────────
# El historial solo guardaba el TEXTO de cada turno. Sin saber qué tools se ejecutaron
# de verdad, en el turno siguiente el modelo se fiaba de lo que él mismo había dicho
# ("fuerza eliminada, ahora creo los Hyrox...") y daba por hecho lo que no se hizo.

_MAX_LOGGED_ACTIONS = 60


def _registry(raw: str) -> str:
    """Texto para anteponer a un mensaje del asistente en el historial: qué tools hicieron algo de verdad."""
    try:
        actions = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    if not isinstance(actions, list):
        return ""
    grupos: dict[tuple[str, bool], list[str]] = {}
    interrumpido = None
    for a in actions:
        if not isinstance(a, dict):
            continue
        if a.get("interrupted"):
            interrumpido = a["interrupted"]
            continue
        name, ok = a.get("tool"), bool(a.get("ok"))
        # Las consultas que salieron bien no aportan: solo lo que cambia datos y todo fallo.
        if not name or (ok and name not in MUTATING_TOOLS):
            continue
        grupos.setdefault((name, ok), []).append(str(a.get("summary") or "")[:90])
    if not grupos and not interrumpido:
        return ""
    partes = []
    for (name, ok), resumenes in grupos.items():
        ultimo = resumenes[-1]
        partes.append(f"{'✓' if ok else '✗'} {name} ×{len(resumenes)}" + (f" ({ultimo})" if ultimo else ""))
    if interrumpido:
        partes.append("TURNO INTERRUMPIDO: no llegó a terminar la tarea")
    texto = " · ".join(partes)[:700]
    return f"\n\n[Registro del sistema — lo que SE EJECUTÓ de verdad en ese turno (fíate de esto, no del texto): {texto}]"


_ECHO_RES = [
    re.compile(r"^\s*\[Enviado[^\]]*\]\s*", re.I),                              # "[Enviado ahora: ...]" al empezar
    re.compile(r"\s*\[Registro del sistema[^\]]*\]\s*$", re.I),                  # el registro al final
]


def _clean_reply(text: str) -> str:
    """Quita lo que el sistema le inyecta al modelo (etiqueta de fecha, registro de acciones) si lo imita."""
    for rx in _ECHO_RES:
        text = rx.sub("", text)
    return text.strip()


def _actions_digest(actions: list[dict[str, Any]]) -> str:
    """'3 × add_workout, 8 × delete_workout' (solo lo que cambió datos con éxito)."""
    cuenta: dict[str, int] = {}
    for a in actions:
        if a.get("ok") and a.get("tool") in MUTATING_TOOLS:
            cuenta[a["tool"]] = cuenta.get(a["tool"], 0) + 1
    if not cuenta:
        return "no llegué a ejecutar ningún cambio"
    return "ya hecho: " + ", ".join(f"{n} × {t}" for t, n in cuenta.items())


def _interruption_notice(kind: str, actions: list[dict[str, Any]]) -> str:
    causa = "mi respuesta se cortó por límite de longitud" if kind == "length" else "me quedé sin margen de pasos"
    return (
        f"Aviso: {causa} antes de terminar; {_actions_digest(actions)}. "
        "Escribe «continúa» y sigo donde me quedé."
    )


# ── Honestidad al editar el plan ─────────────────────────────────────────────
# El modelo a veces escribe "hecho, te lo he metido" SIN haber llamado a la tool,
# y el plan no cambia. Se detecta (petición de cambio + afirmación + ninguna
# tool de edición con éxito) y se le obliga a ejecutarla o a corregirse.

_PART = r"(?:met|a[ñn]adid|agregad|movid|cambiad|ajustad|borrad|eliminad|cread|programad|actualizad|desplazad|incluid|sustituid|reprogramad|marcad)"
_CLAIM_RES = [
    re.compile(rf"\b(?:he|hemos|ya|queda|quedan|te\s+(?:lo|la|los|las))\s+(?:\w+\s+){{0,2}}{_PART}(?:ido|[oa]s?)\b", re.I),
    re.compile(rf"^\W*{_PART}(?:ido|[oa]s?)\b", re.I),
    re.compile(rf"\b{_PART}(?:ido|[oa]s?)\s*[:.!]", re.I),
    re.compile(r"^\W*(?:hecho|listo|perfecto|ok)\b\W*$", re.I),
    re.compile(r"\b(?:lo|la|los|las|te\s+lo|te\s+la)\s+(?:meto|pongo|a[ñn]ado|muevo|cambio|ajusto|borro|elimino|creo|programo)\b", re.I),
    re.compile(r"\bya\s+est[aá]\s+(?:en|metid|añadid|hecho)", re.I),
]
_HEDGE_RE = re.compile(r"\b(no|nunca|tampoco|todav[ií]a|a[uú]n|sin|si\s+quieres|si\s+prefieres|d[ií]melo)\b|¿", re.I)
_ASKS_RE = re.compile(
    r"\b(?:m[eé]te(?:me|lo|la|los|las)?|a[ñn][aá]de(?:me|lo|la)?|agrega(?:me|lo|la)?|pon(?:me|le|lo|la|los|las)?|"
    r"quita(?:me|lo|la|los|las)?|borra(?:me|lo|la|los|las)?|elimina(?:me|lo|la)?|mu[eé]ve(?:me|lo|la)?|"
    r"cambia(?:me|lo|la)?|ajusta(?:me|lo|la)?|desplaza|programa(?:me)?|apunta(?:me)?|sustituye|reemplaza)\b"
    r"|\b(?:sube|baja|reduce|aumenta)(?:me)?\s+(?:la|el|los|las)\s+(?:carga|volumen|intensidad|km|kil[oó]metros|semana)"
    r"|\b(?:quiero|necesito)\s+(?:entrenar|un|otro|m[aá]s)\b"
    r"|un d[ií]a m[aá]s|otro d[ií]a de entreno|m[aá]s d[ií]as de entreno"
    # seguimientos de una petición anterior: "continúa", "hazlo", "¿los has añadido ya?"
    r"|\b(?:contin[uú]a|sigue|hazlo|apl[ií]ca(?:lo|la)?)\b"
    r"|\b(?:lo|la|los|las)\s+has\s+(?:a[ñn]adido|metido|puesto|hecho|cambiado|quitado|borrado|movido|ajustado|aplicado)\b",
    re.I,
)
# Una pregunta explícita o un ofrecimiento ("si quieres lo hago") no es una promesa incumplida.
_QUESTION_OR_OFFER_RE = re.compile(r"¿|\b(?:d[ií]melo|dime\s+si|si\s+quieres|si\s+prefieres|av[ií]same)\b", re.I)


_COMMIT_RES = [
    re.compile(r"\b(?:lo|la|los|las|te\s+(?:lo|la|los|las))\s+(?:arreglo|meto|pongo|a[ñn]ado|muevo|cambio|ajusto|borro|elimino|creo|programo|monto|apa[ñn]o|soluciono|hago|reconstruyo)\b", re.I),
    re.compile(r"\bvoy\s+a\s+(?:meter|a[ñn]adir|poner|mover|cambiar|ajustar|borrar|eliminar|crear|arreglar|montar|reconstruir|aplicar)", re.I),
    re.compile(r"\b(?:ahora|ya)\s+(?:mismo\s+)?(?:lo\s+|la\s+|los\s+|las\s+)?(?:arreglo|meto|a[ñn]ado|aplico|creo|monto|reconstruyo)\b", re.I),
]


def commits_without_doing(text: str) -> bool:
    """True si el texto PROMETE hacer el cambio ("lo arreglo ahora", "voy a añadir…"), sin negaciones ni ofrecimientos."""
    for sentence in re.split(r"(?<=[.!?\n:])\s+", text or ""):
        sentence = sentence.strip()
        if not sentence or _HEDGE_RE.search(sentence):
            continue
        if any(rx.search(sentence) for rx in _COMMIT_RES):
            return True
    return False


def claims_plan_change(text: str) -> bool:
    """True si el texto AFIRMA haber cambiado el plan (ignora negaciones y ofrecimientos)."""
    for sentence in re.split(r"(?<=[.!?\n])\s+", text or ""):
        sentence = sentence.strip()
        if not sentence or _HEDGE_RE.search(sentence):
            continue
        if any(rx.search(sentence) for rx in _CLAIM_RES):
            return True
    return False


def asks_plan_change(text: str) -> bool:
    """True si el atleta está PIDIENDO un cambio del plan (verbos de petición)."""
    return bool(_ASKS_RE.search(text or ""))


# Tools que modifican datos: solo un resultado ok de una de estas cuenta como "cambio hecho".
MUTATING_TOOLS = {
    "move_workout", "update_workout", "delete_workout", "add_workout", "add_recurring_workout",
    "add_weekly_session", "adapt_weekly_plan", "mark_workout_status", "shift_plan", "adjust_week_load",
    "set_training_days_per_week", "set_training_feedback",
}

_GUARD_MESSAGE = (
    "[SISTEMA] Tu respuesta afirma que has modificado el plan, pero en este turno NO has ejecutado con éxito "
    "ninguna herramienta de edición, así que el plan NO ha cambiado. Ejecuta AHORA la herramienta que corresponda "
    "y, cuando tengas su resultado, confirma. Si en realidad no tocaba cambiar nada, corrige tu respuesta sin "
    "afirmar cambios."
)
_PROMISE_MESSAGE = (
    "[SISTEMA] El atleta te ha pedido un cambio en el plan y has terminado el turno sin ejecutar ninguna herramienta "
    "de edición ni hacerle una pregunta, así que el plan NO ha cambiado. Ejecuta AHORA la herramienta que corresponda "
    "(para una regla de varias semanas, `adapt_weekly_plan`; mira `calendar` para las fechas). Si te falta un dato "
    "imprescindible, PREGÚNTALO con una pregunta explícita (¿...?). No prometas cambios: o los ejecutas o preguntas."
)
_NO_CHANGE_NOTICE = (
    "\n\nAviso: No he ejecutado ningún cambio en tu plan. Pídemelo otra vez con el día exacto y lo hago."
)


MAX_TOOL_ITERATIONS = 20
# Una sola llamada a una tool con el WOD completo ocupa ~1.000 tokens: 2.500 no daba ni
# para tres, y lo que se cortaba se perdía en silencio.
CHAT_MAX_TOKENS = 8000
MAX_TRUNCATIONS = 2

_TRUNCATED_MESSAGE = (
    "[SISTEMA] Tu respuesta se cortó por longitud ANTES de terminar: si estabas llamando a una herramienta, "
    "esa llamada NO se ejecutó. No repitas lo que ya has dicho. Hazlo en pasos más pequeños: para cambios en "
    "varias semanas usa `adapt_weekly_plan` o `add_weekly_session` (una sola llamada corta), y si es una sesión "
    "suelta, una por llamada y sin texto de relleno."
)


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    """Convierte un ContentBlock del SDK de Anthropic a dict para append a messages."""
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if isinstance(block, dict):
        return block
    # Fallback genérico
    return {"type": getattr(block, "type", "text"), "text": getattr(block, "text", str(block))}


def chat_stream(
    user: User,
    db: Session,
    user_message: str,
) -> Iterator[dict[str, Any]]:
    """Chat agéntico con tool use. Stream de eventos:

    - {phase: context|thinking}
    - {phase: chunk, text: "..."}              — texto del asistente
    - {phase: tool_use, name, input}           — Claude está llamando una tool
    - {phase: tool_result, name, ok, summary}  — resultado de ejecutar la tool
    - {phase: mutation, ...}                   — mutación efectiva del plan
    - {phase: done, content, mutations}
    - {phase: error, detail}
    """
    yield {"phase": "context", "message": "Cargando tu estado actual"}
    strava_data = strava_service.refresh_recent(user, db)   # antes de leer kilómetros
    context = {"strava_data": strava_data, **_build_athlete_context(user, db)}

    # Conocimiento Hyrox solo si el atleta prepara un Hyrox: engordar el prompt
    # del resto de deportes no aporta y cuesta tokens.
    hyrox_block = hyrox_knowledge.prompt_block_for_user(user, db)
    if hyrox_block:
        hyrox_block = (
            "\n\n" + hyrox_block
            + "\n\n" + wod_structure.PROMPT_SPEC
            + "\nCuando crees o edites WODs de Hyrox/fuerza con add_workout/update_workout, "
            "pasa SIEMPRE el campo `structure` con ese formato (objetivo, calentamiento "
            "específico paso a paso, bloques con pesos de su división, enfriamiento), "
            "además de unas instructions de 1-2 frases."
            "\nEstándar de una sesión de estaciones: ~60 min, 3-4 estaciones distintas en 2-3 bloques y 2-5 km "
            "de carrera dentro; antes de un simulacro, activación de ~40 min; nunca la misma estación pesada "
            "en días seguidos."
        )

    full_system = (
        SYSTEM_PROMPT
        + hyrox_block
        + "\n\n=== CONTEXTO ACTUAL DEL ATLETA ===\n"
        + json.dumps(context, ensure_ascii=False, indent=2, default=str)
        + "\n=== FIN CONTEXTO ===\n"
        + f"\nHOY ES {weekday_es(today_madrid()).upper()} {today_madrid().isoformat()} (hora española). "
        + "Usa esos datos y sus IDs cuando contestes. Sé específico con números y fechas reales."
    )

    history = _load_history(user.id, db, limit=20)
    # El mensaje de AHORA también va con su fecha y hora (el guardado en BD, limpio).
    messages: list[dict[str, Any]] = list(history) + [
        {"role": "user", "content": f"{_stamp(now_madrid(), now=True)}\n{user_message}"}
    ]

    # Persistir el mensaje del usuario antes de llamar a Claude
    db.add(ChatMessage(user_id=user.id, role="user", content=user_message))
    db.commit()

    yield {"phase": "thinking", "message": "Goggins está pensando..."}

    client = ai_client.get_client()
    final_text_parts: list[str] = []
    mutations: list[dict[str, Any]] = []
    wants_change = asks_plan_change(user_message)
    changed_plan = False      # ¿alguna tool de edición terminó con éxito en este turno?
    tool_calls = 0            # nº de tools ejecutadas en este turno (lectura o edición)
    retried = False
    truncations = 0
    interrupted: str | None = None            # 'length' | 'iterations': el turno acabó sin terminar la tarea
    actions: list[dict[str, Any]] = []        # lo que se ejecutó de verdad (para el historial)

    try:
        for iteration in range(MAX_TOOL_ITERATIONS):
            iteration_text: list[str] = []

            # Suelta la transacción antes de esperar a la IA (pueden ser minutos): tenerla
            # abierta bloqueaba las migraciones de un despliegue y, detrás, al resto de consultas.
            db.commit()
            with client.messages.stream(
                model=ai_client.DEFAULT_MODEL,
                max_tokens=CHAT_MAX_TOKENS,
                system=full_system,
                tools=agent_tools.TOOLS,
                messages=messages,
            ) as stream:
                for chunk in stream.text_stream:
                    if not chunk:
                        continue
                    iteration_text.append(chunk)
                    yield {"phase": "chunk", "text": chunk}
                final_msg = stream.get_final_message()

            # Acumular el texto de esta vuelta para guardarlo en BD al final
            if iteration_text:
                final_text_parts.append("".join(iteration_text))

            # Append la respuesta del asistente (texto + tool_use blocks) al historial
            messages.append(
                {
                    "role": "assistant",
                    "content": [_content_block_to_dict(b) for b in final_msg.content],
                }
            )

            if final_msg.stop_reason == "max_tokens":
                # Respuesta CORTADA por longitud. Antes se trataba como el final normal del turno:
                # la llamada a la tool que iba a ejecutarse se perdía y el atleta veía un texto que
                # acababa en "…:" sin que se hubiera hecho nada.
                truncations += 1
                kept = [b for b in messages[-1]["content"] if b.get("type") != "tool_use"]
                messages[-1]["content"] = kept or [{"type": "text", "text": "(respuesta cortada)"}]
                if truncations <= MAX_TRUNCATIONS:
                    messages.append({"role": "user", "content": _TRUNCATED_MESSAGE})
                    continue
                interrupted = "length"
                break

            if final_msg.stop_reason != "tool_use":
                texto = "".join(iteration_text)
                afirma = wants_change and claims_plan_change(texto)
                # Promesa sin cumplir: le pidieron un cambio y termina sin preguntar nada, o bien
                # sin tocar ninguna tool ("empezamos ya") o bien prometiendo hacerlo después de
                # solo consultar ("lo arreglo AHORA").
                promete = (
                    wants_change and bool(texto.strip()) and not _QUESTION_OR_OFFER_RE.search(texto)
                    and (tool_calls == 0 or commits_without_doing(texto))
                )
                if (afirma or promete) and not changed_plan:
                    if not retried:
                        # Se retira ese texto y se le obliga a ejecutar la tool (o a preguntar).
                        retried = True
                        if iteration_text:
                            final_text_parts.pop()
                        yield {"phase": "retract"}
                        messages.append({"role": "user", "content": _GUARD_MESSAGE if afirma else _PROMISE_MESSAGE})
                        continue
                    final_text_parts.append(_NO_CHANGE_NOTICE.strip())
                    yield {"phase": "chunk", "text": _NO_CHANGE_NOTICE}
                break

            # Ejecutar todos los tool_use blocks de esta respuesta
            tool_results: list[dict[str, Any]] = []
            for block in final_msg.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_name = block.name
                tool_input = block.input or {}
                tool_calls += 1
                yield {"phase": "tool_use", "name": tool_name, "input": tool_input}

                result = agent_tools.execute_tool(tool_name, tool_input, user, db)

                yield {
                    "phase": "tool_result",
                    "name": tool_name,
                    "ok": bool(result.get("ok")),
                    "summary": result.get("summary") or result.get("error"),
                }
                if result.get("ok") and result.get("mutation"):
                    mutations.append(result)
                    yield {"phase": "mutation", "data": result}
                if result.get("ok") and tool_name in MUTATING_TOOLS and result.get("mutation"):
                    changed_plan = True
                if len(actions) < _MAX_LOGGED_ACTIONS:
                    actions.append({
                        "tool": tool_name,
                        "ok": bool(result.get("ok")),
                        "summary": str(result.get("summary") or result.get("error") or "")[:160],
                    })

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                        "is_error": not bool(result.get("ok")),
                    }
                )

            # Devolver resultados a Claude para que continúe
            messages.append({"role": "user", "content": tool_results})
        else:
            logger.warning("[goggins_agent] alcanzado MAX_TOOL_ITERATIONS")
            interrupted = "iterations"
    except Exception as e:
        logger.exception(f"[goggins_agent] stream falló: {e}")
        yield {"phase": "error", "detail": f"Error llamando a Claude: {e}"}
        return

    if interrupted:
        aviso = _interruption_notice(interrupted, actions)
        final_text_parts.append(aviso)
        yield {"phase": "chunk", "text": "\n\n" + aviso}
        actions.append({"interrupted": interrupted})

    full_text = _clean_reply("\n\n".join(p for p in final_text_parts if p))

    # Persistir respuesta del asistente (con el registro de lo ejecutado, que el atleta no ve
    # pero el modelo sí recibe en el historial del turno siguiente)
    db.add(ChatMessage(
        user_id=user.id, role="assistant", content=full_text,
        tool_calls=json.dumps(actions, ensure_ascii=False) if actions else None,
    ))
    db.commit()

    yield {"phase": "done", "content": full_text, "mutations": mutations}

def _adaptive_paces_ctx(user) -> dict | None:
    """Resumen de los ritmos adaptativos para el prompt (o None si no hay)."""
    ap = getattr(user, "adaptive_paces", None)
    if not ap:
        return None
    src = ap.get("source") or {}
    return {
        "vdot": ap.get("vdot"),
        "paces_min_per_km": ap.get("paces"),
        "based_on": {
            "kind": src.get("kind"),
            "detail": src.get("category") or src.get("name") or ("VAM" if src.get("kind") == "vam" else None),
            "date": src.get("date"),
        },
        "computed_at": ap.get("computed_at"),
    }
