"""Resumen del plan por semanas, contado por el SERVIDOR.

Un LLM cuenta mal: asigna sesiones a la semana equivocada y da por cumplida una
regla que no lo está. Aquí se cuenta de lunes a domingo con código; Goggins lo
recibe ya calculado (en el contexto y en la tool `plan_overview`) y no cuenta a mano.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.workout import Workout, WorkoutStatus
from app.services.clock import weekday_es

HYROX_TYPES = {"hyrox_stations", "hyrox_sim"}
RUN_TYPES = {"easy_run", "tempo", "intervals", "long_run", "recovery", "fartlek", "hill_repeats"}
STRENGTH_TYPES = {"strength_upper", "strength_lower", "strength_full"}

CATEGORIES = ("hyrox", "run", "strength", "mobility", "race", "other")
_LABELS = {"hyrox": "hyrox", "run": "run", "strength": "fuerza", "mobility": "movilidad", "race": "carrera", "other": "otros"}


def type_value(t: Any) -> str:
    return t.value if hasattr(t, "value") else str(t)


def category_of(workout_type: Any) -> str:
    t = type_value(workout_type)
    if t in HYROX_TYPES:
        return "hyrox"
    if t in RUN_TYPES:
        return "run"
    if t in STRENGTH_TYPES:
        return "strength"
    if t == "mobility":
        return "mobility"
    if t == "race":
        return "race"
    if t == "rest":
        return "rest"
    return "other"


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def overview(db: Session, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
    """Semanas COMPLETAS (lun-dom) que cubren [start, end], con sus conteos por categoría.

    Cuenta lo planificado y lo completado; lo saltado no cuenta. Las semanas vacías
    también salen (un hueco del plan es justo lo que hay que ver).
    """
    first = week_monday(start)
    last = week_monday(end) + timedelta(days=6)
    rows = (
        db.query(Workout)
        .filter(Workout.user_id == user_id, Workout.date >= first, Workout.date <= last)
        .order_by(Workout.date.asc(), Workout.id.asc())
        .all()
    )
    weeks = []
    monday = first
    while monday <= last:
        sunday = monday + timedelta(days=6)
        mine = [
            w for w in rows
            if monday <= w.date <= sunday and w.status != WorkoutStatus.skipped and category_of(w.type) != "rest"
        ]
        counts = {c: 0 for c in CATEGORIES}
        for w in mine:
            counts[category_of(w.type)] += 1
        busy = {w.date.weekday() for w in mine}
        weeks.append({
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "counts": counts,
            "total": len(mine),
            "free_weekdays": [weekday_es(monday + timedelta(days=i)) for i in range(7) if i not in busy],
            "sessions": [
                f"{weekday_es(w.date)} {w.date.day} · {type_value(w.type)} · id {w.id}"
                + (" · hecho" if w.status == WorkoutStatus.completed else "")
                for w in mine
            ],
        })
        monday += timedelta(days=7)
    return weeks


def week_line(week: dict[str, Any]) -> str:
    """Una línea compacta por semana (para el contexto del agente)."""
    c = week["counts"]
    partes = [f"{_LABELS[k]} {c[k]}" for k in ("hyrox", "run", "strength")]
    partes += [f"{_LABELS[k]} {c[k]}" for k in ("mobility", "race", "other") if c[k]]
    libres = ", ".join(d[:3] for d in week["free_weekdays"]) or "ninguno"
    return f"{week['week_start']} · {' · '.join(partes)} · total {week['total']} · días libres: {libres}"
