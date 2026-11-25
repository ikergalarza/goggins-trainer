"""Goggins: noción de la fecha y honestidad al editar el plan.

Síntomas reales: "se lía con el día que es" y "me dice que lo ha metido y no
está en el plan" (afirmaba el cambio sin llamar a ninguna herramienta).
"""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.models.chat_message import ChatMessage
from app.models.goal import Goal, GoalType
from app.models.strava_activity import StravaActivity
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import goggins_agent, strava as strava_service, workout_feedback

DOMINGO = date(2026, 11, 22)


@pytest.fixture(autouse=True)
def _reloj(monkeypatch):
    """Domingo 22 nov 2026, 10:15 hora española."""
    from app.services import agent_tools
    from app.services.clock import TZ
    ahora = datetime(2026, 11, 22, 10, 15, tzinfo=TZ)
    monkeypatch.setattr(goggins_agent, "today_madrid", lambda: DOMINGO)
    monkeypatch.setattr(goggins_agent, "now_madrid", lambda: ahora)
    monkeypatch.setattr(agent_tools, "today_madrid", lambda: DOMINGO)


# --- contexto: calendario explícito -------------------------------------------

def test_el_contexto_trae_un_calendario_de_las_proximas_semanas(db, user):
    ctx = goggins_agent._build_athlete_context(user, db)
    assert ctx["this_week"] == {"monday": "2026-11-16", "sunday": "2026-11-22"}
    assert ctx["next_week"] == {"monday": "2026-11-23", "sunday": "2026-11-29"}
    cal = ctx["calendar"]
    assert len(cal) == 21
    assert cal[0].startswith("2026-11-22 domingo") and "HOY" in cal[0]
    assert cal[1].startswith("2026-11-23 lunes") and "MAÑANA" in cal[1]
    viernes = next(c for c in cal if c.startswith("2026-11-27"))
    assert "viernes" in viernes and "semana que viene" in viernes


def test_el_contexto_lleva_el_id_de_cada_objetivo(db, user):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox Bilbao", is_active=True)
    db.add(g); db.commit()
    ctx = goggins_agent._build_athlete_context(user, db)
    assert ctx["active_goals"][0]["id"] == g.id


def test_el_contexto_no_recorta_los_proximos_entrenos_a_20(db, user, make_workout):
    for i in range(30):
        make_workout(user, date=date(2026, 11, 23), day_of_week=0)
    ctx = goggins_agent._build_athlete_context(user, db)
    assert len(ctx["upcoming_workouts"]) == 30


# --- historial: cada mensaje del atleta lleva SU fecha ------------------------

def test_el_historial_etiqueta_la_fecha_de_los_mensajes_del_atleta(db, user):
    # viernes 20 nov 21:30 UTC = 22:30 en España
    db.add(ChatMessage(user_id=user.id, role="user", content="muéveme el de mañana",
                       created_at=datetime(2026, 11, 20, 21, 30, tzinfo=timezone.utc)))
    db.add(ChatMessage(user_id=user.id, role="assistant", content="Te muevo el de HOY al lunes",
                       created_at=datetime(2026, 11, 20, 21, 31, tzinfo=timezone.utc)))
    db.commit()
    h = goggins_agent._load_history(user.id, db)
    assert h[0]["role"] == "user"
    assert h[0]["content"].startswith("[Enviado el viernes 20/11/2026 a las 22:30]")
    assert h[0]["content"].endswith("muéveme el de mañana")
    assert h[1] == {"role": "assistant", "content": "Te muevo el de HOY al lunes"}   # sin etiqueta


def test_el_historial_acepta_fechas_sin_zona_horaria(db, user):
    db.add(ChatMessage(user_id=user.id, role="user", content="hola",
                       created_at=datetime(2026, 7, 1, 8, 0)))     # naive = UTC; julio = UTC+2
    db.commit()
    assert "01/07/2026 a las 10:00" in goggins_agent._load_history(user.id, db)[0]["content"]


# --- detector: ¿afirma un cambio? / ¿lo está pidiendo el atleta? ---------------

