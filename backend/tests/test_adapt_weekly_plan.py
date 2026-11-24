"""adapt_weekly_plan: aplicar una regla semanal a TODO el plan de una sola vez.

El caso real: "de aquí al Hyrox quiero 2 sesiones de Hyrox a la semana, el resto
running y nada de gym". Goggins lo intentaba con una llamada por sesión, se
quedaba sin respuesta a medias y dejaba semanas con 1 sola sesión de Hyrox.
"""
from datetime import date, timedelta

import pytest

from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import agent_tools, plan_overview as po
from app.services.agent_tools import execute_tool

HOY = date(2026, 11, 24)            # martes
LUNES_1 = date(2026, 11, 23)
CARRERA = date(2027, 2, 7)          # domingo: semana de carrera = lunes 1 feb
SEMANAS_ANTES_DE_CARRERA = 10       # 23 nov .. 25 ene
REGLA = {"hyrox_per_week": 2, "remove_types": ["strength"], "end_date": "2027-02-07"}


@pytest.fixture(autouse=True)
def _hoy(monkeypatch):
    monkeypatch.setattr(agent_tools, "today_madrid", lambda: HOY)


def _w(db, user, goal, dia, tipo, status=WorkoutStatus.planned):
    w = Workout(user_id=user.id, goal_id=goal.id, date=dia, day_of_week=dia.weekday(), type=tipo, status=status)
    db.add(w)
    return w


@pytest.fixture()
def plan(db, user):
    """El plan de las capturas: 1 Hyrox por semana + 1 gym, hasta la semana de carrera."""
    hyrox = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao", hyrox_division="dobles mixto",
                 target_race_date=CARRERA, is_active=True)
    media = Goal(user_id=user.id, type=GoalType.race, description="Media SS", target_race_date=date(2027, 4, 4), is_active=True)
    db.add_all([hyrox, media]); db.commit()
    T = WorkoutType
    # semana 1 (la actual): martes rodaje, jueves gym, sábado Hyrox
    _w(db, user, hyrox, LUNES_1 + timedelta(days=1), T.easy_run)
    _w(db, user, hyrox, LUNES_1 + timedelta(days=3), T.strength_full)
    _w(db, user, hyrox, LUNES_1 + timedelta(days=5), T.hyrox_stations)
    # semana 2: viernes Hyrox, sábado gym
    m = LUNES_1 + timedelta(weeks=1)
    for d, t in ((0, T.easy_run), (1, T.intervals), (4, T.hyrox_stations), (5, T.strength_lower), (6, T.long_run)):
        _w(db, user, hyrox, m + timedelta(days=d), t)
    # semanas 3..10: jueves gym, sábado Hyrox (simulacro / estaciones alternando)
    for k in range(2, SEMANAS_ANTES_DE_CARRERA):
        m = LUNES_1 + timedelta(weeks=k)
        sab = T.hyrox_sim if k % 2 == 0 else T.hyrox_stations
        for d, t in ((0, T.easy_run), (1, T.tempo), (3, T.strength_upper), (5, sab), (6, T.long_run)):
            _w(db, user, hyrox, m + timedelta(days=d), t)
    # semana de carrera (1 feb): rodaje, gym el miércoles, carrera el domingo
    m = LUNES_1 + timedelta(weeks=SEMANAS_ANTES_DE_CARRERA)
    for d, t in ((0, T.easy_run), (2, T.strength_full), (4, T.easy_run), (6, T.race)):
        _w(db, user, hyrox, m + timedelta(days=d), t)
    db.commit()
    return hyrox, media


def _semanas(db, user):
    return po.overview(db, user.id, LUNES_1, CARRERA)


def _planificados(db, tipos):
    return db.query(Workout).filter(Workout.status == WorkoutStatus.planned, Workout.type.in_(tipos)).all()


STRENGTH = [WorkoutType.strength_upper, WorkoutType.strength_lower, WorkoutType.strength_full]


