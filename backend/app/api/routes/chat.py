"""Rutas del chat con el agente Goggins."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user, authorize_user
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.services import goggins_agent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatIn(BaseModel):
    message: str


@router.get("/{user_id}")
def get_history(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve el historial completo del chat ordenado cronológicamente."""
    authorize_user(user_id, current)
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/{user_id}")
def clear_history(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Borra todo el historial del chat del usuario."""
    authorize_user(user_id, current)
    deleted = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).delete()
    db.commit()
    return {"deleted": deleted}


@router.post("/{user_id}/send_stream")
def send_stream(user_id: int, body: ChatIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stream SSE con la respuesta de Goggins en tiempo real."""
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    def event_generator():
        try:
            for event in goggins_agent.chat_stream(user, db, body.message.strip()):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.exception(f"[chat] stream error: {e}")
            yield f"data: {json.dumps({'phase': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