@pytest.mark.parametrize("texto", [
    "Hecho. Te lo he metido el viernes.",
    "Ahora sí. Viernes 27/11 metido: compromised de 4 rondas.",
    "Lo muevo al lunes y listo.",
    "Añadido el entreno del jueves.",
    "He cambiado tu tempo por series.",
    "Listo: ya está en tu plan.",
    # textos reales de producción
    "Tienes razón. Dije que lo hacía y no ejecuté la herramienta. Fallo mío. Lo meto AHORA.",
    "Ahora sí. Viernes 27/11 metido: compromised de 4 rondas con sled push a 152 kg (id 1167).",
])
def test_detecta_cuando_afirma_un_cambio(texto):
    assert goggins_agent.claims_plan_change(texto)


@pytest.mark.parametrize("texto", [
    "No he movido nada todavía. ¿Qué día prefieres?",
    "Tu tempo del jueves son 9 km a 4:40.",
    "Si quieres lo ajusto ahora, dímelo.",
    "Sin cambios por ahora: aún no he tocado el plan.",
    "",
])
def test_no_confunde_explicaciones_ni_negaciones_con_cambios(texto):
    assert not goggins_agent.claims_plan_change(texto)


@pytest.mark.parametrize("texto", [
    "mete un día más de entrenamiento a la semana",
    "añade movilidad todos los días",
    "ponme un entreno el viernes",
    "mueve el del jueves al sábado",
    "quiero entrenar un día más",
    "quita el tempo",
])
def test_detecta_cuando_el_atleta_pide_un_cambio(texto):
    assert goggins_agent.asks_plan_change(texto)


@pytest.mark.parametrize("texto", [
    "¿cómo voy de volumen esta semana?",
    "quiero saber cuántos km llevo",
    "¿puedes explicarme qué es el umbral?",
    "dime qué tengo mañana",
])
def test_una_consulta_no_es_una_peticion_de_cambio(texto):
    assert not goggins_agent.asks_plan_change(texto)


def test_baja_la_carga_si_es_una_peticion():
    assert goggins_agent.asks_plan_change("baja la carga de esta semana")


# --- bucle del agente con un cliente de IA simulado ---------------------------

class _Text:
    type = "text"

    def __init__(self, text): self.text = text
    def model_dump(self): return {"type": "text", "text": self.text}


class _ToolUse:
    type = "tool_use"

    def __init__(self, id, name, input): self.id, self.name, self.input = id, name, input
    def model_dump(self): return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


class _Msg:
    def __init__(self, content, stop_reason): self.content, self.stop_reason = content, stop_reason


class _Stream:
    def __init__(self, text, blocks, stop): self._t, self._b, self._s = text, blocks, stop
    def __enter__(self): return self
    def __exit__(self, *a): return False

    @property
    def text_stream(self):
        if self._t:
            mitad = len(self._t) // 2
            yield self._t[:mitad]
            yield self._t[mitad:]

    def get_final_message(self): return _Msg(self._b, self._s)


def _fake_ai(monkeypatch, guion):
    """guion = [(texto, [bloques], stop_reason), ...]; devuelve la lista de llamadas."""
    llamadas: list[dict] = []

    class _C:
        class messages:
            @staticmethod
            def stream(**kw):
                llamadas.append({**kw, "messages": list(kw["messages"])})
                t, b, s = guion[len(llamadas) - 1]
                return _Stream(t, b, s)

    monkeypatch.setattr(goggins_agent.ai_client, "get_client", lambda: _C())
    return llamadas


def _correr(user, db, mensaje):
    return list(goggins_agent.chat_stream(user, db, mensaje))


