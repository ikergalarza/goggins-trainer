"""Plantillas de WOD de Hyrox: sesiones completas al instante, en el servidor.

Una auditoría del plan real marcó el estándar: las sesiones salían de ~29 min de
trabajo, con 2 estaciones en un único circuito, casi iguales en días seguidos y
con trineo pesado 48 h antes de un simulacro. Aquí cada sesión normal dura ~1 h,
tiene 3 bloques, 3+ estaciones y 2+ km de carrera; antes de un simulacro toca
una activación ligera, al final una descarga corta, y `choose_variant` evita
repetir una estación pesada junto a la sesión de al lado. Además:
  - pesos de la división del atleta (temporada 25/26, `hyrox_knowledge`),
  - ritmo de carrera desde su umbral (+18 s/km en base, +13 construyendo, +8 específico),
  - siempre en SOLITARIO (el atleta entrena solo: cero relevos).
La duración sale de `wod_duration`, a partir del propio WOD.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Optional

from app.services import hyrox_knowledge, wod_duration

STATIONS = {"ski_erg", "sled_push", "sled_pull", "burpee_broad_jump", "row", "farmers_carry", "sandbag_lunges", "wall_balls"}
HEAVY = {"sled_push", "sled_pull", "sandbag_lunges", "burpee_broad_jump"}

N_TEMPLATES = 4
_HEAVY_BY_VARIANT = [
    {"sled_push", "sled_pull"},
    {"sandbag_lunges", "burpee_broad_jump"},
    {"sandbag_lunges", "burpee_broad_jump"},
    {"sled_push", "sled_pull", "burpee_broad_jump"},
]

_PHASES: dict[str, dict[str, int]] = {
    "base":  {"margin": 18, "main": 3, "wb": 20, "bbj": 20, "final_wb": 50},
    "build": {"margin": 13, "main": 4, "wb": 25, "bbj": 20, "final_wb": 60},
    "peak":  {"margin": 8,  "main": 4, "wb": 25, "bbj": 25, "final_wb": 75},
}
_ACTIVATION_LOAD = 0.6
_COOLDOWN = ["6' trote muy suave", "movilidad de cadera, cuádriceps y gemelo (30'' por lado)"]


def _phase(weeks_to_race: Optional[int]) -> str:
    if weeks_to_race is None or weeks_to_race > 8:
        return "base"
    return "build" if weeks_to_race >= 4 else "peak"


def _round5(x: float) -> int:
    return int(round(x / 5) * 5)


def _race_pace(threshold_pace: Optional[str], margin_s: int) -> Optional[str]:
    """Ritmo de las carreras comprometidas: umbral + margen, como 'm:ss/km'. None si no hay ritmo válido."""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", threshold_pace or "")
    if not m:
        return None
    sec = int(m.group(1)) * 60 + int(m.group(2)) + margin_s
    return f"{sec // 60}:{sec % 60:02d}/km"


def _weights(division_key: str) -> dict[str, Any]:
    std = hyrox_knowledge.DIVISION_STANDARDS.get(division_key) or hyrox_knowledge.DIVISION_STANDARDS["open_men"]
    per_hand = re.search(r"(\d+)\s*$", str(std["farmers_kg"]))
    return {
        "push": std["sled_push_kg"],
        "pull": std["sled_pull_kg"],
        "farmers": int(per_hand.group(1)) if per_hand else 24,
        "farmers_label": std["farmers_kg"],
        "sandbag": std["sandbag_kg"],
        "ball": std["wall_ball_kg"],
        "label": std["label"],
    }


# ── Piezas ───────────────────────────────────────────────────────────────────

class _Kit:
    """Construye los items con los pesos de la división y el ritmo de la fase."""

    def __init__(self, w: dict[str, Any], pace: Optional[str]):
        self.w, self.pace = w, pace

    def run(self, m: int) -> dict[str, Any]:
        item: dict[str, Any] = {"exercise": "run", "distance_m": m}
        if self.pace:
            item["pace"] = self.pace
        return item

    def push(self, m: int, load: float = 1.0, notes: str = "pasos cortos, tronco bajo") -> dict[str, Any]:
        kg = self.w["push"] if load >= 1 else _round5(self.w["push"] * load)
        return {"exercise": "sled_push", "distance_m": m, "weight_kg": kg, "notes": notes}

    def pull(self, m: int, load: float = 1.0, notes: str = "mano sobre mano, caderas abajo") -> dict[str, Any]:
        kg = self.w["pull"] if load >= 1 else _round5(self.w["pull"] * load)
        return {"exercise": "sled_pull", "distance_m": m, "weight_kg": kg, "notes": notes}

    def bbj(self, m: int) -> dict[str, Any]:
        return {"exercise": "burpee_broad_jump", "distance_m": m, "notes": "ritmo de respiración constante"}

    def farm(self, m: int) -> dict[str, Any]:
        return {"exercise": "farmers_carry", "distance_m": m, "weight_kg": self.w["farmers"],
                "notes": f"{self.w['farmers_label']} kg, sin soltar si puedes"}

    def lunge(self, m: int) -> dict[str, Any]:
        return {"exercise": "sandbag_lunges", "distance_m": m, "weight_kg": self.w["sandbag"],
                "notes": "zancadas continuas, tronco erguido"}

    def wb(self, reps: int, notes: str = "tandas largas con micro-pausas") -> dict[str, Any]:
        return {"exercise": "wall_balls", "reps": reps, "weight_kg": self.w["ball"], "notes": notes}

    def ski(self, m: int) -> dict[str, Any]:
        return {"exercise": "ski_erg", "distance_m": m, "notes": "ritmo de 2 km, constante"}

    def row(self, m: int) -> dict[str, Any]:
        return {"exercise": "row", "distance_m": m, "notes": "piernas-cadera-brazos"}

    def warmup(self, kind: str) -> list[dict[str, Any]]:
        if kind == "sled":
            return [{"exercise": "row", "distance_m": 500, "notes": "suave, progresivo"},
                    {"exercise": "hip_flexor_stretch", "duration_s": 40, "notes": "cada lado"},
                    {"exercise": "glute_bridge", "reps": 15, "notes": "2 series"},
                    {"exercise": "inchworm", "reps": 6},
                    {"exercise": "sled_push", "distance_m": 12, "weight_kg": _round5(self.w["push"] * 0.5), "notes": "2 aproximaciones al 50%"}]
        if kind == "legs":
            return [{"exercise": "row", "distance_m": 500, "notes": "suave, progresivo"},
                    {"exercise": "ninety_ninety", "duration_s": 60, "notes": "cada lado"},
                    {"exercise": "cossack_squat", "reps": 8, "notes": "cada lado"},
                    {"exercise": "lunge", "reps": 10, "notes": "sin carga, cada pierna"},
                    {"exercise": "wall_balls", "reps": 10, "weight_kg": self.w["ball"], "notes": "técnica"}]
        if kind == "erg":
            return [{"exercise": "thoracic_opener", "reps": 8, "notes": "cada lado"},
                    {"exercise": "leg_swing", "reps": 10, "notes": "cada pierna"},
                    {"exercise": "ski_erg", "distance_m": 250, "notes": "progresivo"},
                    {"exercise": "row", "distance_m": 250, "notes": "progresivo"},
                    {"exercise": "jumping_jack", "reps": 30}]
        return [{"exercise": "run", "distance_m": 800, "notes": "trote suave"},
                {"exercise": "worlds_greatest", "reps": 5, "notes": "cada lado"},
                {"exercise": "glute_bridge", "reps": 12},
                {"exercise": "run", "distance_m": 80, "notes": "3 progresivos"}]


def _block(title: str, rounds: int, items: list[dict[str, Any]], rest: int = 0) -> dict[str, Any]:
    b: dict[str, Any] = {"title": title, "format": "rounds", "rounds": rounds, "items": items}
    if rest:
        b["rest_s"] = rest
    return b


# ── Plantillas ───────────────────────────────────────────────────────────────

def _sled(k: _Kit, p: dict[str, int]):
    return ("Trineo comprometido",
            "Correr con las piernas cargadas por el empuje y la tracción: la habilidad que más tiempo da.",
            "sled",
            [_block("Sled push + carrera", p["main"] + (1 if p["margin"] <= 8 else 0), [k.push(25), k.run(600)], 90),
             _block("Sled pull + SkiErg", p["main"], [k.pull(25), k.ski(250)], 75),
             _block("Remate", 2, [k.wb(20), k.run(400)], 60)],
            "El primer km tras el trineo es el que se entrena: no regales ritmo.",
            "sled push + carrera, sled pull + SkiErg y remate de wall balls")


def _legs(k: _Kit, p: dict[str, int]):
    return ("Piernas y agarre",
            "Zancadas, farmers y wall balls con carrera entre medias: cuádriceps, glúteo y agarre bajo fatiga.",
            "legs",
            [_block("Carrera + zancadas", p["main"], [k.run(800), k.lunge(30)], 90),
             _block("Farmers + wall balls + remo", 3, [k.farm(80), k.wb(p["wb"]), k.row(250)], 75),
             _block("Remate", 2, [k.bbj(20), k.run(400)], 60)],
            "Si el agarre se rinde antes que las piernas, ese es el punto débil: apúntalo.",
            "carrera + zancadas, farmers + wall balls + remo y remate de burpees")


def _engine(k: _Kit, p: dict[str, int]):
    return ("Motor y ergómetros",
            "Remo y SkiErg a ritmo sostenible y estaciones de piernas sin reventar.",
            "erg",
            [_block("Ergómetros + carrera", 3, [k.row(500), k.run(800), k.ski(500)], 90),
             _block("Estaciones", 3, [k.lunge(30), k.bbj(15), k.farm(80)], 75),
             _block("Final", 1, [k.wb(p["final_wb"], "en las menos tandas posibles")])],
            "En remo y ski guarda: si vas a tope aquí, lo pagas en las zancadas.",
            "remo + carrera + SkiErg, zancadas + burpees + farmers y wall balls finales")


def _race_pieces(k: _Kit, p: dict[str, int]):
    return ("Estaciones a ritmo de carrera",
            "Kilómetros a ritmo de carrera con el trineo entre medias, y burpees y wall balls con el pulso alto.",
            "sled",
            [_block("Km + trineo", 2, [k.run(1000), k.push(25), k.run(1000), k.pull(25)], 120),
             _block("Burpees + SkiErg", 3, [k.bbj(p["bbj"]), k.ski(300)], 75),
             _block("Final", 1, [k.wb(min(p["final_wb"], 50))])],
            "Ensaya las transiciones: entra y sal de cada estación sin pararte a pensar.",
            "2 × (km + sled push + km + sled pull), burpees con SkiErg y wall balls")


_TEMPLATES = [_sled, _legs, _engine, _race_pieces]
assert len(_TEMPLATES) == N_TEMPLATES == len(_HEAVY_BY_VARIANT)


def _activation(k: _Kit, p: dict[str, int]):
    return ("Activación pre-simulacro",
            "Soltar antes del simulacro: ritmo y técnica sin fatigar las piernas.",
            "act",
            [_block("Carrera + remo + wall balls", 3, [k.run(600), k.row(200), k.wb(12)], 90),
             _block("Técnica de trineo", 2, [k.push(12, _ACTIVATION_LOAD, "técnica"), k.pull(12, _ACTIVATION_LOAD, "técnica")], 60)],
            "Nada de heroicidades: el trabajo duro es el simulacro.",
            "carrera + remo + wall balls y técnica ligera de trineo")


def _taper(k: _Kit, p: dict[str, int]):
    return ("Descarga",
            "Mantener ritmo de carrera y tacto de las estaciones con poco volumen.",
            "sled",
            [_block("Carrera + push + wall balls", 3, [k.run(800), k.push(25), k.wb(15)], 90),
             _block("Pull + SkiErg + burpees", 2, [k.pull(25), k.ski(250), k.bbj(15)], 75)],
            "Descarga: acaba con ganas de más.",
            "carrera + sled push + wall balls y sled pull + SkiErg + burpees")


def build_session(
    division_key: str,
    *,
    variant: int,
    weeks_to_race: Optional[int],
    threshold_pace: Optional[str] = None,
    kind: str = "full",
) -> dict[str, Any]:
    """Una sesión de estaciones lista para guardar: {type, title, instructions, distance_km, structure}.

    `kind`: "full" (rota entre plantillas con `variant`), "activation" (antes de un
    simulacro) o "taper" (descarga). `weeks_to_race` fija la fase y la carga.
    """
    p = _PHASES[_phase(weeks_to_race)]
    k = _Kit(_weights(division_key), _race_pace(threshold_pace, p["margin"]))
    maker = {"activation": _activation, "taper": _taper}.get(kind) or _TEMPLATES[variant % N_TEMPLATES]
    title, objective, warm, blocks, notes, summary = maker(k, p)
    run_m = sum(i.get("distance_m", 0) * b["rounds"] for b in blocks for i in b["items"] if i["exercise"] == "run")
    return {
        "type": "hyrox_stations",
        "title": title,
        "instructions": f"{title}: {summary}. Pesos de {k.w['label']}.",
        "distance_km": round(run_m / 1000, 1),
        "structure": {
            "objective": objective,
            "warmup": {"duration_min": 12 if kind == "full" else 10, "steps": k.warmup(warm if kind == "full" else "act")},
            "blocks": blocks,
            "cooldown": list(_COOLDOWN),
            "notes": notes,
        },
    }


# ── Elegir según lo que hay alrededor ───────────────────────────────────────

def stations_of(structure: Any) -> set[str]:
    if not isinstance(structure, dict):
        return set()
    return {
        i.get("exercise") for b in (structure.get("blocks") or []) if isinstance(b, dict)
        for i in (b.get("items") or []) if isinstance(i, dict) and i.get("exercise") in STATIONS
    }


def choose_kind(d: date, neighbors: Iterable[tuple[date, str, Any]], weeks_to_race: Optional[int]) -> str:
    """`neighbors`: (fecha, tipo, structure) de otras sesiones de Hyrox cercanas."""
    if any(t == "hyrox_sim" and 0 < (nd - d).days <= 2 for nd, t, _ in neighbors):
        return "activation"
    if weeks_to_race is not None and weeks_to_race <= 1:
        return "taper"
    return "full"


def choose_variant(d: date, neighbors: Iterable[tuple[date, str, Any]], index: int) -> int:
    """La plantilla que menos repite estaciones pesadas con las sesiones a ±2 días; a igualdad, rota."""
    near: set[str] = set()
    for nd, t, structure in neighbors:
        if t != "hyrox_sim" and 0 < abs((nd - d).days) <= 2:
            near |= stations_of(structure) & HEAVY
    order = [(index + i) % N_TEMPLATES for i in range(N_TEMPLATES)]
    return min(order, key=lambda v: len(_HEAVY_BY_VARIANT[v] & near))


def is_thin(structure: Any) -> bool:
    """True si una sesión de estaciones se queda corta: menos de 3 estaciones o de ~50 min."""
    if not isinstance(structure, dict) or not structure.get("blocks"):
        return True
    est = wod_duration.estimate(structure)
    return len(stations_of(structure)) < 3 or not est or est["total_min"] < 50
