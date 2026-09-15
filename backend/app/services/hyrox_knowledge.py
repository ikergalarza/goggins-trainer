"""Conocimiento HYROX orientado a rendimiento, para inyectar en los prompts.

Se inyecta SOLO cuando el objetivo activo es Hyrox (goal.type == hyrox), para
no engordar el prompt del resto de deportes. Contiene: formato oficial de
carrera, tabla de pesos por división (temporada 25/26, contrastada con el
rulebook oficial y dos fuentes), reglas de dobles, y metodología de
entrenamiento (running comprometido, pacing, tipos de sesión).

Fuentes: rulebook oficial hyrox.com 25/26; tablas de pesos verificadas en
hycrew.com y ritfitsports; reglas de dobles en roxlyfe/gymshark/puregym.
"""
from __future__ import annotations

from typing import Any, Optional

from app.models.goal import Goal
from app.models.user import User

# Orden OFICIAL de estaciones (fijo en todo el mundo). Antes de cada estación
# se corre 1 km: 8 km de carrera en total + Roxzone (la zona de transición).
STATION_ORDER = [
    {"slug": "ski_erg", "name": "SkiErg", "volume": "1000 m"},
    {"slug": "sled_push", "name": "Sled Push", "volume": "50 m (4×12,5 m)"},
    {"slug": "sled_pull", "name": "Sled Pull", "volume": "50 m (4×12,5 m)"},
    {"slug": "burpee_broad_jump", "name": "Burpee Broad Jumps", "volume": "80 m"},
    {"slug": "row", "name": "Remo", "volume": "1000 m"},
    {"slug": "farmers_carry", "name": "Farmers Carry", "volume": "200 m"},
    {"slug": "sandbag_lunges", "name": "Sandbag Lunges", "volume": "100 m"},
    {"slug": "wall_balls", "name": "Wall Balls", "volume": "100 reps"},
]

# Pesos y estándares por división — temporada 25/26.
# sled_*: peso TOTAL incluido el trineo. wall_balls: (peso, diana).
DIVISION_STANDARDS: dict[str, dict[str, Any]] = {
    "open_men":     {"label": "Open masculino",   "sled_push_kg": 152, "sled_pull_kg": 103, "farmers_kg": "2×24", "sandbag_kg": 20, "wall_ball_kg": 6, "wall_ball_target_m": 3.0, "wall_ball_reps": 100},
    "pro_men":      {"label": "Pro masculino",    "sled_push_kg": 202, "sled_pull_kg": 153, "farmers_kg": "2×32", "sandbag_kg": 30, "wall_ball_kg": 9, "wall_ball_target_m": 3.0, "wall_ball_reps": 100},
    "open_women":   {"label": "Open femenino",    "sled_push_kg": 102, "sled_pull_kg": 78,  "farmers_kg": "2×16", "sandbag_kg": 10, "wall_ball_kg": 4, "wall_ball_target_m": 2.7, "wall_ball_reps": 100},
    "pro_women":    {"label": "Pro femenino",     "sled_push_kg": 152, "sled_pull_kg": 103, "farmers_kg": "2×24", "sandbag_kg": 20, "wall_ball_kg": 6, "wall_ball_target_m": 2.7, "wall_ball_reps": 100},
    "doubles_men":  {"label": "Dobles masculino", "sled_push_kg": 152, "sled_pull_kg": 103, "farmers_kg": "2×24", "sandbag_kg": 20, "wall_ball_kg": 6, "wall_ball_target_m": 3.0, "wall_ball_reps": 100},
    "doubles_women": {"label": "Dobles femenino", "sled_push_kg": 102, "sled_pull_kg": 78,  "farmers_kg": "2×16", "sandbag_kg": 10, "wall_ball_kg": 4, "wall_ball_target_m": 2.7, "wall_ball_reps": 100},
    "doubles_mixed": {"label": "Dobles mixto",    "sled_push_kg": 152, "sled_pull_kg": 103, "farmers_kg": "2×24", "sandbag_kg": 20, "wall_ball_kg": 6, "wall_ball_target_m": 3.0, "wall_ball_reps": 100},
}


def is_hyrox_goal(goal: Optional[Goal]) -> bool:
    if goal is None:
        return False
    t = goal.type.value if hasattr(goal.type, "value") else goal.type
    if (t or "").lower() == "hyrox":
        return True
    return bool(goal.hyrox_division)


def division_key(goal: Goal, user: User) -> str:
    """Clave de división a partir de goal.hyrox_division y el sexo del usuario."""
    raw = (goal.hyrox_division or "").strip().lower()
    sex = "women" if (user.sex or "").upper() == "F" else "men"
    if "mixt" in raw or "mixed" in raw:
        return "doubles_mixed"
    if "doble" in raw or "double" in raw:
        return f"doubles_{sex}"
    if "pro" in raw:
        return f"pro_{sex}"
    return f"open_{sex}"


def _standards_text(key: str) -> str:
    s = DIVISION_STANDARDS[key]
    return (
        f"DIVISIÓN DEL ATLETA: {s['label']} (temporada 25/26)\n"
        f"- Sled Push: {s['sled_push_kg']} kg TOTAL (trineo incluido), 50 m\n"
        f"- Sled Pull: {s['sled_pull_kg']} kg TOTAL, 50 m\n"
        f"- Farmers Carry: {s['farmers_kg']} kg, 200 m\n"
        f"- Sandbag Lunges: {s['sandbag_kg']} kg, 100 m\n"
        f"- Wall Balls: {s['wall_ball_kg']} kg a diana de {s['wall_ball_target_m']} m, {s['wall_ball_reps']} reps\n"
        f"- SkiErg 1000 m · Remo 1000 m · Burpee Broad Jumps 80 m\n"
    )