def test_afirmar_un_cambio_sin_ejecutarlo_se_corrige_y_se_ejecuta(db, user, monkeypatch):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2027, 2, 7), is_active=True)
    db.add(g); db.commit()
    llamadas = _fake_ai(monkeypatch, [
        ("Hecho. Te lo he metido el viernes 27.", [_Text("Hecho. Te lo he metido el viernes 27.")], "end_turn"),
        ("", [_ToolUse("t1", "add_workout", {"date": "2026-11-27", "type": "hyrox_stations", "duration_min": 50})], "tool_use"),
        ("Viernes 27/11 metido de verdad.", [_Text("Viernes 27/11 metido de verdad.")], "end_turn"),
    ])
    eventos = _correr(user, db, "mete un día más de hyrox a la semana")

    assert {"phase": "retract"} in eventos                                  # el texto falso se retira
    w = db.query(Workout).filter(Workout.date == date(2026, 11, 27)).one()    # y el cambio EXISTE
    assert w.type == WorkoutType.hyrox_stations
    done = eventos[-1]
    assert done["phase"] == "done"
    assert done["content"] == "Viernes 27/11 metido de verdad."              # nada del texto falso
    assert len(done["mutations"]) == 1
    # el modelo recibió el aviso de que NO había ejecutado nada
    aviso = llamadas[1]["messages"][-1]
    assert aviso["role"] == "user" and "NO has ejecutado" in aviso["content"]
    # lo guardado en el chat es la respuesta buena
    assert db.query(ChatMessage).filter_by(role="assistant").one().content == "Viernes 27/11 metido de verdad."


def test_si_tras_el_aviso_sigue_sin_ejecutar_se_lo_dice_al_atleta(db, user, monkeypatch):
    falso = "Hecho, ya lo he añadido."
    _fake_ai(monkeypatch, [(falso, [_Text(falso)], "end_turn"), (falso, [_Text(falso)], "end_turn")])
    eventos = _correr(user, db, "añade un entreno el viernes")
    done = eventos[-1]
    assert done["mutations"] == []
    assert "No he ejecutado ningún cambio" in done["content"]
    assert db.query(Workout).count() == 0


def test_con_la_tool_ejecutada_no_hay_reintento(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "add_workout", {"date": "2026-11-27", "type": "easy_run"})], "tool_use"),
        ("Hecho, viernes metido.", [_Text("Hecho, viernes metido.")], "end_turn"),
    ])
    eventos = _correr(user, db, "mete un rodaje el viernes")
    assert len(llamadas) == 2
    assert {"phase": "retract"} not in eventos


def test_una_pregunta_no_dispara_el_aviso(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [("Ayer moví tu tempo; vas bien de volumen.", [_Text("Ayer moví tu tempo; vas bien de volumen.")], "end_turn")])
    eventos = _correr(user, db, "¿cómo voy de volumen?")
    assert len(llamadas) == 1 and {"phase": "retract"} not in eventos


def test_la_negacion_no_cuenta_como_afirmacion(db, user, monkeypatch):
    t = "No he movido nada todavía. ¿Qué día prefieres?"
    llamadas = _fake_ai(monkeypatch, [(t, [_Text(t)], "end_turn")])
    _correr(user, db, "mueve el entreno del jueves")
    assert len(llamadas) == 1


def test_el_mensaje_actual_va_con_su_fecha_y_hora_pero_se_guarda_limpio(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [("Dime.", [_Text("Dime.")], "end_turn")])
    _correr(user, db, "hola")
    ultimo = llamadas[0]["messages"][-1]["content"]
    assert ultimo.startswith("[Enviado ahora: domingo 22/11/2026 a las 10:15]") and ultimo.endswith("hola")
    assert db.query(ChatMessage).filter_by(role="user").one().content == "hola"
    # y el sistema recuerda que es domingo y cuál es la semana que viene
    assert "DOMINGO 2026-11-22" in llamadas[0]["system"]


# --- promesa implícita: "empezamos ya" sin ejecutar nada ni preguntar -----------

PROMESA = ("Aviso de hierro: 6 días/semana con cero km reales las últimas 2 semanas es un salto brutal. "
           "Pero empezamos ya. Who's gonna carry the boats?")


