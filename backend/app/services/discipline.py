"""Clasificación de actividades de Strava por disciplina deportiva.

Strava etiqueta cada actividad con un `type` textual (Run, Ride, Swim,
WeightTraining, Workout, Kitesurf...). Para separar estadísticas por deporte
reducimos esa variedad a un conjunto cerrado de disciplinas.

A diferencia del mapeo de triatlón de `plan_generator` (que solo mira
swim/bike/run y descarta el resto), aquí SIEMPRE se devuelve una disciplina:
las sesiones de fuerza no tienen distancia y quedarían invisibles si las
descartáramos — el tiempo y el número de sesiones son su única huella — y
cualquier otro deporte cae en "other" para que el total semanal siga
cuadrando con la suma de sus partes.
"""

DISCIPLINES = ("run", "bike", "swim", "strength", "other")

# Tipos de Strava que son trabajo de fuerza/funcional: no suman km pero sí
# tiempo y sesiones. "Workout" es el genérico que usan la mayoría de apps de
# gimnasio (y los Hyrox/circuitos) al exportar a Strava.
_STRENGTH_TYPES = {"weighttraining", "workout", "crossfit", "hiit"}


def discipline_for_strava_type(strava_type: str | None) -> str:
    """Mapea el `type` de Strava a una de las disciplinas de `DISCIPLINES`.

    Nunca devuelve None: lo desconocido o vacío cae en "other" para que
    ninguna actividad desaparezca de las estadísticas (en especial la
    fuerza, que sin distancia sería invisible si solo contáramos km).
    """
    if not strava_type:
        return "other"
    t = strava_type.lower()
    if "swim" in t:
        return "swim"
    if t in ("run", "trailrun", "virtualrun") or "run" in t:
        return "run"
    if t in ("ride", "virtualride", "ebikeride", "gravelride", "mountainbikeride") or "ride" in t or "bike" in t:
        return "bike"
    if t in _STRENGTH_TYPES:
        return "strength"
    return "other"


# --- Disciplina de un WORKOUT planificado ----------------------------------
# Los tipos de workout (WorkoutType) son más finos que las disciplinas: aquí
# se reducen al mismo conjunto para poder emparejar un workout con una
# actividad de Strava del MISMO deporte (una carrera nunca debe cerrar una
# sesión de movilidad).
_WORKOUT_RUN = {
    "easy_run", "tempo", "intervals", "long_run", "recovery", "fartlek",
    "hill_repeats", "cross_training",
}
_WORKOUT_SWIM = {"swim", "swim_technique", "open_water"}
_WORKOUT_BIKE = {"bike"}
_WORKOUT_STRENGTH = {
    "hyrox_sim", "hyrox_stations", "strength_upper", "strength_lower",
    "strength_full", "mobility",
}
# Brick y transiciones encadenan bici + carrera: aceptan actividad de cualquiera.
_WORKOUT_BRICK = {"brick", "transition"}


def discipline_for_workout_type(workout_type: str | None) -> str | None:
    """Disciplina de un tipo de workout, o None si no se empareja (descanso)."""
    if not workout_type:
        return None
    t = str(workout_type).lower()
    # Acepta tanto "easy_run" como "WorkoutType.easy_run".
    if "." in t:
        t = t.rsplit(".", 1)[1]
    if t in _WORKOUT_RUN:
        return "run"
    if t in _WORKOUT_SWIM:
        return "swim"
    if t in _WORKOUT_BIKE:
        return "bike"
    if t in _WORKOUT_STRENGTH:
        return "strength"
    if t in _WORKOUT_BRICK:
        return "brick"
    return None


def activity_matches_workout(strava_type: str | None, workout_type: str | None) -> bool:
    """True si una actividad de Strava puede cerrar ese workout planificado."""
    wd = discipline_for_workout_type(workout_type)
    if wd is None:
        return False
    ad = discipline_for_strava_type(strava_type)
    if wd == "brick":
        return ad in ("bike", "run")
    # La fuerza en Strava suele venir como "Workout"/"WeightTraining" (strength),
    # pero hay relojes que la suben como "other": lo aceptamos también.
    if wd == "strength":
        return ad in ("strength", "other")
    return ad == wd
