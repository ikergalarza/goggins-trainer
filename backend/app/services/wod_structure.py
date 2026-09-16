"""Formato estructurado de un WOD y su validación.

`Workout.structure` guarda el WOD como datos (objetivo, calentamiento, bloques
con ejercicios/dosis/pesos, enfriamiento) en vez de un párrafo de texto. La IA
lo emite siguiendo PROMPT_SPEC y aquí se sanea antes de persistir: la UI pinta
lo que haya aquí, así que nada raro debe llegar a la base de datos.
"""
from __future__ import annotations

from typing import Any, Optional

# Ejercicios canónicos que la UI sabe pintar (pictograma + nombre es-ES).
# "other" exige `name`. Mantener en sintonía con frontend/src/components/exercises/catalog.ts
EXERCISES = {
    "run", "ski_erg", "sled_push", "sled_pull", "burpee_broad_jump", "row",
    "farmers_carry", "sandbag_lunges", "wall_balls", "burpee", "squat",
    "front_squat", "thruster", "deadlift", "kb_swing", "box_jump", "press",
    "pull_up", "plank", "carry", "bike_erg", "mobility", "other",
    # Movilidad / calentamiento (cada uno con ficha y pictograma en la app)
    "ninety_ninety", "cat_camel", "glute_bridge", "hip_flexor_stretch",
    "thoracic_opener", "dead_bug", "bird_dog", "cossack_squat", "leg_swing",
    "inchworm", "worlds_greatest", "ankle_rock", "lunge", "jumping_jack",
}

FORMATS = {"rounds", "amrap", "fortime", "emom", "sets", "circuit"}

PROMPT_SPEC = """FORMATO ESTRUCTURADO DEL WOD (campo `structure` de cada workout):
Los workouts de tipo hyrox_sim, hyrox_stations, strength_upper, strength_lower, strength_full, mobility y recovery DEBEN llevar, además de `instructions` (1-2 frases), un campo `structure`:
{
  "objective": "qué cualidad ataca hoy y por qué, en 1 frase (p. ej. 'Tolerancia a wall balls con pulso alto tras carrera')",
  "warmup": {"duration_min": 10, "steps": [
    {"exercise": "row", "distance_m": 500, "notes": "suave, progresivo"},
    {"exercise": "squat", "reps": 10, "notes": "2 series, pausa 3s abajo"},
    {"exercise": "glute_bridge", "reps": 15, "notes": "2 series"},
    {"exercise": "sled_push", "distance_m": 12, "weight_kg": 76, "notes": "2 aproximaciones al 50%"}
  ]},
  "blocks": [
    {"title": "Bloque principal", "format": "rounds", "rounds": 4, "rest_s": 120,
     "items": [
       {"exercise": "run", "distance_m": 400, "pace": "4:40/km"},
       {"exercise": "wall_balls", "reps": 15, "weight_kg": 6},
       {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152}
     ]}
  ],
  "cooldown": ["5' trote muy suave", "estiramiento de cuádriceps y glúteo"],
  "notes": "consejo táctico opcional (transiciones, respiración, ritmo)"
}
REGLAS del structure:
- `exercise` SOLO de: run, ski_erg, sled_push, sled_pull, burpee_broad_jump, row, farmers_carry, sandbag_lunges, wall_balls, burpee, squat, front_squat, thruster, deadlift, kb_swing, box_jump, press, pull_up, plank, carry, bike_erg, mobility, other. Con "other" añade "name".
- CADA item lleva su dosis: `reps` o `distance_m` o `duration_s`; y `weight_kg` SIEMPRE que el ejercicio sea con carga (usa los pesos de la división del atleta; si entrenas por encima o debajo del peso de competición, dilo en notes).
- `format`: "rounds" (con `rounds`), "amrap" (con `duration_min`), "emom" (con `interval_s` y `duration_min`), "fortime", "sets" (con `rounds` = nº de series), "circuit" (con `rounds` = nº de vueltas). `rest_s` = descanso entre rondas/series.
- OBLIGATORIO: todo bloque "rounds", "sets" o "circuit" lleva `rounds`. Un bloque de fuerza de 4 series de 6 peso muerto se escribe: format "sets", rounds 4, item {"exercise": "deadlift", "reps": 6, "weight_kg": ...}. NUNCA un bloque de fuerza con una sola pasada implícita: si de verdad es 1 serie, pon rounds 1 explícito.
- El calentamiento es ESPECÍFICO del trabajo del día (movilidad de lo que se usa + activación + aproximación progresiva), nunca "10 min genérico". Cada paso del calentamiento (y de los bloques de movilidad) que sea un ejercicio identificable va como objeto {exercise, reps|duration_s|distance_m, notes} usando los slugs de la lista — la app muestra su ficha con dibujo y vídeo. Texto libre solo para indicaciones que no son un ejercicio ("sube pulsaciones andando rápido").
- Slugs de movilidad disponibles: ninety_ninety (90-90 de cadera), cat_camel (gato-camello), glute_bridge (puente de glúteo), hip_flexor_stretch (flexor de cadera en zancada), thoracic_opener (apertura torácica), dead_bug (bicho muerto), bird_dog (perro-pájaro), cossack_squat (sentadilla cosaca), leg_swing (balanceo de pierna), inchworm (oruga), worlds_greatest (el mejor estiramiento del mundo), ankle_rock (movilidad de tobillo contra pared), lunge (zancada), jumping_jack.
- `objective` NUNCA vacío."""

