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
