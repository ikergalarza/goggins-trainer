"""Tests del mapeo `type` de Strava → disciplina deportiva.

Cubre:
- `discipline_for_strava_type` (módulo general): SIEMPRE devuelve una de las
  5 disciplinas, incluidas fuerza (sin km) y "other" para lo desconocido.
- El wrapper de triatlón `_discipline_for_strava_type` de plan_generator,
  que tras el refactor delega en el módulo general pero mantiene su
  contrato: solo swim/bike/run, resto None.
"""
import pytest

from app.services.discipline import DISCIPLINES, discipline_for_strava_type
from app.services.plan_generator import _discipline_for_strava_type


# ────────────────────────────────────────────────────────────────────
# discipline_for_strava_type (mapeo general, nunca None)
# ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("strava_type", "esperada"),
    [
        ("Run", "run"),
        ("TrailRun", "run"),
        ("VirtualRide", "bike"),
        ("EBikeRide", "bike"),
        ("Swim", "swim"),
        ("WeightTraining", "strength"),
        ("Workout", "strength"),
        ("Crossfit", "strength"),
        ("Hiit", "strength"),
        (None, "other"),
        ("", "other"),
        ("Kitesurf", "other"),
    ],
)
def test_mapeo_type_a_disciplina(strava_type, esperada):
    assert discipline_for_strava_type(strava_type) == esperada


def test_siempre_devuelve_una_disciplina_valida():
    # Nunca None: hasta lo desconocido cae en "other" para que ninguna
    # actividad desaparezca de las estadísticas.
    for t in ("Run", "Ride", "Swim", "WeightTraining", "Yoga", "AlpineSki", "Rowing", None, ""):
        assert discipline_for_strava_type(t) in DISCIPLINES


# ────────────────────────────────────────────────────────────────────
# Wrapper de triatlón (plan_generator): solo swim/bike/run, resto None
# ────────────────────────────────────────────────────────────────────

def test_wrapper_triatlon_mantiene_su_contrato():
    assert _discipline_for_strava_type("Run") == "run"
    assert _discipline_for_strava_type("VirtualRide") == "bike"
    assert _discipline_for_strava_type("Swim") == "swim"
    # Fuerza y otros deportes no son volumen de triatlón → None.
    assert _discipline_for_strava_type("WeightTraining") is None
    assert _discipline_for_strava_type("Kitesurf") is None
    assert _discipline_for_strava_type(None) is None
