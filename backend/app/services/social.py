"""Ranking social del grupo y comentario vacilón de Goggins.

Principio: entre usuarios solo circulan AGREGADOS (km, minutos, sesiones por
disciplina). Nunca actividades sueltas, ni email, ni datos físicos. Es lo que
encaja con la política de Strava (no exponer datos de un atleta a otros más
allá de lo imprescindible) y lo único que un ranking necesita.

El comentario de Goggins se genera con el modelo rápido y se cachea en
AiInsight (kind="social_roast") por semana ISO y huella del ranking: solo se
regenera si cambia el ranking o pasa la semana, no cada vez que alguien abre
la pestaña.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.ai_insight import AiInsight
from app.models.strava_activity import StravaActivity
from app.models.user import User
from app.services import ai_client
from app.services.discipline import discipline_for_strava_type

logger = logging.getLogger(__name__)

# Disciplinas que se muestran en el ranking (el resto cae en "other" y no
# compite: no tiene sentido rankear "otro").
RANKED = ("run", "bike", "swim", "strength")

ROAST_KIND = "social_roast"
# user_id "del grupo" para la caché: el roast es compartido, no de un usuario.
# Usamos el del primer usuario (maestro) para no cambiar el esquema.
ROAST_SYSTEM = """Eres David Goggins comentando la clasificación semanal de un grupo de amigos que entrenan juntos (triatlón, carrera, bici, natación, fuerza). Hablas en ESPAÑOL.

TONO: vacilón, pique sano, humor duro estilo Goggins. Picas al que va último para que espabile y reconoces al primero sin hacerle la pelota. Puedes meterte con quien no ha entrenado nada. NUNCA insultos personales, palabrotas ni comentarios sobre el cuerpo, el peso o la salud de nadie. Solo sobre lo que han entrenado (o no).

FORMATO: 3-5 frases cortas, contundentes. Cita números concretos (km, sesiones). Menciona por nombre al menos al primero y al último de la disciplina principal. Sin listas, sin emojis (salvo un 💀 opcional). Termina con una frase de pique para la semana que viene.

