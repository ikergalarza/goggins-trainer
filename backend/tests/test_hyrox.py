"""Conocimiento Hyrox + WODs estructurados + feedback del atleta."""
from datetime import date

from app.models.goal import Goal, GoalType
from app.models.workout import Workout
from app.services import hyrox_knowledge as hk
from app.services import wod_structure, agent_tools


def _hyrox_goal(db, user, division="dobles"):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao",
             hyrox_division=division, is_active=True)
    db.add(g); db.commit(); db.refresh(g)
    return g


# --- conocimiento / divisiones ---------------------------------------------

def test_tabla_de_pesos_25_26():
    om = hk.DIVISION_STANDARDS["open_men"]
    assert (om["sled_push_kg"], om["sled_pull_kg"], om["sandbag_kg"], om["wall_ball_kg"]) == (152, 103, 20, 6)
    pm = hk.DIVISION_STANDARDS["pro_men"]
    assert (pm["sled_push_kg"], pm["wall_ball_kg"]) == (202, 9)
    # dobles usa cargas de Open de su sexo
    assert hk.DIVISION_STANDARDS["doubles_men"]["sled_push_kg"] == 152
    assert hk.DIVISION_STANDARDS["doubles_women"]["sled_push_kg"] == 102


def test_division_key_desde_goal(db, user):
    g = _hyrox_goal(db, user, "dobles")
    assert hk.division_key(g, user) == "doubles_men"  # user fixture es sexo M
    g.hyrox_division = "pro"
    assert hk.division_key(g, user) == "pro_men"
    g.hyrox_division = "mixto"
    assert hk.division_key(g, user) == "doubles_mixed"
    g.hyrox_division = None
    assert hk.division_key(g, user) == "open_men"


def test_is_hyrox_goal(db, user):
    assert hk.is_hyrox_goal(_hyrox_goal(db, user))
    running = Goal(user_id=user.id, type=GoalType.race, description="10k", is_active=True)
    db.add(running); db.commit()
    assert not hk.is_hyrox_goal(running)


def test_prompt_block_lleva_pesos_de_su_division(db, user):
    g = _hyrox_goal(db, user, "dobles")
    block = hk.prompt_block(g, user)
    assert "152 kg" in block and "103 kg" in block and "2×24" in block
    assert "Wall Balls" in block and "100 reps" in block
    assert "corren JUNTOS" in block  # reglas de dobles presentes


def test_prompt_block_for_user_solo_con_goal_hyrox(db, user):
    assert hk.prompt_block_for_user(user, db) == ""
    _hyrox_goal(db, user)
    assert "CONOCIMIENTO HYROX" in hk.prompt_block_for_user(user, db)


# --- sanitizado del structure ------------------------------------------------

RAW = {
    "objective": "Tolerancia a wall balls tras carrera",
    "warmup": {"duration_min": 12, "steps": ["500 m remo suave", "2×10 sentadillas"]},
    "blocks": [
        {"title": "Principal", "format": "rounds", "rounds": 4, "rest_s": 120,
         "items": [
             {"exercise": "run", "distance_m": 400, "pace": "4:40/km"},
             {"exercise": "wall_balls", "reps": 15, "weight_kg": 6},
             {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152},
         ]},
    ],
    "cooldown": ["5' trote suave"],
    "notes": "Respira en el cambio",
}


def test_sanitize_conserva_wod_valido():
    s = wod_structure.sanitize(RAW)
    assert s["objective"].startswith("Tolerancia")
    assert s["warmup"]["steps"] == ["500 m remo suave", "2×10 sentadillas"]
    assert s["blocks"][0]["rounds"] == 4
    assert s["blocks"][0]["items"][1] == {"exercise": "wall_balls", "reps": 15, "weight_kg": 6}


def test_sanitize_ejercicio_desconocido_cae_en_other():
    s = wod_structure.sanitize({"blocks": [{"items": [{"exercise": "devil_press", "reps": 10}]}]})
    assert s["blocks"][0]["items"][0] == {"exercise": "other", "name": "devil_press", "reps": 10}


def test_sanitize_basura_devuelve_none():
    assert wod_structure.sanitize(None) is None
    assert wod_structure.sanitize("texto") is None
    assert wod_structure.sanitize({"objective": "x"}) is None  # sin bloques no hay WOD
    assert wod_structure.sanitize({"blocks": [{"items": [{"exercise": 42}]}]}) is None


def test_sanitize_capa_tamaños():
    s = wod_structure.sanitize({"blocks": [{"items": [{"exercise": "run", "distance_m": 400}]} for _ in range(50)]})
    assert len(s["blocks"]) <= 12


# --- tools del chat: structure + feedback ------------------------------------

def test_add_workout_tool_persiste_structure(db, user):
    out = agent_tools.execute_tool("add_workout", {
        "date": "2026-09-17", "type": "hyrox_stations",
        "instructions": "4 rondas run+wall balls+sled",
        "structure": RAW,
    }, user, db)
    assert out["ok"]
    w = db.query(Workout).get(out["workout_id"])
    assert w.structure["blocks"][0]["items"][2]["weight_kg"] == 152
    assert out["workout"]["structure"]["objective"]


def test_update_workout_tool_actualiza_structure(db, user):
    out = agent_tools.execute_tool("add_workout", {"date": "2026-09-18", "type": "hyrox_sim"}, user, db)
    wid = out["workout_id"]
    out2 = agent_tools.execute_tool("update_workout", {"workout_id": wid, "structure": RAW}, user, db)
    assert out2["ok"]
    db.expire_all()
    assert db.query(Workout).get(wid).structure["blocks"]


def test_set_training_feedback(db, user):
    out = agent_tools.execute_tool("set_training_feedback",
                                   {"area": "Sled Push", "rating": "flojo", "note": "me muero en el empuje"}, user, db)
    assert out["ok"]
    db.refresh(user)
    assert user.station_feedback["sled_push"]["rating"] == "flojo"
    # rating inválido no rompe ni guarda
    bad = agent_tools.execute_tool("set_training_feedback", {"area": "remo", "rating": "regulinchi"}, user, db)
    assert not bad["ok"]


def test_spec_exige_numero_de_series():
    # Guardia del prompt: sin esto la IA emitía bloques "sets" sin rounds y el
    # WOD quedaba ambiguo (¿cuántas series?).
    assert 'rounds` = nº de series' in wod_structure.PROMPT_SPEC
    assert "rounds 1 explícito" in wod_structure.PROMPT_SPEC
