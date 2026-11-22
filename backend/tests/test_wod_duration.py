"""Duración de un WOD calculada desde su contenido (no a ojo por la IA).

El síntoma que motivó esto: sesiones Hyrox etiquetadas con 55' que el atleta
hacía en ~40'. `planned_duration_min` lo escribía la IA sin ninguna regla que lo
atase al WOD; ahora se calcula sumando calentamiento + bloques (con descansos)
+ vuelta a la calma.
"""
from datetime import date

from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import agent_tools, plan_generator, wod_duration, wod_structure

# El WOD de ejemplo de PROMPT_SPEC (el que la IA toma de modelo).
EJEMPLO = {
    "objective": "Tolerancia a wall balls con pulso alto tras carrera",
    "warmup": {"duration_min": 10, "steps": ["500 m remo suave", "2×10 sentadillas"]},
    "blocks": [
        {"title": "Bloque principal", "format": "rounds", "rounds": 4, "rest_s": 120,
         "items": [
             {"exercise": "run", "distance_m": 400, "pace": "4:40/km"},
             {"exercise": "wall_balls", "reps": 15, "weight_kg": 6},
             {"exercise": "sled_push", "distance_m": 25, "weight_kg": 152},
         ]},
    ],
    "cooldown": ["5' trote muy suave", "estiramiento de cuádriceps y glúteo"],
}


def _wod(blocks, warmup=None, cooldown=None):
    s = {"blocks": blocks}
    if warmup is not None:
        s["warmup"] = warmup
    if cooldown is not None:
        s["cooldown"] = cooldown
    return s


# --- el cálculo ---------------------------------------------------------------

def test_el_ejemplo_de_la_spec_dura_unos_40_no_55():
    est = wod_duration.estimate(EJEMPLO)
    assert est["warmup_min"] == 10
    assert est["cooldown_min"] == 5
    # 4 rondas × (400 m a 4:40 + 15 wall balls + 25 m de sled a 152 kg) + 3 descansos de 2'
    assert 20 <= est["work_min"] <= 27
    assert 35 <= est["total_min"] <= 42
    assert est["total_min"] == est["warmup_min"] + est["work_min"] + est["cooldown_min"]


def test_el_ritmo_de_la_carrera_se_lee_del_item():
    rapido = wod_duration.estimate(_wod([{"format": "fortime", "items": [
        {"exercise": "run", "distance_m": 1000, "pace": "4:00/km"}]}]))
    lento = wod_duration.estimate(_wod([{"format": "fortime", "items": [
        {"exercise": "run", "distance_m": 1000, "pace": "6:00/km"}]}]))
    assert lento["work_min"] - rapido["work_min"] == 2  # 1 km: 2' de diferencia


def test_amrap_y_emom_duran_lo_que_dicen():
    amrap = wod_duration.estimate(_wod([{"format": "amrap", "duration_min": 12,
                                         "items": [{"exercise": "burpee", "reps": 10}]}]))
    emom = wod_duration.estimate(_wod([{"format": "emom", "duration_min": 16, "interval_s": 60,
                                        "items": [{"exercise": "kb_swing", "reps": 15}]}]))
    assert amrap["work_min"] == 12
    assert emom["work_min"] == 16


def test_series_de_fuerza_cuentan_el_descanso_entre_series():
    # 4 series de 6 peso muerto con 2' de descanso entre series (3 descansos)
    est = wod_duration.estimate(_wod([{"format": "sets", "rounds": 4, "rest_s": 120,
                                       "items": [{"exercise": "deadlift", "reps": 6, "weight_kg": 100}]}]))
    assert 8 <= est["work_min"] <= 10


def test_series_sin_descanso_declarado_llevan_uno_por_defecto():
    sin = wod_duration.estimate(_wod([{"format": "sets", "rounds": 4,
                                       "items": [{"exercise": "deadlift", "reps": 6}]}]))
    con = wod_duration.estimate(_wod([{"format": "sets", "rounds": 4, "rest_s": 0,
                                       "items": [{"exercise": "deadlift", "reps": 6}]}]))
    assert sin["work_min"] > con["work_min"] + 3  # 3 descansos por defecto, no cero


def test_duration_s_manda_sobre_cualquier_tabla():
    est = wod_duration.estimate(_wod([{"format": "rounds", "rounds": 1,
                                       "items": [{"exercise": "plank", "duration_s": 120}]}]))
    assert est["work_min"] == 2 or est["work_min"] == 3  # 120 s + una transición


