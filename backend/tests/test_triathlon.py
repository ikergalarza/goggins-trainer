"""Tests del servicio de distancias de triatlón.

Verifica que las 4 distancias estándar devuelven swim/bike/run correctos y que
las claves desconocidas o vacías devuelven None.
"""
import pytest

from app.services.triathlon import get_triathlon_distance, TRIATHLON_DISTANCES


EXPECTED = {
    "sprint": (0.75, 20.0, 5.0),
    "olympic": (1.5, 40.0, 10.0),
    "half": (1.9, 90.0, 21.1),
    "ironman": (3.8, 180.0, 42.2),
}


@pytest.mark.parametrize("key,segments", EXPECTED.items())
def test_distancias_devuelven_segmentos_correctos(key, segments):
    swim, bike, run = segments
    cfg = get_triathlon_distance(key)
    assert cfg is not None
    assert cfg["swim_km"] == swim
    assert cfg["bike_km"] == bike
    assert cfg["run_km"] == run


def test_las_cuatro_distancias_existen():
    assert set(TRIATHLON_DISTANCES.keys()) == {"sprint", "olympic", "half", "ironman"}


def test_cada_distancia_tiene_nombre_legible():
    for key in EXPECTED:
        assert get_triathlon_distance(key)["name"]


def test_clave_es_case_insensitive():
    assert get_triathlon_distance("OLYMPIC") == get_triathlon_distance("olympic")
    assert get_triathlon_distance("Sprint")["swim_km"] == 0.75


def test_clave_desconocida_devuelve_none():
    assert get_triathlon_distance("marathon") is None


def test_clave_vacia_devuelve_none():
    assert get_triathlon_distance("") is None
