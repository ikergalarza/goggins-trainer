"""Tests del feedback automático al completar (sin llamar al LLM real)."""
from datetime import date, timedelta

from app.services import workout_feedback
from app.models.workout import Workout, WorkoutType, WorkoutStatus
from app.models.chat_message import ChatMessage


def _completed(db, user, d, fb=None):
    w = Workout(user_id=user.id, date=d, type=WorkoutType.easy_run,
                status=WorkoutStatus.completed, planned_distance_km=10.0,
                planned_duration_min=50, actual_distance_km=10.2,
                actual_duration_min=52, ai_feedback=fb)
    db.add(w); db.commit(); db.refresh(w)
    return w


def test_genera_feedback_reciente_y_guarda_en_chat(db, user, monkeypatch):
    monkeypatch.setattr(workout_feedback.ai_client, "complete", lambda **k: "Buen trabajo. Stay hard.")
    w = _completed(db, user, date.today())
    n = workout_feedback.generate_for_completed(user, [w], db)
    assert n == 1
    db.refresh(w)
    assert w.ai_feedback == "Buen trabajo. Stay hard."
    msgs = db.query(ChatMessage).filter(ChatMessage.user_id == user.id, ChatMessage.role == "assistant").all()
    assert len(msgs) == 1 and "Stay hard" in msgs[0].content


def test_ignora_historico_antiguo(db, user, monkeypatch):
    called = {"n": 0}
    def fake(**k):
        called["n"] += 1
        return "x"
    monkeypatch.setattr(workout_feedback.ai_client, "complete", fake)
    old = _completed(db, user, date.today() - timedelta(days=30))  # histórico
    n = workout_feedback.generate_for_completed(user, [old], db)
    assert n == 0
    assert called["n"] == 0  # ni siquiera llama al LLM
    assert db.query(ChatMessage).count() == 0


def test_no_duplica_si_ya_tiene_feedback(db, user, monkeypatch):
    monkeypatch.setattr(workout_feedback.ai_client, "complete", lambda **k: "nuevo")
    w = _completed(db, user, date.today(), fb="ya tenía feedback")
    n = workout_feedback.generate_for_completed(user, [w], db)
    assert n == 0
    assert db.query(ChatMessage).count() == 0
