"""Un despliegue no puede quedarse colgado contra la base de datos en uso.

El despliegue del 24-11 falló: Railway espera /health 60 s. En cada arranque se
lanzaban `ALTER TABLE` (piden bloqueo EXCLUSIVO aunque la columna ya exista) y,
con una conversación abierta con Goggins manteniendo su transacción mientras la
IA generaba, el arranque esperaba hasta agotar el plazo. Además, mientras tanto,
el resto de consultas se encolaban detrás y la app parecía bloqueada.
"""
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import migrations
from app.db.database import Base
import app.models  # noqa: F401


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    return eng


def _statements(eng):
    seen: list[str] = []
    event.listen(eng, "before_cursor_execute", lambda conn, cur, stmt, *a: seen.append(stmt))
    return seen


def test_con_el_esquema_al_dia_el_arranque_no_ejecuta_ningun_alter():
    eng = _engine()
    seen = _statements(eng)
    migrations.ensure_schema(eng)
    assert not [s for s in seen if s.lstrip().upper().startswith(("ALTER", "CREATE", "DROP", "DO"))], seen


def test_detecta_solo_las_columnas_que_faltan():
    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE workouts (id INTEGER PRIMARY KEY, goal_id INTEGER)"))
    faltan = migrations._missing_columns(eng, [("workouts", "goal_id", "INTEGER"), ("workouts", "week_index", "INTEGER"),
                                               ("tabla_que_no_existe", "x", "INTEGER")])
    assert faltan == [("workouts", "week_index", "INTEGER")]


def test_anade_la_columna_que_falta_y_no_la_repite():
    eng = create_engine("sqlite://", poolclass=StaticPool)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE workouts (id INTEGER PRIMARY KEY)"))
    migrations._add_columns(eng, [("workouts", "week_index", "INTEGER")])
    assert migrations._missing_columns(eng, [("workouts", "week_index", "INTEGER")]) == []
    migrations._add_columns(eng, [("workouts", "week_index", "INTEGER")])      # idempotente


def test_el_healthcheck_responde_aunque_los_recalculos_de_datos_tarden(monkeypatch):
    from app import main

    eng = _engine()
    monkeypatch.setattr(main, "engine", eng)
    monkeypatch.setattr(main, "seed_master", lambda: None)
    soltar = threading.Event()
    arrancados = threading.Event()

    def _lento():
        arrancados.set()
        soltar.wait(10)

    monkeypatch.setattr(main, "backfill_wod_durations", _lento)
    monkeypatch.setattr(main, "backfill_race_days", lambda: None)
    inicio = time.monotonic()
    try:
        with TestClient(main.app) as c:          # si el arranque esperase a los recálculos, tardaría 10 s
            assert time.monotonic() - inicio < 5, "el arranque no puede esperar a los recálculos de datos"
            assert c.get("/health").json() == {"status": "ok"}
            assert arrancados.wait(5), "el recálculo debe lanzarse (en segundo plano)"
    finally:
        soltar.set()


# --- no se mantiene una transacción abierta mientras la IA genera ---------------

def test_el_chat_suelta_la_transaccion_antes_de_cada_llamada_a_la_ia(db, user, monkeypatch):
    from app.services import goggins_agent

    abiertas: list[bool] = []

    class _Block:
        def __init__(self, **kw): self.__dict__.update(kw)
        def model_dump(self): return dict(self.__dict__)

    class _Stream:
        def __init__(self, blocks, stop): self.b, self.s = blocks, stop
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def text_stream(self):
            yield from ()
        def get_final_message(self):
            class _M: pass
            m = _M(); m.content, m.stop_reason = self.b, self.s
            return m

    guion = [
        ([_Block(type="tool_use", id="t1", name="list_workouts", input={})], "tool_use"),   # lectura: abre transacción
        ([_Block(type="text", text="Tienes pocas.")], "end_turn"),
    ]

    class _C:
        class messages:
            @staticmethod
            def stream(**kw):
                abiertas.append(db.in_transaction())
                return _Stream(*guion[len(abiertas) - 1])

    monkeypatch.setattr(goggins_agent.ai_client, "get_client", lambda: _C())
    list(goggins_agent.chat_stream(user, db, "¿cómo voy?"))
    assert abiertas == [False, False]


def test_la_generacion_del_plan_tampoco_la_mantiene(db, user, monkeypatch):
    from app.models.goal import Goal, GoalType
    from app.services import plan_generator

    g = Goal(user_id=user.id, type=GoalType.fitness, description="Forma", is_active=True)
    db.add(g); db.commit()
    abiertas: list[bool] = []

    class _S:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def text_stream(self):
            yield '```json\n{"plan_name": "p", "weeks": 8, "weekly_plan": []}\n```'
        def get_final_message(self):
            class _M: stop_reason = "end_turn"
            return _M()

    class _C:
        class messages:
            @staticmethod
            def stream(**kw):
                abiertas.append(db.in_transaction())
                return _S()

    monkeypatch.setattr(plan_generator.ai_client, "get_client", lambda: _C())
    list(plan_generator.generate_plan_stream(user, g, db))
    assert abiertas == [False]