def test_una_promesa_sin_ejecutar_ni_preguntar_tambien_se_corrige(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [
        (PROMESA, [_Text(PROMESA)], "end_turn"),
        ("", [_ToolUse("t1", "add_workout", {"date": "2026-11-27", "type": "easy_run"})], "tool_use"),
        ("Viernes 27 metido.", [_Text("Viernes 27 metido.")], "end_turn"),
    ])
    eventos = _correr(user, db, "mete un día más de entrenamiento a la semana")
    assert {"phase": "retract"} in eventos
    assert "ni hacerle una pregunta" in llamadas[1]["messages"][-1]["content"]
    assert db.query(Workout).count() == 1
    assert eventos[-1]["content"] == "Viernes 27 metido."


@pytest.mark.parametrize("respuesta", [
    "¿Qué día prefieres para la sesión extra?",
    "Si quieres lo meto el viernes; dímelo y lo hago.",
])
def test_preguntar_o_ofrecer_no_es_una_promesa(db, user, monkeypatch, respuesta):
    llamadas = _fake_ai(monkeypatch, [(respuesta, [_Text(respuesta)], "end_turn")])
    eventos = _correr(user, db, "mete un día más de entrenamiento a la semana")
    assert len(llamadas) == 1 and {"phase": "retract"} not in eventos


def test_una_consulta_con_respuesta_normal_no_se_reintenta(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [("Llevas 40 km esta semana.", [_Text("Llevas 40 km esta semana.")], "end_turn")])
    _correr(user, db, "quiero saber cuántos km llevo")
    assert len(llamadas) == 1


def test_si_ya_consulto_datos_no_se_considera_promesa(db, user, monkeypatch):
    """Tras mirar el plan, explicar que ya tiene ese día cubierto no es incumplir."""
    llamadas = _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "list_workouts", {})], "tool_use"),
        ("Ya tienes entreno todos los días de esa semana.", [_Text("Ya tienes entreno todos los días de esa semana.")], "end_turn"),
    ])
    eventos = _correr(user, db, "mete un entreno el viernes")
    assert len(llamadas) == 2 and {"phase": "retract"} not in eventos


def test_si_tras_el_aviso_sigue_prometiendo_se_le_avisa_al_atleta(db, user, monkeypatch):
    _fake_ai(monkeypatch, [(PROMESA, [_Text(PROMESA)], "end_turn"), (PROMESA, [_Text(PROMESA)], "end_turn")])
    done = _correr(user, db, "mete un día más de entrenamiento a la semana")[-1]
    assert "No he ejecutado ningún cambio" in done["content"] and done["mutations"] == []


# --- el bucle NO se corta en silencio ------------------------------------------
# Síntoma real: dos respuestas largas acababan en "…con WOD completo y pesos de tu división:"
# y no se había creado nada. Eran llamadas a herramienta cortadas por el límite de longitud
# (max_tokens), que el bucle trataba como el final normal del turno.

def _cortada(texto, *bloques):
    return (texto, [_Text(texto), *bloques], "max_tokens")


def test_una_llamada_cortada_por_longitud_no_se_ejecuta_se_avisa_al_modelo_y_se_reintenta(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [
        _cortada("Lo arreglo AHORA con un segundo Hyrox cada semana:", _ToolUse("t0", "add_workout", {"date": "2026-11-2"})),
        ("", [_ToolUse("t1", "add_workout", {"date": "2026-11-27", "type": "hyrox_stations"})], "tool_use"),
        ("Viernes 27 metido.", [_Text("Viernes 27 metido.")], "end_turn"),
    ])
    eventos = _correr(user, db, "mete un hyrox el viernes")
    assert db.query(Workout).count() == 1                                   # solo la llamada completa
    previo = llamadas[1]["messages"][-2]                                    # lo que el modelo "dijo" antes
    assert previo["role"] == "assistant" and all(b["type"] != "tool_use" for b in previo["content"])
    aviso = llamadas[1]["messages"][-1]
    assert aviso["role"] == "user" and "se cortó por longitud" in aviso["content"] and "NO se ejecutó" in aviso["content"]
    assert eventos[-1]["phase"] == "done" and "continúa" not in eventos[-1]["content"].lower()


