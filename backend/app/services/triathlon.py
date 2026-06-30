"""Configuración de las distancias estándar de triatlón.

Cada distancia define los kilómetros de natación, ciclismo y carrera, además
de un nombre legible en español. Estos valores son los oficiales de las
distancias homologadas y los usa el generador de planes para repartir el
volumen entre las tres disciplinas.
"""
from typing import Optional


# Distancias estándar de triatlón.
# swim_km / bike_km / run_km = distancia de cada segmento.
TRIATHLON_DISTANCES: dict[str, dict] = {
    "sprint": {
        "name": "Sprint",
        "swim_km": 0.75,
        "bike_km": 20.0,
        "run_km": 5.0,
    },
    "olympic": {
        "name": "Olímpico",
        "swim_km": 1.5,
        "bike_km": 40.0,
        "run_km": 10.0,
    },
    "half": {
        "name": "Medio Ironman (70.3)",
        "swim_km": 1.9,
        "bike_km": 90.0,
        "run_km": 21.1,
    },
    "ironman": {
        "name": "Ironman",
        "swim_km": 3.8,
        "bike_km": 180.0,
        "run_km": 42.2,
    },
}


def get_triathlon_distance(key: str) -> Optional[dict]:
    """Devuelve la config de una distancia de triatlón por su clave.

    Claves válidas: 'sprint' | 'olympic' | 'half' | 'ironman'.
    Devuelve None si la clave no existe.
    """
    if not key:
        return None
    return TRIATHLON_DISTANCES.get(key.lower())
