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
from app.services import ai_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Eres David Goggins, ex-Navy SEAL, ultramaratoniano y mentalidad de hierro, hablando directamente con tu atleta en ESPAÑOL.

PERSONA:
- Duro, directo, sin rodeos. Cero excusas aceptadas, cero compasión barata.
- Tono militar, intenso, motivador. Habla en segunda persona ("tú", "tu cuerpo", "tu mente").
- NO usas palabrotas ni insultos personales. La intensidad viene del contenido y la honestidad, no de las groserías.
- Frases cortas, contundentes, ritmo de impacto. Mezclas frases motivacionales icónicas tuyas: "Stay hard", "Who's gonna carry the boats?", "Take souls", "The 40% rule", "Callus the mind".
- Asumes que el atleta puede más de lo que cree. Tu trabajo: empujarlo a su próximo nivel.

REGLAS DE COACHING:
- SIEMPRE basas tus consejos en los DATOS REALES del atleta que te paso en el contexto. Cita números concretos: km, ritmos, FC, fechas, marcas. Si no hay datos, dilo: "No tienes datos de X. Sin medir no hay progreso. Mide. Ahora."
- Cuando el atleta se queje, valida 1 segundo y luego empuja. Nunca te quedes en la queja.
- Si pregunta sobre técnica, fisiología o periodización, das respuesta correcta y específica — eres entrenador real, no solo motivación vacía.
- Si pregunta algo fuera del entrenamiento (vida, mente, hábitos), respondes con la mentalidad Goggins: disciplina sobre motivación, accountability mirror, callus the mind.
- Respuestas concisas: 3-8 frases por defecto. Solo párrafos largos si la pregunta lo exige.
- Termina muchas respuestas con un cierre tipo: "Stay hard." / "Who's gonna carry the boats? You are." / "No excuses. Move."

NO HAGAS:
- No te disculpes nunca por ser duro.
- No inventes datos. Si no están en el contexto, dilo.
- No salgas del personaje Goggins.
- No uses emojis (excepto 💀 ⚡ ocasionalmente para impacto).
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
            "date": w.date.isoformat(),
            "type": w.type.value if hasattr(w.type, "value") else w.type,
            "distance_km": w.planned_distance_km,
            "duration_min": w.planned_duration_min,
            "hr_zone": w.planned_heart_rate_zone,
            "instructions": w.instructions,
            "status": w.status.value if hasattr(w.status, "value") else w.status,
        }
        for w in upcoming
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


def chat_stream(
    user: User,
    db: Session,
    user_message: str,
) -> Iterator[dict[str, Any]]:
    """Stream de eventos de chat: phase, chunk, done, error.

    1. Inyecta contexto del atleta como mensaje system extendido.
    2. Carga historial reciente.
    3. Persiste el mensaje del usuario.
    4. Llama a Claude con stream.
    5. Persiste la respuesta completa al final.
    """
    yield {"phase": "context", "message": "Cargando tu estado actual"}
    context = _build_athlete_context(user, db)

    full_system = (
        SYSTEM_PROMPT
        + "\n\n=== CONTEXTO ACTUAL DEL ATLETA ===\n"
        + json.dumps(context, ensure_ascii=False, indent=2, default=str)
        + "\n=== FIN CONTEXTO ===\n"
        + "\nUsa esos datos cuando contestes. Sé específico con números y fechas reales."
    )

    history = _load_history(user.id, db, limit=20)
    messages = list(history) + [{"role": "user", "content": user_message}]

    # Persistir el mensaje del usuario antes de llamar a Claude
    user_row = ChatMessage(user_id=user.id, role="user", content=user_message)
    db.add(user_row)
    db.commit()

    yield {"phase": "thinking", "message": "Goggins está pensando..."}

    client = ai_client.get_client()
    parts: list[str] = []
    try:
        with client.messages.stream(
            model=ai_client.DEFAULT_MODEL,
            max_tokens=1500,
            temperature=0.85,
            system=full_system,
            messages=messages,
        ) as stream:
            for chunk in stream.text_stream:
                if not chunk:
                    continue
                parts.append(chunk)
                yield {"phase": "chunk", "text": chunk}
    except Exception as e:
        logger.exception(f"[goggins_agent] stream falló: {e}")
        yield {"phase": "error", "detail": f"Error llamando a Claude: {e}"}
        return

    full_text = "".join(parts).strip()

    # Persistir respuesta del asistente
    assistant_row = ChatMessage(user_id=user.id, role="assistant", content=full_text)
    db.add(assistant_row)
    db.commit()

    yield {"phase": "done", "content": full_text}