def test_cada_semana_hasta_la_carrera_acaba_con_2_hyrox_y_sin_gym(db, user, plan):
    out = execute_tool("adapt_weekly_plan", REGLA, user, db)
    assert out["ok"] and out["mutation"] == "adapt_weekly_plan"
    semanas = _semanas(db, user)
    assert len(semanas) == SEMANAS_ANTES_DE_CARRERA + 1
    for s in semanas[:-1]:
        assert s["counts"]["hyrox"] == 2, s["week_start"]
        assert s["counts"]["strength"] == 0, s["week_start"]
    # la semana de carrera no recibe Hyrox nuevos (taper), pero el gym también se quita
    assert semanas[-1]["counts"]["hyrox"] == 0 and semanas[-1]["counts"]["strength"] == 0
    assert semanas[-1]["counts"]["race"] == 1
    assert out["removed"] == 1 + 1 + 8 + 1          # 11 sesiones de gym planificadas
    assert out["added"] == 10                        # una por cada una de las 10 semanas con 1 sola
    assert not _planificados(db, STRENGTH)


def test_las_sesiones_nuevas_son_wods_completos_con_los_pesos_de_su_division(db, user, plan):
    hyrox, _ = plan
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    nuevas = db.query(Workout).filter(Workout.modified_by == "user").all()
    assert len(nuevas) == 10
    for w in nuevas:
        assert w.type == WorkoutType.hyrox_stations and w.status == WorkoutStatus.planned
        assert w.goal_id == hyrox.id                                   # antes de la carrera: su bloque
        assert w.date >= HOY and w.date != CARRERA
        assert w.structure and w.structure["blocks"] and w.structure["estimate"]["total_min"] == w.planned_duration_min
        assert 28 <= w.planned_duration_min <= 65
        assert w.instructions and "Dobles mixto" in w.instructions
    assert len({w.instructions.split(":")[0] for w in nuevas}) >= 4     # rotan las plantillas, no son clones


def test_la_semana_actual_solo_se_toca_de_hoy_en_adelante_y_aprovecha_el_hueco_del_gym(db, user, plan):
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    nueva = [w for w in db.query(Workout).filter(Workout.modified_by == "user")
             if LUNES_1 <= w.date < LUNES_1 + timedelta(days=7)]
    assert [str(w.date) for w in nueva] == ["2026-11-26"]              # el jueves del gym que se quitó


def test_nunca_dos_sesiones_el_mismo_dia_si_hay_huecos(db, user, plan):
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    por_dia: dict = {}
    for w in db.query(Workout).filter(Workout.status == WorkoutStatus.planned):
        por_dia.setdefault(w.date, []).append(w)
    assert all(len(v) == 1 for v in por_dia.values())


def test_no_planifica_hyrox_el_dia_antes_de_la_tirada_larga_si_hay_otra_opcion(db, user, plan):
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    for w in db.query(Workout).filter(Workout.modified_by == "user"):
        manana = db.query(Workout).filter(Workout.date == w.date + timedelta(days=1), Workout.type == WorkoutType.long_run).count()
        assert not manana, w.date


def test_lo_completado_no_se_toca_ni_se_cuenta_como_gym_a_quitar(db, user, plan):
    hyrox, _ = plan
    hecho = Workout(user_id=user.id, goal_id=hyrox.id, date=date(2026, 12, 11), type=WorkoutType.strength_full,
                    status=WorkoutStatus.completed, day_of_week=4)
    db.add(hecho); db.commit()
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    assert db.query(Workout).get(hecho.id) is not None
    assert db.query(Workout).get(hecho.id).status == WorkoutStatus.completed


def test_repetirlo_no_cambia_nada(db, user, plan):
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    n = db.query(Workout).count()
    again = execute_tool("adapt_weekly_plan", REGLA, user, db)
    assert again["ok"] and again["added"] == 0 and again["removed"] == 0 and "mutation" not in again
    assert db.query(Workout).count() == n


def test_el_informe_cuenta_semana_a_semana_con_los_numeros_del_servidor(db, user, plan):
    out = execute_tool("adapt_weekly_plan", REGLA, user, db)
    linea = next(l for l in out["weeks"] if l.startswith("2026-12-07"))
    assert "hyrox 1→2" in linea and "fuerza 1→0" in linea
    assert out["weeks_race_skipped"] == ["2027-02-01"]
    assert "2 Hyrox por semana" in out["summary"]


