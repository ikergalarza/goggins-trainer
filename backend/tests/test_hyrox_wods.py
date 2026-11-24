"""Plantillas de WOD de Hyrox para añadir sesiones al instante, en el servidor.

Pedirle a Goggins que redacte un WOD completo por sesión nuevo (8-10 de golpe)
desbordaba el límite de su respuesta y la petición se quedaba a medias. Estas
plantillas dan sesiones válidas, con los pesos de la división del atleta, su
ritmo y la carga adecuada a lo cerca que está la carrera.
"""
import pytest

from app.services import hyrox_knowledge, hyrox_wods, wod_duration, wod_structure

LOADED = {"sled_push", "sled_pull", "wall_balls", "sandbag_lunges", "farmers_carry"}
FASES = [None, 12, 6, 3, 1]          # semanas hasta la carrera: base, base, build, peak, taper


def _items(structure):
    for b in structure["blocks"]:
        yield from b["items"]
    for st in (structure.get("warmup") or {}).get("steps", []):
        if isinstance(st, dict):
            yield st


@pytest.mark.parametrize("division", sorted(hyrox_knowledge.DIVISION_STANDARDS))
def test_cada_plantilla_es_un_wod_valido_con_dosis_y_pesos(division):
    for variant in range(hyrox_wods.N_TEMPLATES):
        for semanas in FASES:
            s = hyrox_wods.build_session(division, variant=variant, weeks_to_race=semanas)
            san = wod_structure.sanitize(s["structure"])
            assert san is not None, (variant, semanas)
            # el saneado no pierde nada: todo lo que pone la plantilla es válido
            assert [i for b in san["blocks"] for i in b["items"]] == [i for b in s["structure"]["blocks"] for i in b["items"]]
            assert san["objective"] and san["warmup"]["steps"] and san["cooldown"]
            for b in san["blocks"]:
                assert b.get("rounds"), "todo bloque lleva nº de rondas/series"
            for it in _items(san):
                assert any(k in it for k in ("reps", "distance_m", "duration_s")), it
                if it["exercise"] in LOADED:
                    assert it["weight_kg"] > 0, it
            assert s["type"] == "hyrox_stations" and s["instructions"]


def test_los_pesos_son_los_de_su_division():
    for division, std in (("open_men", 152), ("doubles_women", 102), ("pro_men", 202)):
        s = hyrox_wods.build_session(division, variant=0, weeks_to_race=6)
        push = [i for i in _items(s["structure"]) if i["exercise"] == "sled_push" and i["distance_m"] == 25]
        assert push and push[0]["weight_kg"] == std, division
        ball = [i for i in _items(s["structure"]) if i["exercise"] == "wall_balls"]
        assert ball[0]["weight_kg"] == hyrox_knowledge.DIVISION_STANDARDS[division]["wall_ball_kg"]


def test_los_farmers_llevan_el_peso_de_cada_mano():
    s = hyrox_wods.build_session("open_men", variant=2, weeks_to_race=6)
    farmers = [i for i in _items(s["structure"]) if i["exercise"] == "farmers_carry"]
    assert farmers and farmers[0]["weight_kg"] == 24          # "2×24" -> 24 kg por mano


def test_la_carga_progresa_con_la_cercania_de_la_carrera():
    lejos = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=12)["structure"]
    cerca = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=3)["structure"]
    assert lejos["blocks"][0]["rounds"] < cerca["blocks"][0]["rounds"]
    sled = lambda st: [i for i in _items(st) if i["exercise"] == "sled_push" and i["distance_m"] == 25][0]["weight_kg"]
    assert sled(lejos) < sled(cerca)


def test_las_variantes_son_distintas_entre_si():
    titulos = {hyrox_wods.build_session("open_men", variant=v, weeks_to_race=6)["title"] for v in range(hyrox_wods.N_TEMPLATES)}
    assert len(titulos) == hyrox_wods.N_TEMPLATES
    # y la variante da la vuelta (no se rompe con índices grandes)
    assert hyrox_wods.build_session("open_men", variant=hyrox_wods.N_TEMPLATES + 2, weeks_to_race=6)["title"] in titulos


@pytest.mark.parametrize("variant", range(hyrox_wods.N_TEMPLATES))
def test_la_duracion_calculada_es_razonable(variant):
    for semanas in FASES:
        est = wod_duration.estimate(hyrox_wods.build_session("open_men", variant=variant, weeks_to_race=semanas)["structure"])
        assert est is not None and 28 <= est["total_min"] <= 65, (variant, semanas, est)


def test_se_entrena_solo_sin_relevos():
    for v in range(hyrox_wods.N_TEMPLATES):
        s = hyrox_wods.build_session("doubles_mixed", variant=v, weeks_to_race=6)
        texto = " ".join([s["instructions"], s["structure"]["objective"], s["structure"].get("notes", "")]).lower()
        assert not any(p in texto for p in ("relevo", "compañero", "pareja", "tú vas"))


def test_usa_el_ritmo_del_atleta_con_el_margen_de_la_carga_de_estaciones():
    s = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6, threshold_pace="4:50")
    run = [i for i in _items(s["structure"]) if i["exercise"] == "run"][0]
    assert run["pace"] == "5:05/km"                   # umbral + 15 s/km: ritmo de carrera Hyrox


def test_sin_ritmo_conocido_no_se_inventa_ninguno():
    s = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6)
    assert all("pace" not in i for i in _items(s["structure"]) if i["exercise"] == "run")
    s = hyrox_wods.build_session("open_men", variant=0, weeks_to_race=6, threshold_pace="rápido")
    assert all("pace" not in i for i in _items(s["structure"]) if i["exercise"] == "run")


def test_division_desconocida_cae_en_open():
    a = hyrox_wods.build_session("inventada", variant=1, weeks_to_race=6)
    b = hyrox_wods.build_session("open_men", variant=1, weeks_to_race=6)
    assert a["structure"] == b["structure"]


def test_la_instruccion_resume_la_sesion_y_nombra_la_division():
    s = hyrox_wods.build_session("doubles_mixed", variant=0, weeks_to_race=6)
    assert "Running comprometido" in s["instructions"] and "Dobles mixto" in s["instructions"]