def test_ejercicio_desconocido_no_rompe_ni_vale_cero():
    est = wod_duration.estimate(_wod([{"items": [{"exercise": "other", "name": "devil_press", "reps": 10}]}]))
    assert est is not None and est["work_min"] >= 1


def test_la_carga_del_sled_importa():
    ligero = wod_duration.estimate(_wod([{"items": [{"exercise": "sled_push", "distance_m": 50, "weight_kg": 60}]}]))
    pesado = wod_duration.estimate(_wod([{"items": [{"exercise": "sled_push", "distance_m": 50, "weight_kg": 202}]}]))
    assert pesado["work_min"] > ligero["work_min"]


def test_vuelta_a_la_calma_lee_los_minutos_del_texto():
    assert wod_duration.estimate(_wod([{"items": [{"exercise": "run", "distance_m": 400}]}],
                                      cooldown=["8' trote suave", "estiramientos"]))["cooldown_min"] == 8
    assert wod_duration.estimate(_wod([{"items": [{"exercise": "run", "distance_m": 400}]}],
                                      cooldown=["10 min caminando"]))["cooldown_min"] == 10
    # sin minutos escritos -> 5' por defecto; los segundos (30'') no cuentan como minutos
    assert wod_duration.estimate(_wod([{"items": [{"exercise": "run", "distance_m": 400}]}],
                                      cooldown=["3 x 30'' de estiramiento"]))["cooldown_min"] == 5


def test_sin_calentamiento_ni_vuelta_a_la_calma_no_se_inventan():
    est = wod_duration.estimate(_wod([{"items": [{"exercise": "run", "distance_m": 400}]}]))
    assert est["warmup_min"] == 0 and est["cooldown_min"] == 0


def test_simulacro_completo_cae_en_el_rango_de_un_atleta_intermedio():
    sim = {"warmup": {"duration_min": 10}, "cooldown": ["5' trote"], "blocks": [
        {"title": "Simulacro", "format": "fortime", "rounds": 1, "items": [
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "ski_erg", "distance_m": 1000},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "sled_push", "distance_m": 50, "weight_kg": 152},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "sled_pull", "distance_m": 50, "weight_kg": 103},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "burpee_broad_jump", "distance_m": 80},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "row", "distance_m": 1000},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "farmers_carry", "distance_m": 200, "weight_kg": 24},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "sandbag_lunges", "distance_m": 100, "weight_kg": 20},
            {"exercise": "run", "distance_m": 1000, "pace": "5:10/km"}, {"exercise": "wall_balls", "reps": 100, "weight_kg": 6},
        ]}]}
    est = wod_duration.estimate(sim)
    # Un Hyrox de amateur intermedio ronda 1h15-1h30; +15' de calentamiento y vuelta a la calma.
    assert 70 <= est["work_min"] <= 90
    assert 85 <= est["total_min"] <= 105


def test_basura_devuelve_none_sin_romper():
    assert wod_duration.estimate(None) is None
    assert wod_duration.estimate({}) is None
    assert wod_duration.estimate({"blocks": []}) is None
    assert wod_duration.estimate({"blocks": ["x", 3, None]}) is None
    assert wod_duration.estimate("texto") is None
    # números corruptos no tiran el cálculo
    assert wod_duration.estimate(_wod([{"items": [{"exercise": "run", "distance_m": "mucho"}]}])) is not None


# --- aplicarlo a un workout ---------------------------------------------------

def _wo(db, user, **kw):
    base = dict(user_id=user.id, date=date(2026, 12, 1), day_of_week=1, week_index=2,
                type=WorkoutType.hyrox_stations, status=WorkoutStatus.planned,
                planned_duration_min=55, modified_by="ai")
    base.update(kw)
    w = Workout(**base)
    db.add(w); db.commit(); db.refresh(w)
    return w


def test_apply_to_workout_fija_la_duracion_y_guarda_el_reparto(db, user):
    w = _wo(db, user, structure=wod_structure.sanitize(EJEMPLO))
    assert wod_duration.apply_to_workout(w) is True
    db.commit(); db.expire_all()
    w = db.query(Workout).get(w.id)
    assert 35 <= w.planned_duration_min <= 42
    assert w.structure["estimate"]["total_min"] == w.planned_duration_min
    assert w.structure["estimate"]["warmup_min"] == 10


def test_apply_to_workout_sin_structure_no_toca_nada(db, user):
    w = _wo(db, user, structure=None)
    assert wod_duration.apply_to_workout(w) is False
    assert w.planned_duration_min == 55