_ITEM_KEYS = {"exercise", "name", "reps", "distance_m", "duration_s", "weight_kg", "pace", "target_m", "notes"}
_INT_KEYS = {"reps", "distance_m", "duration_s"}


def _clean_str(v: Any, max_len: int) -> Optional[str]:
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v[:max_len] if v else None


def _clean_num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v < 0 or v > 100000:
        return None
    return v


def _clean_item(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    ex = raw.get("exercise")
    if ex not in EXERCISES:
        # Ejercicio desconocido: lo conservamos como "other" con su nombre,
        # mejor que perder la línea del WOD.
        name = _clean_str(raw.get("name") or (ex if isinstance(ex, str) else None), 80)
        if not name:
            return None
        item: dict[str, Any] = {"exercise": "other", "name": name}
    else:
        item = {"exercise": ex}
        name = _clean_str(raw.get("name"), 80)
        if name:
            item["name"] = name
    for k in _ITEM_KEYS - {"exercise", "name"}:
        v = raw.get(k)
        if v is None:
            continue
        if k in ("pace", "notes"):
            s = _clean_str(v, 120)
            if s:
                item[k] = s
        else:
            n = _clean_num(v)
            if n is not None:
                item[k] = int(n) if k in _INT_KEYS else n
    return item


def sanitize(raw: Any) -> Optional[dict[str, Any]]:
    """Devuelve el structure saneado, o None si no hay nada utilizable."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}

    obj = _clean_str(raw.get("objective"), 300)
    if obj:
        out["objective"] = obj

    wu = raw.get("warmup")
    if isinstance(wu, dict):
        # Pasos: texto libre ("sube pulsaciones") o ejercicio identificable
        # ({exercise, reps...}) — la UI muestra ficha y pictograma de estos.
        steps: list[Any] = []
        for x in (wu.get("steps") or [])[:20]:
            if isinstance(x, dict):
                item = _clean_item(x)
                if item:
                    steps.append(item)
            else:
                txt = _clean_str(x, 200)
                if txt:
                    steps.append(txt)
        clean_wu: dict[str, Any] = {}
        dur = _clean_num(wu.get("duration_min"))
        if dur:
            clean_wu["duration_min"] = int(dur)
        if steps:
            clean_wu["steps"] = steps
        if clean_wu:
            out["warmup"] = clean_wu

    blocks = []
    for b in (raw.get("blocks") or [])[:12]:
        if not isinstance(b, dict):
            continue
        items = [i for i in (_clean_item(x) for x in (b.get("items") or [])[:20]) if i]
        if not items:
            continue
        cb: dict[str, Any] = {"items": items}
        title = _clean_str(b.get("title"), 80)
        if title:
            cb["title"] = title
        fmt = b.get("format")
        cb["format"] = fmt if fmt in FORMATS else "rounds"
        for k in ("rounds", "rest_s", "duration_min", "interval_s"):
            n = _clean_num(b.get(k))
            if n:
                cb[k] = int(n)
        blocks.append(cb)
    if blocks:
        out["blocks"] = blocks

    cd = [s for s in (_clean_str(x, 200) for x in (raw.get("cooldown") or [])[:10]) if s]
    if cd:
        out["cooldown"] = cd
    notes = _clean_str(raw.get("notes"), 500)
    if notes:
        out["notes"] = notes

    # Sin bloques no hay WOD estructurado que pintar.
    return out if out.get("blocks") else None
