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
from app.services import ai_client, agent_tools

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
- `add_workout(date, type, ...)` — para añadir un entreno nuevo.
- `mark_workout_status(workout_id, status)` — para marcar como completado o saltado.
- `list_workouts(start_date, end_date)` — si necesitas buscar workouts fuera del contexto inicial.
- `shift_plan(days|weeks, from_date)` — desplaza TODOS los workouts futuros del plan N días o semanas. Úsalo para "no puedo entrenar esta semana / estos días": muévelo todo de golpe en vez de uno a uno.
- `adjust_week_load(week_start_date, factor)` — escala distancia y duración de los workouts de esa semana por un factor (0.8 = bajar 20%, 1.15 = subir 15%). Úsalo para "me veo flojo" (baja) o "me veo fuerte/sobrado" (sube).
- `get_strava_summary(days)` — resumen agregado de lo realmente hecho en Strava (km, tiempo, sesiones, FC media por disciplina) en el periodo. Úsalo para responder con datos a "¿cómo voy?", "¿puedo mejorar?".
- `compare_planned_vs_actual(start_date, end_date)` — compara lo planificado con lo realmente hecho en el rango. Úsalo para detectar desfases y justificar subir/bajar la carga.

REGLAS DE TOOL USE:
- Los workout_ids están en el contexto que te paso (campo `id` de cada workout en `upcoming_workouts`). Úsalos.
- Si el atleta pide algo ambiguo ("muéveme el de mañana"), elige el más probable basándote en el contexto y CONFIRMA en tu respuesta qué hiciste.
- Después de ejecutar una tool, responde como Goggins: confirma el cambio en 1-2 frases con tono duro-motivador. NO listes datos crudos del JSON, escribe como humano.
- Si la tool falla, díselo al atleta sin rodeos: "Eso no funcionó. Intenta de nuevo o dime qué entreno exacto."
- NUNCA inventes workout_ids. Si no los tienes, llama a `list_workouts` primero.
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
    today = date.today()

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
    }

    # Objetivos activos
    goals = db.query(Goal).filter(Goal.user_id == user.id, Goal.is_active == True).all()  # noqa
    goals_list = []
    for g in goals:
        days_to = None
        if g.target_race_date:
            days_to = (g.target_race_date - today).days
        goals_list.append({
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
        entry = {"category": r.category}
        if r.value_seconds:
            entry["time"] = _format_seconds(r.value_seconds)
        if r.value_numeric is not None:
            entry["value"] = r.value_numeric
            entry["unit"] = r.unit
        if r.date_achieved:
            entry["date"] = r.date_achieved.isoformat()
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
        .limit(20)
        .all()
    )
    upcoming_list = [
        {
            "id": w.id,
            "date": w.date.isoformat(),
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

    return {
        "today": today.isoformat(),
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


def _load_history(user_id: int, db: Session, limit: int = 20) -> list[dict[str, str]]:
    """Carga los últimos N mensajes del historial en orden cronológico."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content} for r in rows]


MAX_TOOL_ITERATIONS = 6


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
    context = _build_athlete_context(user, db)

    full_system = (
        SYSTEM_PROMPT
        + "\n\n=== CONTEXTO ACTUAL DEL ATLETA ===\n"
        + json.dumps(context, ensure_ascii=False, indent=2, default=str)
        + "\n=== FIN CONTEXTO ===\n"
        + "\nUsa esos datos y sus IDs cuando contestes. Sé específico con números y fechas reales."
    )

    history = _load_history(user.id, db, limit=20)
    messages: list[dict[str, Any]] = list(history) + [
        {"role": "user", "content": user_message}
    ]

    # Persistir el mensaje del usuario antes de llamar a Claude
    db.add(ChatMessage(user_id=user.id, role="user", content=user_message))
    db.commit()

    yield {"phase": "thinking", "message": "Goggins está pensando..."}

    client = ai_client.get_client()
    final_text_parts: list[str] = []
    mutations: list[dict[str, Any]] = []

    try:
        for iteration in range(MAX_TOOL_ITERATIONS):
            iteration_text: list[str] = []

            with client.messages.stream(
                model=ai_client.DEFAULT_MODEL,
                max_tokens=2500,
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

            if final_msg.stop_reason != "tool_use":
                break

            # Ejecutar todos los tool_use blocks de esta respuesta
            tool_results: list[dict[str, Any]] = []
            for block in final_msg.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                tool_name = block.name
                tool_input = block.input or {}
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
    except Exception as e:
        logger.exception(f"[goggins_agent] stream falló: {e}")
        yield {"phase": "error", "detail": f"Error llamando a Claude: {e}"}
        return

    full_text = "\n\n".join(p for p in final_text_parts if p).strip()

    # Persistir respuesta del asistente
    db.add(ChatMessage(user_id=user.id, role="assistant", content=full_text))
    db.commit()

    yield {"phase": "done", "content": full_text, "mutations": mutations}