def test_solo_hyrox_sin_quitar_el_gym(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {"hyrox_per_week": 2, "end_date": "2027-02-07"}, user, db)
    assert out["ok"] and out["added"] == 10 and out["removed"] == 0
    assert len(_planificados(db, STRENGTH)) == 11


def test_solo_quitar_el_gym_sin_anadir_hyrox(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {"remove_types": ["gym"], "end_date": "2027-02-07"}, user, db)
    assert out["ok"] and out["removed"] == 11 and out["added"] == 0


def test_tipos_concretos_de_fuerza_tambien_valen(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {"remove_types": ["strength_upper"], "end_date": "2027-02-07"}, user, db)
    assert out["removed"] == 8                      # solo los de tren superior (semanas 3..10)
    assert len(_planificados(db, [WorkoutType.strength_full, WorkoutType.strength_lower])) == 3


def test_con_skip_race_week_false_tambien_se_completa_la_semana_de_carrera(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {**REGLA, "skip_race_week": False}, user, db)
    ultima = _semanas(db, user)[-1]
    assert ultima["counts"]["hyrox"] == 2 and out["weeks_race_skipped"] == []
    # nunca el día de la carrera ni después
    assert not db.query(Workout).filter(Workout.modified_by == "user", Workout.date >= CARRERA).count()


def test_una_semana_sin_hueco_se_avisa_en_vez_de_apilar_sesiones(db, user, plan):
    hyrox, _ = plan
    m = LUNES_1 + timedelta(weeks=3)                 # semana del 14 dic
    # sin gym en esa semana y con TODOS los días ocupados: no hay dónde meter el 2º Hyrox
    for w in db.query(Workout).filter(Workout.date >= m, Workout.date < m + timedelta(days=7),
                                      Workout.type == WorkoutType.strength_upper):
        db.delete(w)
    db.commit()
    for d in range(7):
        if not db.query(Workout).filter(Workout.date == m + timedelta(days=d)).count():
            _w(db, user, hyrox, m + timedelta(days=d), WorkoutType.mobility)
    db.commit()
    out = execute_tool("adapt_weekly_plan", REGLA, user, db)
    assert out["ok"] and out["weeks_without_room"] == ["2026-12-14"]
    assert po.overview(db, user.id, m, m)[0]["counts"]["hyrox"] == 1 and out["added"] == 9
    assert any("SIN HUECO" in l for l in out["weeks"]) and "SIN HUECO" in out["summary"]


def test_la_misma_semana_pasada_se_ignora(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {**REGLA, "start_date": "2026-12-07", "end_date": "2026-12-20"}, user, db)
    assert out["added"] == 2 and out["removed"] == 2
    assert po.overview(db, user.id, LUNES_1, LUNES_1)[0]["counts"]["hyrox"] == 1      # la semana actual, intacta


@pytest.mark.parametrize("args", [
    {},                                                             # nada que hacer
    {"hyrox_per_week": 9},
    {"hyrox_per_week": 0},
    {"hyrox_per_week": "dos"},
    {"remove_types": ["race"]},
    {"remove_types": ["rest"]},
    {"remove_types": ["inventado"]},
    {"hyrox_per_week": 2, "start_date": "2027-01-10", "end_date": "2026-12-01"},
    {"hyrox_per_week": 2, "end_date": "2030-01-01"},
])
def test_peticiones_invalidas_se_rechazan_sin_tocar_nada(db, user, plan, args):
    n = db.query(Workout).count()
    out = execute_tool("adapt_weekly_plan", args, user, db)
    assert not out["ok"] and out["error"]
    assert db.query(Workout).count() == n


def test_sesiones_de_hyrox_sin_fecha_de_fin_llegan_hasta_el_ultimo_hyrox_no_hasta_la_media(db, user, plan):
    hyrox, media = plan
    # plan combinado: el bloque de la media también tiene entrenos planificados
    _w(db, user, media, date(2027, 2, 15), WorkoutType.easy_run)
    db.commit()
    out = execute_tool("adapt_weekly_plan", {"hyrox_per_week": 2}, user, db)
    assert out["ok"] and out["range"]["to"] == "2027-02-07"
    # y no se ha metido Hyrox en el bloque de la media
    assert not db.query(Workout).filter(Workout.modified_by == "user", Workout.date > CARRERA).count()