NO inventes datos: solo lo que te paso. Si todos están a cero, métete con el grupo entero."""


def display_name(u: User) -> str:
    """Nombre de pila para mostrar al grupo. Nunca un handle de email.

    create_user rellena name = parte local del email si no se da nombre
    ("ikergalarza1999"); eso no debe publicarse. Un nombre real que coincida
    con el email ("Unai" / unai@x.com) sí vale: lo que se rechaza son las
    señales de handle (dígitos, puntos, guiones bajos, arroba), no la
    coincidencia en sí.
    """
    raw = (u.name or "").strip()
    if not raw or "@" in raw:
        return f"Atleta {u.id}"
    first = raw.split()[0]
    if any(ch.isdigit() for ch in first) or "." in first or "_" in first:
        return f"Atleta {u.id}"
    return first[:1].upper() + first[1:]


def _monday(dt: datetime) -> datetime:
    d = dt - timedelta(days=dt.weekday())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def leaderboard(db: Session, weeks: int = 1, me_id: Optional[int] = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """Ranking por disciplina de TODOS los usuarios en las últimas `weeks` semanas.

    weeks=1 -> desde el lunes de la semana actual. weeks=4 -> desde el lunes de
    hace 3 semanas (4 semanas naturales incluyendo la actual).
    """
    now = now or datetime.now(timezone.utc)
    since = _monday(now) - timedelta(weeks=max(weeks, 1) - 1)

    users = db.query(User).order_by(User.id.asc()).all()
    agg: dict[int, dict[str, dict[str, float]]] = {
        u.id: {d: {"km": 0.0, "min": 0.0, "n": 0} for d in RANKED} for u in users
    }
    rows = (
        db.query(StravaActivity)
        .filter(StravaActivity.start_date >= since)
        .all()
    )
    for a in rows:
        if a.user_id not in agg:
            continue
        d = discipline_for_strava_type(a.type)
        if d not in RANKED:
            continue
        b = agg[a.user_id][d]
        b["km"] += (a.distance_m or 0) / 1000.0
        b["min"] += (a.moving_time_s or 0) / 60.0
        b["n"] += 1

    names = {u.id: display_name(u) for u in users}
    out: dict[str, list[dict[str, Any]]] = {}
    for d in RANKED:
        rows_d = []
        for u in users:
            b = agg[u.id][d]
            rows_d.append({
                "user_id": u.id,
                "name": names[u.id],
                "km": round(b["km"], 1),
                "min": int(round(b["min"])),
                "sessions": int(b["n"]),
                "is_me": (me_id is not None and u.id == me_id),
            })
        # Fuerza se ordena por minutos (no tiene km); el resto por km.
        key = (lambda r: (r["min"], r["sessions"])) if d == "strength" else (lambda r: (r["km"], r["min"]))
        rows_d.sort(key=key, reverse=True)
        # Empates exactos comparten puesto (1,1,3): no se reparten medallas
        # distintas por orden de alta.
        prev_key, prev_rank = None, 0
        for i, r in enumerate(rows_d, start=1):
            k = key(r)
            if k != prev_key:
                prev_rank = i
                prev_key = k
            r["rank"] = prev_rank
        out[d] = rows_d

    return {
        "weeks": weeks,
        "since": since.date().isoformat(),
        "until": now.date().isoformat(),
        "members": len(users),
        "disciplines": out,
    }


def roast_context(board: dict[str, Any]) -> str:
    """Texto compacto y anónimo (solo nombres de pila + números) para el prompt."""
    lines = [f"Periodo: {board['since']} a {board['until']} ({board['weeks']} semana(s)). {board['members']} atletas."]
    labels = {"run": "Carrera", "bike": "Bici", "swim": "Natación", "strength": "Fuerza"}
    for d in RANKED:
        rows = board["disciplines"].get(d, [])
        if not rows:
            continue
        parts = []
        for r in rows:
            if d == "strength":
                parts.append(f"{r['name']} {r['sessions']} ses/{r['min']} min")
            else:
                parts.append(f"{r['name']} {r['km']} km/{r['sessions']} ses")
        lines.append(f"{labels[d]}: " + ", ".join(parts))
    return "\n".join(lines)


def _fingerprint(board: dict[str, Any]) -> str:
    # Huella del ranking sin nombres de usuario id: si cambian km/sesiones, cambia.
    payload = {d: [(r["name"], r["km"], r["sessions"], r["min"]) for r in rows]
               for d, rows in board["disciplines"].items()}
    payload["since"] = board["since"]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


NEGATIVE_TTL = timedelta(minutes=10)


def get_roast(db: Session, board: dict[str, Any], force: bool = False) -> Optional[dict[str, Any]]:
    """Comentario de Goggins sobre el ranking, cacheado por huella del ranking.

    - Acierta por HUELLA (no solo la última fila): alternar 1/4 semanas no
      invalida la caché del otro periodo.
    - Caché negativa: si la IA falla, no se reintenta en cada carga de página
      durante NEGATIVE_TTL.
    Devuelve {"text", "created_at", "cached"} o None si no hay texto.
    """
    fp = _fingerprint(board)
    owner = db.query(User).order_by(User.id.asc()).first()
    if owner is None:
        return None

    # Búsqueda por huella entre las recientes (no hay índice JSON; acotamos).
    recent = (
        db.query(AiInsight)
        .filter(AiInsight.user_id == owner.id, AiInsight.kind == ROAST_KIND)
        .order_by(AiInsight.created_at.desc())
        .limit(50)
        .all()
    )
    if not force:
        for row in recent:
            data = row.data or {}
            if data.get("fingerprint") != fp:
                continue
            if row.summary:
                return {"text": row.summary, "created_at": row.created_at.isoformat() if row.created_at else None, "cached": True}
            # Fila "negativa" (fallo reciente): no reintentar todavía.
            created = row.created_at
            if created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - created < NEGATIVE_TTL:
                    return None
            break

    try:
        text = ai_client.complete(ROAST_SYSTEM, roast_context(board), model=ai_client.FAST_MODEL, max_tokens=400).strip()
    except Exception as e:
        logger.warning(f"[social] roast falló: {e}")
        # Caché negativa: fila sin summary con la huella.
        try:
            db.add(AiInsight(user_id=owner.id, kind=ROAST_KIND, summary=None,
                             data={"fingerprint": fp, "weeks": board["weeks"], "since": board["since"], "error": str(e)[:200]},
                             model=ai_client.FAST_MODEL))
            db.commit()
        except Exception:
            db.rollback()
        return None

    row = AiInsight(user_id=owner.id, kind=ROAST_KIND, summary=text,
                    data={"fingerprint": fp, "weeks": board["weeks"], "since": board["since"]},
                    model=ai_client.FAST_MODEL)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"text": text, "created_at": row.created_at.isoformat() if row.created_at else None, "cached": False}