def test_si_se_corta_una_y_otra_vez_se_lo_dice_al_atleta_y_como_seguir(db, user, monkeypatch):
    cortada = _cortada("Voy a añadirlos:", _ToolUse("t", "add_workout", {}))
    llamadas = _fake_ai(monkeypatch, [cortada, cortada, cortada])
    done = _correr(user, db, "mete un hyrox el viernes")[-1]
    assert len(llamadas) == 3                                               # el original + 2 reintentos
    assert "se cortó" in done["content"] and "continúa" in done["content"].lower()
    assert "No he ejecutado ningún cambio" in done["content"] or "ningún cambio" in done["content"].lower()


def test_al_llegar_al_limite_de_pasos_dice_lo_hecho_y_como_continuar(db, user, monkeypatch):
    monkeypatch.setattr(goggins_agent, "MAX_TOOL_ITERATIONS", 3)
    paso = ("", [_ToolUse("t", "add_workout", {"date": "2026-11-27", "type": "easy_run"})], "tool_use")
    _fake_ai(monkeypatch, [paso, paso, paso])
    done = _correr(user, db, "mete rodajes")[-1]
    assert "sin margen" in done["content"] and "continúa" in done["content"].lower()
    assert "add_workout" in done["content"] and "3" in done["content"]      # qué y cuántas veces se hizo


def test_lo_realmente_ejecutado_queda_en_el_historial_y_llega_al_modelo_en_el_turno_siguiente(db, user, monkeypatch):
    _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "add_workout", {"date": "2026-11-27", "type": "easy_run"})], "tool_use"),
        ("Listo, viernes metido.", [_Text("Listo, viernes metido.")], "end_turn"),
    ])
    _correr(user, db, "mete un rodaje el viernes")
    asistente = [m for m in goggins_agent._load_history(user.id, db) if m["role"] == "assistant"][-1]["content"]
    assert asistente.startswith("Listo, viernes metido.")
    assert "Registro del sistema" in asistente and "add_workout ×1" in asistente

    llamadas = _fake_ai(monkeypatch, [("Dime.", [_Text("Dime.")], "end_turn")])
    _correr(user, db, "hola")
    previos = [m["content"] for m in llamadas[0]["messages"] if m["role"] == "assistant"]
    assert any("Registro del sistema" in c and "add_workout ×1" in c for c in previos)
    # lo que ve el atleta en el chat sigue limpio
    assert "Registro del sistema" not in db.query(ChatMessage).filter_by(role="assistant").first().content


def test_los_fallos_tambien_quedan_en_el_registro(db, user, monkeypatch):
    _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "add_workout", {"date": "2025-11-27", "type": "easy_run"})], "tool_use"),
        ("No pude.", [_Text("No pude.")], "end_turn"),
    ])
    _correr(user, db, "mete un rodaje el viernes")
    asistente = [m for m in goggins_agent._load_history(user.id, db) if m["role"] == "assistant"][-1]["content"]
    assert "✗ add_workout ×1" in asistente


def test_las_consultas_no_ensucian_el_registro(db, user, monkeypatch):
    _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "plan_overview", {})], "tool_use"),
        ("Tienes 3 sesiones.", [_Text("Tienes 3 sesiones.")], "end_turn"),
    ])
    _correr(user, db, "¿cuántas sesiones tengo?")
    asistente = [m for m in goggins_agent._load_history(user.id, db) if m["role"] == "assistant"][-1]["content"]
    assert "Registro del sistema" not in asistente


def test_dos_mensajes_del_mismo_segundo_no_se_intercambian_en_el_historial(db, user):
    from datetime import datetime, timezone
    t = datetime(2026, 11, 22, 9, 0, 0, tzinfo=timezone.utc)
    db.add(ChatMessage(user_id=user.id, role="user", content="uno", created_at=t))
    db.add(ChatMessage(user_id=user.id, role="assistant", content="dos", created_at=t))
    db.add(ChatMessage(user_id=user.id, role="user", content="tres", created_at=t))
    db.commit()
    assert [m["role"] for m in goggins_agent._load_history(user.id, db)] == ["user", "assistant", "user"]


