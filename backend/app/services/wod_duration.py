"""Cuánto dura un WOD estructurado, calculado desde su contenido.

Antes la duración (`planned_duration_min`) era un número que la IA escribía a
ojo: nada lo ataba a lo que el WOD contiene y tendía a redondear hacia la "hora
de gimnasio" (55-60') aunque el trabajo real fuese de ~40'. Aquí se calcula
sumando calentamiento + bloques (con sus descansos) + vuelta a la calma, con
tiempos por ejercicio de un atleta intermedio entrenando.

La MISMA tabla de tiempos alimenta el prompt de la IA (para que dimensione las
sesiones con cabeza) y este estimador (para que el número mostrado sea honesto),
así que no pueden desincronizarse.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Tiempos de referencia (atleta intermedio, entrenando) ────────────────────
# Segundos por metro.
_S_PER_M: dict[str, float] = {
    "ski_erg": 0.26,            # 1000 m ≈ 4:20
    "row": 0.25,                # 1000 m ≈ 4:10
    "bike_erg": 0.12,           # 1000 m ≈ 2:00
    "burpee_broad_jump": 3.75,  # 80 m ≈ 5:00
    "farmers_carry": 0.6,       # 200 m ≈ 2:00
    "carry": 0.6,
    "sandbag_lunges": 2.4,      # 100 m ≈ 4:00
    "lunge": 2.5,
}
# Segundos por repetición.
_S_PER_REP: dict[str, float] = {
    "wall_balls": 3.0,          # 100 reps ≈ 5:00
    "burpee": 3.5,
    "squat": 4.0,
    "front_squat": 4.0,
    "thruster": 3.5,
    "deadlift": 4.0,
    "kb_swing": 2.2,
    "box_jump": 3.5,
    "press": 4.0,
    "pull_up": 4.0,
    "lunge": 2.5,
    "sandbag_lunges": 2.4,
    "jumping_jack": 1.0,
}
_DEFAULT_REP_S = 3.5            # ejercicio sin tabla, con repeticiones
_DEFAULT_M_S = 1.2              # ejercicio sin tabla, con distancia
_DEFAULT_ITEM_S = 40            # item sin dosis medible
_DEFAULT_RUN_PACE_S_KM = 320    # 5:20/km si el item no trae ritmo
_DEFAULT_SLED_KG = 100

_TRANSITION_S = 8               # entre ejercicios (colocarse, coger el material)
_BLOCK_SETUP_S = 30             # al cambiar de bloque (cargar discos, cambiar de zona)
_DEFAULT_SETS_REST_S = 90       # series de fuerza sin descanso declarado

_WARMUP_RANGE = (4, 15)
_COOLDOWN_RANGE = (3, 12)
_COOLDOWN_DEFAULT_MIN = 5
# Fuera de este rango no nos fiamos del cálculo (WOD roto) y no se toca el número.
_MIN_TOTAL, _MAX_TOTAL = 8, 180

_PACE_RE = re.compile(r"(\d{1,2}):(\d{2})")
# "5'" o "10 min" cuentan como minutos; "30''" (segundos) no.
_MINUTES_RE = re.compile(r"(\d+)\s*(?:'(?!')|’(?!’)|min)")


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def _sled_s_per_m(exercise: str, weight_kg: Optional[float]) -> float:
    w = weight_kg if weight_kg else _DEFAULT_SLED_KG
    if exercise == "sled_pull":
        return 1.8 + w / 50      # 103 kg → 3,86 s/m
    return 1.2 + w / 110         # 152 kg → 2,58 s/m


def _pace_s_per_km(pace: Any) -> int:
    if isinstance(pace, str):
        m = _PACE_RE.search(pace)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
    return _DEFAULT_RUN_PACE_S_KM


def item_seconds(it: dict[str, Any]) -> float:
    """Segundos que lleva UNA pasada de un ejercicio (sin descanso ni transición)."""
    ex = it.get("exercise")
    dur = _num(it.get("duration_s"))
    if dur:
        return dur
    dist = _num(it.get("distance_m"))
    reps = _num(it.get("reps"))
    w = _num(it.get("weight_kg"))

    if ex == "run" and dist:
        return dist / 1000 * _pace_s_per_km(it.get("pace"))
    if ex in ("sled_push", "sled_pull") and dist:
        return dist * _sled_s_per_m(ex, w)
    if dist and ex in _S_PER_M:
        return dist * _S_PER_M[ex]
    if reps:
        return reps * _S_PER_REP.get(ex, _DEFAULT_REP_S)
    if dist:
        return dist * _DEFAULT_M_S
    return _DEFAULT_ITEM_S


def _block_seconds(b: dict[str, Any]) -> float:
    items = [i for i in (b.get("items") or []) if isinstance(i, dict)]
    if not items:
        return 0.0
    per_pass = sum(item_seconds(i) for i in items) + _TRANSITION_S * len(items)
    fmt = b.get("format") or "rounds"
    rounds = int(_num(b.get("rounds")) or 1)
    rest = _num(b.get("rest_s"))
    clock = _num(b.get("duration_min"))

    # Bloques a reloj: duran lo que dicen.
    if fmt == "amrap":
        return clock * 60 if clock else per_pass * rounds
    if fmt == "emom":
        if clock:
            return clock * 60
        interval = _num(b.get("interval_s"))
        return interval * rounds if interval else per_pass * rounds

    if rest is None:
        rest = _DEFAULT_SETS_REST_S if fmt == "sets" else 0
    return rounds * per_pass + max(rounds - 1, 0) * rest + _BLOCK_SETUP_S


def _warmup_minutes(wu: Any) -> int:
    if not isinstance(wu, dict):
        return 0
    declared = _num(wu.get("duration_min"))
    lo, hi = _WARMUP_RANGE
    if declared:
        return int(min(max(round(declared), lo), hi))
    steps = wu.get("steps") or []
    if not steps:
        return 0
    secs = sum(item_seconds(s) if isinstance(s, dict) else _DEFAULT_ITEM_S for s in steps)
    return int(min(max(round((secs + 120) / 60), lo), hi))


def _cooldown_minutes(cd: Any) -> int:
    if not isinstance(cd, list) or not cd:
        return 0
    minutes = 0
    for s in cd:
        if isinstance(s, str):
            minutes += sum(int(m) for m in _MINUTES_RE.findall(s))
    lo, hi = _COOLDOWN_RANGE
    return int(min(max(minutes or _COOLDOWN_DEFAULT_MIN, lo), hi))


def estimate(structure: Any) -> Optional[dict[str, int]]:
    """Reparto del tiempo de un WOD: {warmup_min, work_min, cooldown_min, total_min}.

    None si no hay un WOD calculable (sin bloques, o datos que no son un WOD).
    Nunca lanza: un structure raro no debe romper la generación del plan.
    """
    try:
        if not isinstance(structure, dict):
            return None
        blocks = [b for b in (structure.get("blocks") or []) if isinstance(b, dict)]
        work_s = sum(_block_seconds(b) for b in blocks)
        if not work_s:
            return None
        warmup = _warmup_minutes(structure.get("warmup"))
        work = max(1, round(work_s / 60))
        cooldown = _cooldown_minutes(structure.get("cooldown"))
        return {
            "warmup_min": warmup,
            "work_min": work,
            "cooldown_min": cooldown,
            "total_min": warmup + work + cooldown,
        }
    except Exception as e:  # pragma: no cover - red de seguridad
        logger.warning(f"[wod_duration] no se pudo estimar: {e}")
        return None


def apply_to_workout(w: Any) -> bool:
    """Fija `planned_duration_min` desde el WOD del workout y guarda el reparto en
    `structure["estimate"]` (la UI lo enseña). False si no hay WOD calculable.

    Reasigna el dict entero: SQLAlchemy no ve mutaciones dentro de una columna JSON.
    """
    s = w.structure
    if not isinstance(s, dict):
        return False
    est = estimate(s)
    if est is None or not (_MIN_TOTAL <= est["total_min"] <= _MAX_TOTAL):
        return False
    w.structure = {**{k: v for k, v in s.items() if k != "estimate"}, "estimate": est}
    w.planned_duration_min = est["total_min"]
    return True


def backfill(db: Any) -> int:
    """Corrige los planes YA generados: recalcula lo planificado con WOD que aún no
    lleva `estimate`. Lo completado/saltado es historia y no se toca. Idempotente.
    Devuelve cuántos workouts cambió (sin commit propio si es 0)."""
    from app.models.workout import Workout, WorkoutStatus

    changed = 0
    rows = db.query(Workout).filter(Workout.status == WorkoutStatus.planned).all()
    for w in rows:
        if isinstance(w.structure, dict) and "estimate" not in w.structure:
            if apply_to_workout(w):
                changed += 1
    if changed:
        db.commit()
    return changed


# ── Referencia para el prompt de la IA (sale de la misma tabla) ──────────────

def _mmss(seconds: float) -> str:
    s = int(round(seconds / 5) * 5)
    return f"{s // 60}:{s % 60:02d}"


def _ref(exercise: str, **dose: Any) -> str:
    return _mmss(item_seconds({"exercise": exercise, **dose}))


PROMPT_REFERENCE = (
    "TIEMPOS DE REFERENCIA (atleta intermedio entrenando; la app los usa para calcular la duración real de cada sesión):\n"
    f"- SkiErg 1000 m ≈ {_ref('ski_erg', distance_m=1000)} · Remo 1000 m ≈ {_ref('row', distance_m=1000)} · "
    f"carrera a su `pace` (si no hay, ~{_mmss(_DEFAULT_RUN_PACE_S_KM)}/km)\n"
    f"- Sled Push 50 m (152 kg) ≈ {_ref('sled_push', distance_m=50, weight_kg=152)} · "
    f"Sled Pull 50 m (103 kg) ≈ {_ref('sled_pull', distance_m=50, weight_kg=103)} · "
    f"Farmers Carry 200 m ≈ {_ref('farmers_carry', distance_m=200)}\n"
    f"- Burpee Broad Jumps 80 m ≈ {_ref('burpee_broad_jump', distance_m=80)} · "
    f"Sandbag Lunges 100 m ≈ {_ref('sandbag_lunges', distance_m=100)} · "
    f"Wall Balls 100 reps ≈ {_ref('wall_balls', reps=100)}\n"
    f"- Fuerza: ~{_S_PER_REP['deadlift']:.0f} s por repetición, más el descanso entre series/rondas (`rest_s`). "
    f"Entre ejercicios ~{_TRANSITION_S} s de transición y ~{_BLOCK_SETUP_S} s al cambiar de bloque.\n"
    "DURACIÓN (`duration_min` del workout) = reloj TOTAL de la sesión: calentamiento + bloques (con sus descansos) + "
    "vuelta a la calma. Súmala con estos tiempos: NO la redondees hacia arriba \"por si acaso\" ni la acerques a una "
    "\"hora de gimnasio\" por defecto. La app recalcula este número desde el `structure`, así que lo que importa es "
    "dimensionar el WOD para el tiempo que quieres que dure (si el atleta dice de cuánto tiempo dispone, ajústalo a eso)."
)