# --- por dónde entra: generación del plan y herramientas de Goggins -----------

def test_el_plan_generado_recalcula_la_duracion_de_los_wods(db, user):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", is_active=True)
    db.add(g); db.commit()
    data = {"weekly_plan": [{"week": 1, "workouts": [
        {"day_of_week": 1, "type": "hyrox_stations", "duration_min": 55, "structure": EJEMPLO},
        {"day_of_week": 3, "type": "easy_run", "distance_km": 8, "duration_min": 48},  # sin structure
    ]}]}
    plan_generator._insert_plan_workouts(db, user, data, date(2026, 11, 30), g.id)
    db.commit()
    rows = {w.type: w for w in db.query(Workout).all()}
    assert 35 <= rows[WorkoutType.hyrox_stations].planned_duration_min <= 42
    assert rows[WorkoutType.hyrox_stations].structure["estimate"]["warmup_min"] == 10
    assert rows[WorkoutType.easy_run].planned_duration_min == 48  # lo que no tiene WOD no se toca


def test_goggins_add_workout_con_structure_calcula_la_duracion(db, user, soon):
    out = agent_tools.execute_tool("add_workout", {
        "date": soon(2), "type": "hyrox_stations", "duration_min": 60, "structure": EJEMPLO,
    }, user, db)
    assert out["ok"]
    w = db.query(Workout).get(out["workout_id"])
    assert 35 <= w.planned_duration_min <= 42


def test_goggins_update_con_structure_recalcula_pero_sin_structure_respeta_lo_pedido(db, user, soon):
    out = agent_tools.execute_tool("add_workout", {"date": soon(3), "type": "hyrox_sim"}, user, db)
    wid = out["workout_id"]
    agent_tools.execute_tool("update_workout", {"workout_id": wid, "structure": EJEMPLO}, user, db)
    db.expire_all()
    w = db.query(Workout).get(wid)
    assert 35 <= w.planned_duration_min <= 42
    # el atleta pide expresamente otra duración, sin tocar el WOD: se respeta
    agent_tools.execute_tool("update_workout", {"workout_id": wid, "duration_min": 70}, user, db)
    db.expire_all()
    assert db.query(Workout).get(wid).planned_duration_min == 70


# --- planes ya generados ------------------------------------------------------

def test_backfill_corrige_lo_planificado_y_es_idempotente(db, user):
    s = wod_structure.sanitize(EJEMPLO)
    plan = _wo(db, user, structure=s)                                           # inflado a 55'
    hecho = _wo(db, user, structure=s, status=WorkoutStatus.completed,
                date=date(2026, 11, 20))                                        # historia: intocable
    corrida = _wo(db, user, type=WorkoutType.easy_run, structure=None,
                  date=date(2026, 12, 2))                                       # sin WOD: intocable
    assert wod_duration.backfill(db) == 1
    db.expire_all()
    assert 35 <= db.query(Workout).get(plan.id).planned_duration_min <= 42
    assert db.query(Workout).get(hecho.id).planned_duration_min == 55
    assert db.query(Workout).get(corrida.id).planned_duration_min == 55
    assert wod_duration.backfill(db) == 0   # segunda pasada: nada que hacer


def test_el_arranque_corrige_el_plan_existente_y_no_rompe_si_falla(db, user, monkeypatch):
    from app.db import seed
    plan = _wo(db, user, structure=wod_structure.sanitize(EJEMPLO))      # inflado a 55'
    # el arranque abre su propia sesión: se la damos de la misma base de test
    monkeypatch.setattr(seed, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    seed.backfill_wod_durations()
    db.expire_all()
    assert 35 <= db.query(Workout).get(plan.id).planned_duration_min <= 42

    # si el cálculo explota, el arranque sigue (solo avisa)
    monkeypatch.setattr(wod_duration, "backfill", lambda _db: (_ for _ in ()).throw(RuntimeError("boom")))
    seed.backfill_wod_durations()


# --- el prompt y el cálculo no se desincronizan --------------------------------

def test_el_prompt_de_la_ia_lleva_la_referencia_de_tiempos():
    spec = wod_structure.PROMPT_SPEC
    assert "TIEMPOS DE REFERENCIA" in spec
    assert "NO la redondees" in spec
    # las cifras del prompt salen de la misma tabla que el estimador
    assert "4:20" in spec           # SkiErg 1000 m
    assert "5:00" in spec           # wall balls 100 reps