# --- el contexto trae el plan por semanas contado por el servidor ---------------

def test_el_contexto_trae_el_plan_por_semanas_contado_por_el_servidor(db, user, make_workout):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", target_race_date=date(2026, 12, 20), is_active=True)
    db.add(g); db.commit()
    make_workout(user, goal=g, date=date(2026, 12, 12), type=WorkoutType.hyrox_sim)         # semana del 7
    make_workout(user, goal=g, date=date(2026, 12, 17), type=WorkoutType.hyrox_stations)    # semana del 14
    ctx = goggins_agent._build_athlete_context(user, db)
    lineas = {l.split(" · ")[0]: l for l in ctx["plan_weeks"]}
    # una sesión el sábado 12 y otra el jueves 17: UNA por semana, no dos en la misma
    assert "hyrox 1" in lineas["2026-12-07"] and "hyrox 1" in lineas["2026-12-14"]
    assert ctx["plan_weeks"][0].startswith("2026-11-16")                                    # arranca en la semana de HOY
    assert ctx["plan_weeks"][-1].startswith("2026-12-14")                                   # y acaba en la de la carrera


# --- herramientas de lectura compactas ------------------------------------------

def test_list_workouts_va_compacto_sin_el_wod_entero(db, user, make_workout):
    from app.services.agent_tools import execute_tool
    make_workout(user, date=date(2026, 11, 23), structure={"blocks": [{"items": [{"exercise": "run", "distance_m": 400}]}]})
    w = execute_tool("list_workouts", {"start_date": "2026-11-23", "end_date": "2026-11-23"}, user, db)["workouts"][0]
    assert "structure" not in w and "instructions" not in w
    assert w["has_wod"] is True and w["weekday"] == "lunes"
    det = execute_tool("list_workouts", {"start_date": "2026-11-23", "end_date": "2026-11-23", "include_details": True}, user, db)
    assert det["workouts"][0]["structure"]["blocks"]


def test_el_detalle_completo_solo_para_pocas_sesiones(db, user, make_workout):
    from app.services.agent_tools import execute_tool
    for _ in range(9):
        make_workout(user, date=date(2026, 11, 23))
    out = execute_tool("list_workouts", {"start_date": "2026-11-23", "end_date": "2026-11-23", "include_details": True}, user, db)
    assert not out["ok"] and "máximo" in out["error"].lower() or "máx" in out["error"].lower()


def test_plan_overview_cuenta_por_semanas_y_valida_fechas(db, user, make_workout):
    from app.services.agent_tools import execute_tool
    make_workout(user, date=date(2026, 12, 12), type=WorkoutType.hyrox_sim)
    make_workout(user, date=date(2026, 12, 17), type=WorkoutType.hyrox_stations)
    out = execute_tool("plan_overview", {"start_date": "2026-12-07", "end_date": "2026-12-20"}, user, db)
    assert out["ok"] and [w["counts"]["hyrox"] for w in out["weeks"]] == [1, 1]
    assert out["summary_lines"][0].startswith("2026-12-07")
    assert not execute_tool("plan_overview", {"start_date": "2025-01-01"}, user, db)["ok"]


def test_el_prompt_enseña_a_usar_las_herramientas_de_varias_semanas():
    p = goggins_agent.SYSTEM_PROMPT
    assert "adapt_weekly_plan" in p and "plan_overview" in p
    assert "NUNCA cuentes" in p and "Registro del sistema" in p


# --- lo que ve el atleta sale limpio -------------------------------------------

def test_el_registro_y_las_etiquetas_de_fecha_no_se_cuelan_en_lo_que_ve_el_atleta(db, user, monkeypatch):
    sucio = ("[Enviado ahora: domingo 22/11/2026 a las 10:15]\nListo, viernes metido.\n\n"
             "[Registro del sistema — lo que SE EJECUTÓ de verdad en ese turno (fíate de esto, no del texto): ✓ add_workout ×1]")
    _fake_ai(monkeypatch, [(sucio, [_Text(sucio)], "end_turn")])
    done = _correr(user, db, "¿qué tal?")[-1]
    assert done["content"] == "Listo, viernes metido."
    assert db.query(ChatMessage).filter_by(role="assistant").one().content == "Listo, viernes metido."


