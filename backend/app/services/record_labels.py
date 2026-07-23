"""Etiquetas legibles de las categorías de marcas personales.

`PersonalRecord.category` guarda un slug ("tri_olympic"). Hasta ahora ese slug
viajaba crudo al contexto de la IA, que no puede saber qué distancias implica.
Aquí se traduce antes de construir el prompt.

Mantener en sintonía con CATEGORIES en frontend/src/pages/Records.tsx.
"""

CATEGORY_LABELS: dict[str, str] = {
    # Carrera
    "5k": "5 km",
    "10k": "10 km",
    "21k": "Media maratón (21,1 km)",
    "42k": "Maratón (42,2 km)",
    "1mile": "1 milla",
    "vam_test": "Test VAM (5 min)",
    # Triatlón — tiempo total. El sufijo coincide con las claves de
    # TRIATHLON_DISTANCES y con goal.triathlon_distance, para poder cruzar
    # un objetivo de triatlón con la marca de esa misma distancia.
    "tri_sprint": "Triatlón sprint (750 m nado / 20 km bici / 5 km carrera)",
    "tri_olympic": "Triatlón olímpico (1,5 km nado / 40 km bici / 10 km carrera)",
    "tri_half": "Triatlón medio, 70.3 (1,9 km nado / 90 km bici / 21,1 km carrera)",
    "tri_ironman": "Triatlón completo, Ironman (3,8 km nado / 180 km bici / 42,2 km carrera)",
    # Natación
    "swim_400m": "Natación 400 m",
    "swim_1500m": "Natación 1500 m",
    # Ciclismo
    "bike_40k_tt": "Bici 40 km contrarreloj",
    "bike_ftp": "Bici FTP (umbral funcional)",
    # Hyrox
    "hyrox_full": "Hyrox completo",
    "hyrox_run_only": "Hyrox — solo running (8×1 km)",
    "hyrox_roxzone": "Hyrox — Roxzone",
    # Fuerza
    "squat_1rm": "Sentadilla 1RM",
    "deadlift_1rm": "Peso muerto 1RM",
    "bench_1rm": "Press banca 1RM",
    "wall_balls": "Wall balls (reps/min)",
}


def label_for(category: str | None) -> str:
    """Etiqueta legible de una categoría. Si no se conoce, devuelve el slug."""
    if not category:
        return ""
    return CATEGORY_LABELS.get(category, category)
