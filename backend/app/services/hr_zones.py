"""Calculadora de zonas cardíacas y ritmos objetivo.

Usa FC máxima (medida o estimada) + FC de reposo para aplicar Karvonen.
Si hay VAM disponible, también calcula ritmos objetivo por zona.
"""
from typing import Optional


# Porcentajes de FC reserva para cada zona (Karvonen)
# Z1: recuperación, Z2: base aeróbica, Z3: tempo, Z4: umbral, Z5: VO2max
ZONE_PCT = {
    "Z1": (0.50, 0.60),
    "Z2": (0.60, 0.70),
    "Z3": (0.70, 0.80),
    "Z4": (0.80, 0.90),
    "Z5": (0.90, 1.00),
}

# Porcentajes de VAM (velocidad aeróbica máxima) para ritmos por zona
# Referencia: Billat et al.
ZONE_VAM_PCT = {
    "Z1": (0.55, 0.65),
    "Z2": (0.65, 0.75),
    "Z3": (0.75, 0.85),
    "Z4": (0.85, 0.92),
    "Z5": (0.92, 1.00),
}


def estimate_max_hr(age: int, sex: Optional[str] = None) -> int:
    """Estima FC máxima. Tanaka > Fox para >40 años."""
    # Tanaka: 208 - 0.7 * age
    return round(208 - 0.7 * age)


def karvonen_zone(hr_max: int, hr_rest: int, low: float, high: float) -> tuple[int, int]:
    """Calcula rango de FC para una zona usando Karvonen."""
    reserve = hr_max - hr_rest
    return (round(hr_rest + reserve * low), round(hr_rest + reserve * high))


def compute_hr_zones(
    age: Optional[int],
    max_heart_rate: Optional[int],
    resting_heart_rate: Optional[int] = None,
    sex: Optional[str] = None,
) -> Optional[dict]:
    """Devuelve dict con rangos por zona. Requiere al menos edad o FC máx."""
    if not max_heart_rate and not age:
        return None

    hr_max = max_heart_rate or estimate_max_hr(age, sex)
    hr_rest = resting_heart_rate or 60  # default razonable

    zones = {}
    for zone, (low, high) in ZONE_PCT.items():
        zones[zone] = list(karvonen_zone(hr_max, hr_rest, low, high))

    return {
        "hr_max": hr_max,
        "hr_rest": hr_rest,
        "method": "karvonen",
        "zones": zones,
    }


def ms_to_pace_per_km(ms: float) -> str:
    """Convierte m/s a ritmo min:seg / km."""
    if ms <= 0:
        return "—"
    seconds_per_km = 1000 / ms
    minutes = int(seconds_per_km // 60)
    seconds = int(round(seconds_per_km - minutes * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def compute_paces_from_vam(vam_ms: float) -> dict:
    """Ritmos objetivo por zona a partir de VAM (m/s)."""
    paces = {}
    for zone, (low, high) in ZONE_VAM_PCT.items():
        v_low = vam_ms * low
        v_high = vam_ms * high
        paces[zone] = {
            "pace_slow": ms_to_pace_per_km(v_low),
            "pace_fast": ms_to_pace_per_km(v_high),
            "speed_ms": [round(v_low, 2), round(v_high, 2)],
        }
    return paces