def test_quitar_sin_fecha_de_fin_llega_hasta_la_ultima_carrera_del_plan(db, user, plan):
    hyrox, media = plan
    _w(db, user, media, date(2027, 2, 15), WorkoutType.strength_full)
    db.commit()
    out = execute_tool("adapt_weekly_plan", {"remove_types": ["strength"]}, user, db)
    assert out["ok"] and out["range"]["to"] == "2027-04-04"
    assert not _planificados(db, STRENGTH)


def test_con_un_solo_objetivo_en_el_plan_llega_hasta_su_carrera(db, user, plan):
    out = execute_tool("adapt_weekly_plan", {"hyrox_per_week": 2}, user, db)
    assert out["ok"] and out["range"]["to"] == "2027-02-07"


def test_otro_usuario_no_se_toca(db, user, other_user, plan):
    ajeno = Workout(user_id=other_user.id, date=date(2026, 12, 10), type=WorkoutType.strength_full, status=WorkoutStatus.planned)
    db.add(ajeno); db.commit()
    execute_tool("adapt_weekly_plan", REGLA, user, db)
    assert db.query(Workout).get(ajeno.id) is not None


# --- de punta a punta, por el chat: tu petición real, una sola vez ---------------

def test_por_el_chat_una_sola_peticion_deja_todo_el_plan_bien(db, user, plan, monkeypatch):
    from app.services import goggins_agent

    monkeypatch.setattr(goggins_agent, "today_madrid", lambda: HOY)

    class _Block:
        def __init__(self, **kw): self.__dict__.update(kw)
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items()}

    class _Stream:
        def __init__(self, texto, bloques, stop): self.t, self.b, self.s = texto, bloques, stop
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def text_stream(self):
            if self.t:
                yield self.t
        def get_final_message(self):
            class _M: pass
            m = _M(); m.content, m.stop_reason = self.b, self.s
            return m

    guion = [
        ("", [_Block(type="tool_use", id="t1", name="plan_overview", input={})], "tool_use"),
        ("", [_Block(type="tool_use", id="t2", name="adapt_weekly_plan", input=REGLA)], "tool_use"),
        ("Hecho: 2 Hyrox por semana hasta Bilbao y cero gym.",
         [_Block(type="text", text="Hecho: 2 Hyrox por semana hasta Bilbao y cero gym.")], "end_turn"),
    ]
    llamadas = []

    class _Cliente:
        class messages:
            @staticmethod
            def stream(**kw):
                llamadas.append({**kw, "messages": list(kw["messages"])})
                return _Stream(*guion[len(llamadas) - 1])

    monkeypatch.setattr(goggins_agent.ai_client, "get_client", lambda: _Cliente())

    eventos = list(goggins_agent.chat_stream(
        user, db,
        "esta semana tengo poco entreno, no? el resto de semanas hasta la prueba del hyrox quiero 2 sesiones de hyrox "
        "semanales y después running, y no quiero sesión de gym. Adapta el plan con esto"))
    done = eventos[-1]

    assert len(llamadas) == 3 and done["phase"] == "done"
    # Goggins parte con el plan por semanas ya contado por el servidor (sin contar a mano)
    assert "plan_weeks" in llamadas[0]["system"] and "hyrox 1" in llamadas[0]["system"]
    # la tool recibió el informe y se lo devolvió al modelo para confirmar con esos números
    resultado = llamadas[2]["messages"][-1]["content"][0]["content"]
    assert "hyrox 1→2" in resultado and "adapt_weekly_plan" in resultado
    # y el plan quedó bien de verdad, todas las semanas
    for s in _semanas(db, user)[:-1]:
        assert s["counts"]["hyrox"] == 2 and s["counts"]["strength"] == 0, s["week_start"]
    assert [m["mutation"] for m in done["mutations"]] == ["adapt_weekly_plan"]
    # y en el historial del siguiente turno queda lo que de verdad se ejecutó
    from app.services.goggins_agent import _load_history
    ultimo = [m for m in _load_history(user.id, db) if m["role"] == "assistant"][-1]["content"]
    assert "adapt_weekly_plan ×1" in ultimo and "Registro del sistema" in ultimo
