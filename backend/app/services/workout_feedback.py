"""Feedback automático de Goggins cuando se completa un entreno.

Cuando un workout pasa a 'completed' (al emparejar una actividad de Strava o al
marcarlo a mano), Goggins escribe un mensaje breve en el historial del chat
comparando lo planificado con lo realmente hecho. Queda guardado para que el
atleta lo lea cuando entre.

Política "de ahora en adelante": solo se genera para entrenos recientes
(date >= hoy - RECENT_DAYS) y una sola vez por entreno (si no tiene ya feedback),
para no generar una avalancha al sincronizar el histórico.
"""
import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workout import Workout
from app.models.chat_message import ChatMessage
from app.services import ai_client

logger = logging.getLogger(__name__)

RECENT_DAYS = 2  # ventana para considerar un completado "de ahora en adelante"

_SYSTEM = """Eres David Goggins, coach de resistencia, hablando a tu atleta en ESPAÑOL.
El atleta acaba de COMPLETAR un entreno. Escríbele un feedback BREVE (2-4 frases),
duro pero justo, comparando lo planificado con lo que realmente hizo:
- Si cumplió o superó el plan, reconócelo con intensidad y empuja a más.
- Si se quedó corto (menos distancia/tiempo o FC muy alta para la zona), dilo sin rodeos y da la corrección.
- Cita 1-2 datos concretos (km, ritmo, FC). No inventes datos que no estén.
- Nada de listas; texto directo. Cierra con una frase de impacto solo a veces.
No uses emojis salvo 💀 o ⚡ ocasional."""


def _fmt(workout: Workout) -> str:
    def g(v, suf=""):
        return f"{v}{suf}" if v is not None else "—"
    wtype = workout.type.value if hasattr(workout.type, "value") else workout.type
    return (
        f"Tipo: {wtype}\n"
        f"PLANIFICADO: distancia={g(workout.planned_distance_km, ' km')}, "
        f"duración={g(workout.planned_duration_min, ' min')}, "
        f"zona={g(workout.planned_heart_rate_zone)}\n"
        f"REALIZADO (Strava): distancia={g(workout.actual_distance_km, ' km')}, "
        f"duración={g(workout.actual_duration_min, ' min')}, "
        f"FC media={g(workout.actual_avg_heart_rate, ' ppm')}, "
        f"FC máx={g(workout.actual_max_heart_rate, ' ppm')}\n"
        f"Instrucciones del plan: {workout.instructions or '—'}"
    )


def generate_completion_feedback(user: User, workout: Workout, db: Session) -> str | None:
    """Genera y guarda en el chat un feedback de Goggins para un workout completado.

    Devuelve el texto, o None si no aplica (ya tenía feedback) o falló.
    """
    if workout.ai_feedback:
        return None
    try:
        text = ai_client.complete(
            system=_SYSTEM,
            user_message="Dame el feedback de este entreno completado:\n\n" + _fmt(workout),
            model=ai_client.FAST_MODEL,
            max_tokens=400,
        ).strip()
    except Exception as e:
        logger.warning(f"[workout_feedback] no se pudo generar feedback wid={workout.id}: {e}")
        return None
    if not text:
        return None

    workout.ai_feedback = text
    db.add(workout)
    db.add(ChatMessage(user_id=user.id, role="assistant", content=text))
    db.commit()
    logger.info(f"[workout_feedback] feedback generado para workout {workout.id}")
    return text


def generate_for_completed(user: User, workouts: list[Workout], db: Session) -> int:
    """Genera feedback para los workouts recién completados que sean recientes.

    'De ahora en adelante': ignora los de fecha antigua (histórico) para no
    inundar el chat al sincronizar Strava por primera vez.
    """
    cutoff = date.today() - timedelta(days=RECENT_DAYS)
    count = 0
    for w in workouts:
        if not w.date or w.date < cutoff:
            continue
        if generate_completion_feedback(user, w, db):
            count += 1
    if count:
        logger.info(f"[workout_feedback] {count} feedbacks de completado generados")
    return count
