"""Goggins: noción de la fecha y honestidad al editar el plan.

Síntomas reales: "se lía con el día que es" y "me dice que lo ha metido y no
está en el plan" (afirmaba el cambio sin llamar a ninguna herramienta).
"""
from datetime import date, datetime, timezone

import pytest

from app.models.chat_message import ChatMessage
from app.models.goal import Goal, GoalType
from app.models.workout import Workout, WorkoutStatus, WorkoutType
from app.services import goggins_agent

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


def test_una_pregunta_no_es_una_peticion_de_cambio():
    assert not goggins_agent.asks_plan_change("¿cómo voy de volumen esta semana?")


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
