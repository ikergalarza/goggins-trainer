"""Plantillas de WOD de Hyrox: el estándar de sesión del que salió la auditoría.

La auditoría encontró sesiones de ~29 min de trabajo con 2 estaciones en un
único circuito, casi iguales en días seguidos y trineo pesado 48 h antes de un
simulacro. El estándar: ~60 min, 3 bloques, 3+ estaciones y 2+ km de carrera;
activación ligera antes de un simulacro, descarga corta al final y nunca la
misma estación pesada pegada.
"""
from datetime import date

import pytest

from app.services import hyrox_knowledge, hyrox_wods, wod_duration, wod_structure

LOADED = {"sled_push", "sled_pull", "wall_balls", "sandbag_lunges", "farmers_carry"}
FASES = [None, 12, 6, 3]                     # semanas hasta la carrera: base, base, build, peak


def _items(structure):
    for b in structure["blocks"]:
        yield from b["items"]
    for st in (structure.get("warmup") or {}).get("steps", []):
        if isinstance(st, dict):
            yield st


def _stations(structure):
    return {i["exercise"] for b in structure["blocks"] for i in b["items"] if i["exercise"] != "run"}


def _run_m(structure):
    return sum(i.get("distance_m", 0) * b.get("rounds", 1) for b in structure["blocks"] for i in b["items"] if i["exercise"] == "run")


def _todas(division="open_men", semanas=6, thr=None):
    for v in range(hyrox_wods.N_TEMPLATES):
        yield hyrox_wods.build_session(division, variant=v, weeks_to_race=semanas, threshold_pace=thr)
    for kind in ("activation", "taper"):
        yield hyrox_wods.build_session(division, variant=0, weeks_to_race=semanas, threshold_pace=thr, kind=kind)


@pytest.mark.parametrize("division", sorted(hyrox_knowledge.DIVISION_STANDARDS))
def test_cada_plantilla_es_un_wod_valido_con_dosis_y_pesos(division):
    for semanas in FASES:
        for s in _todas(division, semanas):
            san = wod_structure.sanitize(s["structure"])
            assert san is not None
            assert [i for b in san["blocks"] for i in b["items"]] == [i for b in s["structure"]["blocks"] for i in b["items"]]
            assert san["objective"] and san["warmup"]["steps"] and san["cooldown"]
            for b in san["blocks"]:
                assert b.get("rounds")
            for it in _items(san):
                assert any(k in it for k in ("reps", "distance_m", "duration_s")), it
                if it["exercise"] in LOADED:
                    assert it["weight_kg"] > 0, it
            assert s["type"] == "hyrox_stations" and s["instructions"] and s["distance_km"] > 0


@pytest.mark.parametrize("variant", range(hyrox_wods.N_TEMPLATES))
def test_una_sesion_normal_dura_una_hora_con_3_bloques_y_estaciones_variadas(variant):
    for semanas in FASES:
        s = hyrox_wods.build_session("open_men", variant=variant, weeks_to_race=semanas)["structure"]
        est = wod_duration.estimate(s)
        assert 55 <= est["total_min"] <= 75, (variant, semanas, est)
        assert len(s["blocks"]) >= 3
        assert len(_stations(s)) >= 4
        assert _run_m(s) >= 2000


def test_la_activacion_y_la_descarga_son_cortas():
    for semanas in FASES:
        act = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=semanas, kind="activation")["structure"]
        taper = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=1, kind="taper")["structure"]
        assert 35 <= wod_duration.estimate(act)["total_min"] <= 50
        assert 35 <= wod_duration.estimate(taper)["total_min"] <= 55
        # en la activación el trineo va aligerado
        sled = [i for i in _items(act) if i["exercise"] in ("sled_push", "sled_pull") and i["distance_m"] >= 12]
        assert sled and all(i["weight_kg"] < 100 for i in sled)


def test_la_distancia_es_la_carrera_de_dentro_de_la_sesion():
    s = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6)
    assert s["distance_km"] == round(_run_m(s["structure"]) / 1000, 1)


def test_los_pesos_son_los_de_su_division():
    for division, std in (("open_men", 152), ("doubles_women", 102), ("pro_men", 202)):
        s = hyrox_wods.build_session(division, variant=0, weeks_to_race=6)
        push = [i for i in _items(s["structure"]) if i["exercise"] == "sled_push" and i["distance_m"] == 25]
        assert push and push[0]["weight_kg"] == std, division
    farmers = [i for i in _items(hyrox_wods.build_session("open_men", variant=1, weeks_to_race=6)["structure"])
               if i["exercise"] == "farmers_carry"]
    assert farmers and farmers[0]["weight_kg"] == 24          # "2×24" -> 24 kg por mano