def test_leer_el_plan_de_hace_semanas_si_se_puede(db, user, make_workout):
    from app.services.agent_tools import execute_tool
    make_workout(user, date=date(2026, 10, 26), type=WorkoutType.hyrox_stations)           # hace 4 semanas
    out = execute_tool("plan_overview", {"start_date": "2026-10-26", "end_date": "2026-11-01"}, user, db)
    assert out["ok"] and out["weeks"][0]["counts"]["hyrox"] == 1


def test_toda_herramienta_nueva_esta_clasificada_como_de_lectura_o_de_edicion():
    """Si una tool que modifica datos no está en MUTATING_TOOLS, no cuenta como "cambio hecho" para la
    guarda y no queda en el registro del historial. Esto obliga a clasificar cada herramienta nueva."""
    from app.services import agent_tools
    solo_lectura = {"list_workouts", "plan_overview", "get_strava_summary", "compare_planned_vs_actual"}
    todas = {t["name"] for t in agent_tools.TOOLS}
    assert solo_lectura <= todas
    assert goggins_agent.MUTATING_TOOLS == todas - solo_lectura


# --- consulta, promete y no hace: la captura del 25-11 -------------------------

PROMESA_TRAS_LEER = ("Ocho semanas con un solo Hyrox. Tenías toda la razón. "
                     "Lo arreglo AHORA con un segundo Hyrox en cada una. Y no hay ningún gym que quitar.")


def test_prometer_despues_de_consultar_tambien_obliga_a_ejecutar(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [
        ("", [_ToolUse("t1", "list_workouts", {})], "tool_use"),
        (PROMESA_TRAS_LEER, [_Text(PROMESA_TRAS_LEER)], "end_turn"),
        ("", [_ToolUse("t2", "add_workout", {"date": "2026-11-27", "type": "hyrox_stations"})], "tool_use"),
        ("Hecho.", [_Text("Hecho.")], "end_turn"),
    ])
    eventos = _correr(user, db, "pero te faltan todo el resto de semanas, añade el segundo hyrox")
    assert {"phase": "retract"} in eventos and len(llamadas) == 4
    assert db.query(Workout).count() == 1


@pytest.mark.parametrize("texto", [
    "continúa", "Continua", "sigue", "hazlo", "aplícalo", "aplica lo nuevo que te he dicho entonces",
    "los has añadido ya?", "¿lo has cambiado?",
])
def test_los_seguimientos_de_una_peticion_cuentan_como_peticion(texto):
    assert goggins_agent.asks_plan_change(texto)


@pytest.mark.parametrize("texto", [
    "Lo arreglo AHORA con un segundo Hyrox en cada una.",
    "Voy a añadir el segundo Hyrox en cada semana.",
    "Ahora los meto todos.",
    "Te lo monto ya.",
])
def test_detecta_el_compromiso_sin_ejecutar(texto):
    assert goggins_agent.commits_without_doing(texto)


@pytest.mark.parametrize("texto", [
    "Ya tienes entreno todos los días de esa semana.",
    "Esa semana lleva dos Hyrox, no hace falta tocar nada.",
    "No voy a meter más carga: sería lesionarte.",
])
def test_explicar_no_es_comprometerse(texto):
    assert not goggins_agent.commits_without_doing(texto)


def test_las_cifras_de_actividad_salen_del_contexto_no_de_mensajes_viejos():
    p = goggins_agent.SYSTEM_PROMPT
    assert "NUNCA repitas cifras de mensajes anteriores" in p and "last_14_days" in p
    assert "strava_data" in p


