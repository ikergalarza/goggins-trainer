"""Goggins debe saber qué día es: fecha española, día de la semana y reglas."""
from datetime import date, datetime

from app.services import clock
from app.services.goggins_agent import SYSTEM_PROMPT, _build_athlete_context
from app.models.workout import Workout, WorkoutType, WorkoutStatus


def test_weekday_es():
    assert clock.weekday_es(date(2026, 10, 4)) == "domingo"
    assert clock.weekday_es(date(2026, 10, 5)) == "lunes"


def test_today_madrid_es_fecha_de_madrid():
    # Coherente con la conversión directa (si esto falla, la tz está rota).
    assert clock.today_madrid() == datetime.now(clock.TZ).date()


def test_contexto_lleva_hoy_inconfundible(db, user):
    hoy = clock.today_madrid()
    w = Workout(user_id=user.id, date=hoy, type=WorkoutType.easy_run, status=WorkoutStatus.planned)
    db.add(w); db.commit()

    ctx = _build_athlete_context(user, db)

    assert ctx["today"]["date"] == hoy.isoformat()
    assert ctx["today"]["weekday"] == clock.weekday_es(hoy)
    assert "tomorrow" in ctx["today"]
    mine = next(x for x in ctx["upcoming_workouts"] if x["id"] == w.id)
    assert mine["is_today"] is True
    assert mine["weekday"] == clock.weekday_es(hoy)


def test_prompt_tiene_reglas_de_fechas():
    assert "FECHAS (CRÍTICO" in SYSTEM_PROMPT
    assert "NUNCA deduzcas qué día es" in SYSTEM_PROMPT
    assert "is_today" in SYSTEM_PROMPT