def test_la_carga_progresa_con_la_cercania_de_la_carrera():
    for v in range(hyrox_wods.N_TEMPLATES):
        lejos = wod_duration.estimate(hyrox_wods.build_session("open_men", variant=v, weeks_to_race=12)["structure"])
        cerca = wod_duration.estimate(hyrox_wods.build_session("open_men", variant=v, weeks_to_race=3)["structure"])
        assert lejos["work_min"] <= cerca["work_min"], v


def test_el_ritmo_de_carrera_es_el_del_atleta_y_baja_segun_se_acerca_la_prueba():
    base = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=12, threshold_pace="4:37")
    peak = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=3, threshold_pace="4:37")
    pace = lambda s: [i for i in _items(s["structure"]) if i["exercise"] == "run" and i.get("pace")][0]["pace"]
    assert pace(base) == "4:55/km" and pace(peak) == "4:45/km"
    sin = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6, threshold_pace="rápido")
    assert all("pace" not in i for i in _items(sin["structure"]) if i["exercise"] == "run")


def test_las_variantes_son_distintas_entre_si():
    titulos = {hyrox_wods.build_session("open_men", variant=v, weeks_to_race=6)["title"] for v in range(hyrox_wods.N_TEMPLATES)}
    assert len(titulos) == hyrox_wods.N_TEMPLATES
    assert hyrox_wods.build_session("open_men", variant=hyrox_wods.N_TEMPLATES + 2, weeks_to_race=6)["title"] in titulos


def test_se_entrena_solo_sin_relevos():
    for s in _todas("doubles_mixed"):
        texto = " ".join([s["instructions"], s["structure"]["objective"], s["structure"].get("notes", "")]).lower()
        assert not any(p in texto for p in ("relevo", "compañero", "tú vas"))


def test_division_desconocida_cae_en_open():
    a = hyrox_wods.build_session("inventada", variant=1, weeks_to_race=6)
    b = hyrox_wods.build_session("open_men", variant=1, weeks_to_race=6)
    assert a["structure"] == b["structure"]


# --- elegir la sesión según lo que hay alrededor --------------------------------

def _ses(d, *estaciones, tipo="hyrox_stations"):
    return (d, tipo, {"blocks": [{"items": [{"exercise": e} for e in estaciones]}]})


D = date(2026, 12, 17)


def test_antes_de_un_simulacro_toca_activacion():
    assert hyrox_wods.choose_kind(D, [_ses(date(2026, 12, 19), tipo="hyrox_sim")], weeks_to_race=6) == "activation"
    assert hyrox_wods.choose_kind(D, [_ses(date(2026, 12, 18), tipo="hyrox_sim")], weeks_to_race=6) == "activation"
    assert hyrox_wods.choose_kind(D, [_ses(date(2026, 12, 21), tipo="hyrox_sim")], weeks_to_race=6) == "full"
    assert hyrox_wods.choose_kind(D, [], weeks_to_race=1) == "taper"
    assert hyrox_wods.choose_kind(D, [], weeks_to_race=None) == "full"


def test_no_repite_estacion_pesada_con_la_sesion_de_al_lado():
    ayer_trineo = [_ses(date(2026, 12, 16), "sled_push", "sled_pull", "wall_balls")]
    v = hyrox_wods.choose_variant(D, ayer_trineo, index=0)
    s = hyrox_wods.build_session("open_men", variant=v, weeks_to_race=6)
    assert not _stations(s["structure"]) & {"sled_push", "sled_pull"}
    # sin vecinos, rota
    assert {hyrox_wods.choose_variant(D, [], index=i) for i in range(hyrox_wods.N_TEMPLATES)} == set(range(hyrox_wods.N_TEMPLATES))


def test_una_sesion_pobre_se_detecta():
    pobre = {"warmup": {"duration_min": 10}, "blocks": [{"rounds": 4, "items": [
        {"exercise": "run", "distance_m": 400}, {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152},
        {"exercise": "wall_balls", "reps": 15, "weight_kg": 6}]}]}
    assert hyrox_wods.is_thin(pobre)
    assert hyrox_wods.is_thin(None)
    assert not hyrox_wods.is_thin(hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6)["structure"])