def test_a_un_atleta_de_hyrox_goggins_le_exige_sesiones_completas(db, user, monkeypatch):
    g = Goal(user_id=user.id, type=GoalType.hyrox, description="Hyrox", is_active=True)
    db.add(g); db.commit()
    llamadas = _fake_ai(monkeypatch, [("Ok.", [_Text("Ok.")], "end_turn")])
    _correr(user, db, "hola")
    assert "3-4 estaciones distintas en 2-3 bloques" in llamadas[0]["system"]


# --- datos frescos de Strava antes de hablar de kilómetros ----------------------
# Síntoma real: "0 km en 14 días" con tres carreras hechas. Strava solo se
# sincronizaba con el botón del Dashboard y Goggins leía datos de hacía dos semanas.

AYER = datetime.now(timezone.utc).replace(hour=12) - timedelta(days=1)


@pytest.fixture(autouse=True)
def _sin_memoria_de_sync(monkeypatch):
    monkeypatch.setattr(strava_service, "_last_refresh", {}, raising=False)
    monkeypatch.setattr(workout_feedback, "generate_for_completed", lambda *a, **k: 0)


def _conectar_strava(db, user):
    user.strava_access_token = "token-de-prueba"
    user.strava_refresh_token = "refresh-de-prueba"
    user.strava_token_expires_at = 4_000_000_000
    db.add(user); db.commit()


def _sync_que_trae_una_carrera(monkeypatch):
    llamadas: list[int] = []

    def sync(u, s, pages=2):
        llamadas.append(pages)
        if len(llamadas) > 1:
            return 0
        s.add(StravaActivity(user_id=u.id, strava_id=1, type="Run", distance_m=8000,
                             moving_time_s=2700, start_date=AYER))
        s.commit()
        return 1

    monkeypatch.setattr(strava_service, "sync_activities", sync)
    return llamadas


def test_antes_de_responder_trae_lo_ultimo_de_strava(db, user, monkeypatch):
    _conectar_strava(db, user)
    sincronizaciones = _sync_que_trae_una_carrera(monkeypatch)
    llamadas = _fake_ai(monkeypatch, [("Ok.", [_Text("Ok.")], "end_turn")] * 2)

    _correr(user, db, "¿cómo voy?")
    assert '"total_km": 8.0' in llamadas[0]["system"]
    assert '"strava_data": "al día' in llamadas[0]["system"]

    _correr(user, db, "¿y ahora?")
    assert len(sincronizaciones) == 1                      # no se llama a Strava en cada mensaje


def test_lo_recien_sincronizado_se_marca_como_hecho_en_el_plan(db, user, make_workout, monkeypatch):
    _conectar_strava(db, user)
    w = make_workout(user, date=AYER.date(), day_of_week=AYER.weekday(), type=WorkoutType.easy_run)
    _sync_que_trae_una_carrera(monkeypatch)
    _fake_ai(monkeypatch, [("Ok.", [_Text("Ok.")], "end_turn")])

    _correr(user, db, "¿cómo voy?")
    db.refresh(w)
    assert w.status == WorkoutStatus.completed


def test_si_strava_falla_el_chat_sigue_y_goggins_sabe_que_faltan_datos(db, user, monkeypatch):
    _conectar_strava(db, user)

    def falla(u, s, pages=2):
        raise httpx.ConnectTimeout("lento")

    monkeypatch.setattr(strava_service, "sync_activities", falla)
    llamadas = _fake_ai(monkeypatch, [("Ok.", [_Text("Ok.")], "end_turn")])
    eventos = _correr(user, db, "¿cómo voy?")

    assert eventos[-1]["phase"] == "done"
    assert '"strava_data": "NO actualizado' in llamadas[0]["system"]
    assert db.query(ChatMessage).filter_by(role="user").count() == 1


def test_sin_strava_goggins_sabe_que_no_ve_lo_entrenado_fuera(db, user, monkeypatch):
    llamadas = _fake_ai(monkeypatch, [("Ok.", [_Text("Ok.")], "end_turn")])
    _correr(user, db, "¿cómo voy?")
    assert '"strava_data": "sin Strava' in llamadas[0]["system"]
