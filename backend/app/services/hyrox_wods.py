"""Plantillas de WOD de Hyrox: sesiones nuevas al instante, en el servidor.

Cuando hay que añadir sesiones de Hyrox a muchas semanas de golpe (p. ej. "dos
a la semana hasta la carrera"), pedirle a Goggins que redacte un WOD completo por
sesión desbordaba el límite de su respuesta y la petición se quedaba a medias.
Estas plantillas dan sesiones VÁLIDAS (mismo formato que `wod_structure`) con:
  - los pesos de la división del atleta (temporada 25/26, `hyrox_knowledge`),
  - su ritmo de carrera (umbral + 15 s/km: ritmo Hyrox según la metodología),
  - carga que sube según lo cerca que esté la carrera (base → build → peak → taper),
  - siempre en SOLITARIO (el atleta entrena solo: cero relevos).
La duración sale luego de `wod_duration` desde el propio WOD.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from app.services import hyrox_knowledge

N_TEMPLATES = 5

# Margen sobre el ritmo de umbral para correr con la fatiga de las estaciones.
_RACE_PACE_MARGIN_S = 15

_PHASES: dict[str, dict[str, Any]] = {
    "base":  {"scale": 0.85, "rounds": 3, "wb": 15, "bbj": 20, "run_m": 500, "lunge_m": 50, "erg_rounds": 2},
    "build": {"scale": 1.0,  "rounds": 4, "wb": 20, "bbj": 25, "run_m": 600, "lunge_m": 50, "erg_rounds": 3},
    "peak":  {"scale": 1.0,  "rounds": 5, "wb": 25, "bbj": 30, "run_m": 800, "lunge_m": 60, "erg_rounds": 3},
    "taper": {"scale": 0.9,  "rounds": 3, "wb": 15, "bbj": 20, "run_m": 400, "lunge_m": 40, "erg_rounds": 2},
}

_COOLDOWN = ["5' trote muy suave", "estiramiento de cuádriceps, glúteo y gemelo (30'' por lado)"]


def _phase(weeks_to_race: Optional[int]) -> str:
    if weeks_to_race is None or weeks_to_race > 8:
        return "base"
    if weeks_to_race >= 4:
        return "build"
    if weeks_to_race >= 2:
        return "peak"
    return "taper"


def _round5(x: float) -> int:
    return int(round(x / 5) * 5)


def _race_pace(threshold_pace: Optional[str]) -> Optional[str]:
    """Ritmo de las carreras comprometidas: umbral + 15 s/km, como 'm:ss/km'. None si no hay ritmo válido."""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", threshold_pace or "")
    if not m:
        return None
    sec = int(m.group(1)) * 60 + int(m.group(2)) + _RACE_PACE_MARGIN_S
    return f"{sec // 60}:{sec % 60:02d}/km"


def _weights(division_key: str, scale: float) -> dict[str, Any]:
    std = hyrox_knowledge.DIVISION_STANDARDS.get(division_key) or hyrox_knowledge.DIVISION_STANDARDS["open_men"]
    per_hand = re.search(r"(\d+)\s*$", str(std["farmers_kg"]))
    # Con la carga de competición (scale 1) se usa el peso EXACTO; al rebajarlo, a múltiplos de 5.
    load = (lambda kg: kg) if scale >= 1 else (lambda kg: _round5(kg * scale))
    return {
        "push": load(std["sled_push_kg"]),
        "pull": load(std["sled_pull_kg"]),
        "farmers": int(per_hand.group(1)) if per_hand else 24,
        "farmers_label": std["farmers_kg"],
        "sandbag": std["sandbag_kg"],
        "ball": std["wall_ball_kg"],
        "label": std["label"],
    }


def _run(distance_m: int, pace: Optional[str]) -> dict[str, Any]:
    item: dict[str, Any] = {"exercise": "run", "distance_m": distance_m}
    if pace:
        item["pace"] = pace
    return item


def _approach(w: dict[str, Any]) -> dict[str, Any]:
    return {"exercise": "sled_push", "distance_m": 12, "weight_kg": _round5(w["push"] * 0.5), "notes": "2 aproximaciones al 50%"}


# ── Plantillas ───────────────────────────────────────────────────────────────
# Cada una devuelve: título, objetivo, calentamiento (pasos), bloques, notas y el resumen de 1 frase.

def _compromised(p, w, pace):
    return dict(
        title="Running comprometido",
        objective="Correr con las piernas cargadas: tras el sled y los wall balls, mantener el ritmo del primer km al último.",
        warmup=[
            {"exercise": "row", "distance_m": 500, "notes": "suave, progresivo"},
            {"exercise": "inchworm", "reps": 6, "notes": "2 series"},
            {"exercise": "glute_bridge", "reps": 15, "notes": "2 series"},
            _approach(w),
        ],
        blocks=[{
            "title": "Carrera + estaciones", "format": "rounds", "rounds": p["rounds"], "rest_s": 90,
            "items": [
                _run(p["run_m"], pace),
                {"exercise": "wall_balls", "reps": p["wb"], "weight_kg": w["ball"]},
                {"exercise": "sled_push", "distance_m": 25, "weight_kg": w["push"]},
            ],
        }],
        notes="El km de la ronda 1 y el de la última deben salir al mismo ritmo: corre plano, sin adrenalina.",
        summary=f"{p['rounds']} rondas de {p['run_m']} m + {p['wb']} wall balls + 25 m de sled push ({w['push']} kg), 90'' de descanso",
    )


def _sled(p, w, pace):
    return dict(
        title="Trineo y tracción",
        objective="Fuerza específica de empuje y tracción: el trineo es donde más tiempo pierde el amateur.",
        warmup=[
            {"exercise": "cat_camel", "reps": 8},
            {"exercise": "hip_flexor_stretch", "duration_s": 40, "notes": "cada lado"},
            {"exercise": "glute_bridge", "reps": 15, "notes": "2 series"},
            _approach(w),
        ],
        blocks=[
            {"title": "Trineo", "format": "rounds", "rounds": p["rounds"], "rest_s": 120, "items": [
                {"exercise": "sled_push", "distance_m": 25, "weight_kg": w["push"], "notes": "pasos cortos, tronco bajo"},
                {"exercise": "sled_pull", "distance_m": 25, "weight_kg": w["pull"], "notes": "mano sobre mano, caderas abajo"},
            ]},
            {"title": "Remate", "format": "rounds", "rounds": 2, "rest_s": 60, "items": [
                {"exercise": "burpee_broad_jump", "distance_m": p["bbj"]},
                {"exercise": "ski_erg", "distance_m": 250},
            ]},
        ],
        notes="En el pull, no te sientes: la tracción sale de las caderas y las piernas, no de la espalda.",
        summary=f"{p['rounds']} rondas de 25 m de sled push ({w['push']} kg) + 25 m de sled pull ({w['pull']} kg), y remate de burpees y SkiErg",
    )


def _legs_grip(p, w, pace):
    return dict(
        title="Piernas y agarre",
        objective="Cuádriceps, glúteo y agarre bajo fatiga: lunges con saco, farmers y wall balls.",
        warmup=[
            {"exercise": "ninety_ninety", "duration_s": 60, "notes": "cada lado"},
            {"exercise": "cossack_squat", "reps": 8, "notes": "cada lado"},
            {"exercise": "glute_bridge", "reps": 15, "notes": "2 series"},
            {"exercise": "lunge", "reps": 10, "notes": "sin carga, cada pierna"},
        ],
        blocks=[
            {"title": "Lunges con saco", "format": "rounds", "rounds": p["rounds"], "rest_s": 90, "items": [
                {"exercise": "sandbag_lunges", "distance_m": p["lunge_m"], "weight_kg": w["sandbag"], "notes": "zancadas continuas, sin apoyar la rodilla"},
            ]},
            {"title": "Farmers + wall balls", "format": "rounds", "rounds": 3, "rest_s": 60, "items": [
                {"exercise": "farmers_carry", "distance_m": 100, "weight_kg": w["farmers"], "notes": f"{w['farmers_label']} kg, uno en cada mano"},
                {"exercise": "wall_balls", "reps": p["wb"], "weight_kg": w["ball"], "notes": "tandas largas con micro-pausas"},
            ]},
        ],
        notes="Si el agarre se rinde antes que las piernas, ese es el punto débil: apúntalo.",
        summary=f"{p['rounds']} × {p['lunge_m']} m de lunges con saco ({w['sandbag']} kg) y 3 rondas de farmers ({w['farmers_label']} kg) + {p['wb']} wall balls",
    )


def _ergs(p, w, pace):
    return dict(
        title="Ergómetros a ritmo de carrera",
        objective="Ritmo sostenible en SkiErg y remo (algo conservador, ~ritmo de 2 km) para no pagarlo en las estaciones siguientes.",
        warmup=[
            {"exercise": "thoracic_opener", "reps": 8, "notes": "cada lado"},
            {"exercise": "leg_swing", "reps": 10, "notes": "cada pierna"},
            {"exercise": "ski_erg", "distance_m": 250, "notes": "suave, progresivo"},
            {"exercise": "row", "distance_m": 250, "notes": "suave, progresivo"},
        ],
        blocks=[
            {"title": "Ergómetros", "format": "rounds", "rounds": p["erg_rounds"], "rest_s": 180, "items": [
                {"exercise": "ski_erg", "distance_m": 1000, "notes": "ritmo de 2 km + 5 s/500 m, constante"},
                {"exercise": "row", "distance_m": 1000, "notes": "piernas-cadera-brazos, ritmo constante"},
            ]},
            {"title": "Carrera final", "format": "rounds", "rounds": 1, "items": [_run(1000, pace)]},
        ],
        notes="Si la última mitad la haces más rápida que la primera, vas bien: es la pauta de carrera.",
        summary=f"{p['erg_rounds']} rondas de 1000 m de SkiErg + 1000 m de remo a ritmo constante y 1 km de carrera final",
    )


def _wb_burpees(p, w, pace):
    return dict(
        title="Wall balls y burpees",
        objective="Tolerancia a wall balls y burpee broad jumps con el pulso alto: las dos estaciones que más lo disparan.",
        warmup=[
            {"exercise": "jumping_jack", "reps": 30},
            {"exercise": "inchworm", "reps": 6, "notes": "2 series"},
            {"exercise": "squat", "reps": 10, "notes": "2 series, pausa 2 s abajo"},
            {"exercise": "wall_balls", "reps": 10, "weight_kg": w["ball"], "notes": "técnica, sin prisa"},
        ],
        blocks=[{
            "title": "Circuito", "format": "circuit", "rounds": p["rounds"], "rest_s": 120, "items": [
                {"exercise": "wall_balls", "reps": p["wb"], "weight_kg": w["ball"], "notes": "tandas de 10, respira en la bajada"},
                {"exercise": "burpee_broad_jump", "distance_m": p["bbj"]},
                {"exercise": "row", "distance_m": 250},
            ],
        }],
        notes="El objetivo es no parar a medio wall ball: tandas grandes y descansos cortos.",
        summary=f"{p['rounds']} vueltas de {p['wb']} wall balls + {p['bbj']} m de burpee broad jumps + 250 m de remo, 2' de descanso",
    )


_TEMPLATES: list[Callable[..., dict[str, Any]]] = [_compromised, _sled, _legs_grip, _ergs, _wb_burpees]
assert len(_TEMPLATES) == N_TEMPLATES


def build_session(
    division_key: str,
    *,
    variant: int,
    weeks_to_race: Optional[int],
    threshold_pace: Optional[str] = None,
) -> dict[str, Any]:
    """Una sesión de estaciones lista para guardar: {type, title, instructions, structure}.

    `variant` rota entre las plantillas (da la vuelta); `weeks_to_race` fija la fase y la carga.
    """
    p = _PHASES[_phase(weeks_to_race)]
    w = _weights(division_key, p["scale"])
    t = _TEMPLATES[variant % N_TEMPLATES](p, w, _race_pace(threshold_pace))
    return {
        "type": "hyrox_stations",
        "title": t["title"],
        "instructions": f"{t['title']}: {t['summary']}. Pesos de {w['label']}.",
        "structure": {
            "objective": t["objective"],
            "warmup": {"duration_min": 10, "steps": t["warmup"]},
            "blocks": t["blocks"],
            "cooldown": list(_COOLDOWN),
            "notes": t["notes"],
        },
    }