KNOWLEDGE = """=== CONOCIMIENTO HYROX (rendimiento) ===

FORMATO DE CARRERA (fijo, mundial): 8 rondas de [1 km de carrera + 1 estación], en este orden:
1 SkiErg 1000 m → 2 Sled Push 50 m → 3 Sled Pull 50 m → 4 Burpee Broad Jumps 80 m → 5 Remo 1000 m → 6 Farmers Carry 200 m → 7 Sandbag Lunges 100 m → 8 Wall Balls 100 reps.
Total: 8 km corriendo + estaciones + Roxzone (la zona de transición entre carrera y estación: se RECORRE andando/trotando y puede comerse 4-8 min de carrera si no se entrena).

DOBLES (reglas de CARRERA, para estrategia): los dos corren JUNTOS los 8 km completos. En cada estación solo UNO trabaja a la vez y el reparto es libre; el que descansa permanece en la zona. El volumen total de estación es el mismo que en individual → en dobles se corre TODO pero se trabaja ~la mitad de estación con más frescura: el running pesa MÁS en el resultado.
DOBLES en el ENTRENAMIENTO: el atleta ENTRENA SOLO. NUNCA prescribas relevos, cambios de pareja, "tú vas / yo voy" ni nada que requiera un compañero presente. Las simulaciones se hacen en solitario con el volumen COMPLETO de estación (entrenar el total en solitario deja el día de carrera, con media estación, mucho más asequible). La estrategia de reparto con el compañero es tema de CHARLA (chat), no de sesiones.

PRINCIPIOS DE ENTRENAMIENTO:
1. RUNNING COMPROMETIDO (compromised running): correr con fatiga de estación es LA habilidad diferencial. Se entrena alternando estación→carrera sin descanso (p. ej. 4×[500-1000 m + estación]). El error clásico es entrenar carrera y fuerza por separado y descubrir en carrera que las piernas no responden tras el sled.
2. LAS ESTACIONES QUE DECIDEN LA CARRERA: sled push y sled pull (fuerza específica, técnica de empuje bajo y pasos cortos; es donde más tiempo pierde el amateur), wall balls al final con fatiga total (ritmo sostenible y tandas grandes: mejor 25-25-25-25 con micro-pausas que series al fallo), y sandbag lunges (cuádriceps/glúteo bajo fatiga; zancadas continuas sin apoyar rodilla con rebote).
3. ERGÓMETROS (SkiErg y remo): ritmo objetivo LIGERAMENTE conservador (~ritmo de 2 km), son las estaciones donde "ir a tope" cuesta caro después; técnica: piernas-cadera-brazos en remo, latigazo de core en ski.
4. PACING: la primera carrera SIEMPRE sale rápida por adrenalina — el objetivo es correr PLANO (mismo ritmo del km 1 al km 8, idealmente negativo). Referencia: ritmo de carrera Hyrox ≈ ritmo de 10k + 15-30 s/km por la fatiga de estaciones.
5. SEMANA TIPO (según días disponibles): 2-3 carreras (1 intervalos/umbral, 1 rodaje Z2, 1 compromised), 1-2 fuerza (empuje/tracción/piernas con transferencia: trineo, hip hinge, zancadas, carries), 1 simulación parcial o completa cada 1-2 semanas. Taper: última semana volumen -40/50% manteniendo intensidad corta.
6. FUERZA ESPECÍFICA por estación: sled → empuje pesado y arrastres; farmers → peso muerto, carries pesados, agarre; wall balls → thrusters, front squats, tandas largas de wall ball; burpee broad jump → pliometría y ritmo respiratorio (es la estación que más dispara pulsaciones).
7. CADA WOD DEBE TENER UN OBJETIVO explícito (qué cualidad ataca: umbral con fatiga, fuerza de empuje, tolerancia a wall balls, ritmo de ergómetro, práctica de relevos en dobles...) y calentamiento ESPECÍFICO de lo que viene (no "10 min genérico": movilidad de lo que se usa + activación + aproximación progresiva).
=== FIN CONOCIMIENTO HYROX ==="""


def prompt_block(goal: Goal, user: User) -> str:
    """Bloque completo para inyectar en el system prompt cuando el goal es Hyrox."""
    key = division_key(goal, user)
    return KNOWLEDGE + "\n\n" + _standards_text(key) + (
        "\nUSA SIEMPRE estos pesos y volúmenes de SU división al prescribir estaciones "
        "(en entrenamiento puede trabajarse al 70-110% del peso de competición, dilo explícitamente). "
        "NUNCA prescribas una estación sin peso/volumen concreto."
        + (
            "\nRECUERDA: aunque compite en dobles, ENTRENA SOLO — cero sesiones de relevos "
            "o con compañero; simulaciones en solitario a volumen completo."
            if key.startswith("doubles_") else ""
        )
    )


def prompt_block_for_user(user: User, db) -> str:
    """Bloque Hyrox si el usuario tiene un objetivo Hyrox ACTIVO; si no, ''."""
    goal = (
        db.query(Goal)
        .filter(Goal.user_id == user.id, Goal.is_active == True)  # noqa: E712
        .order_by(Goal.id.desc())
        .all()
    )
    for g in goal:
        if is_hyrox_goal(g):
            return prompt_block(g, user)
    return ""
