from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base


class ChatMessage(Base):
    """Mensajes del chat con el agente Goggins."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)

    # Para tool-use de Claude (opcional)
    tool_calls = Column(Text, nullable=True)  # JSON serializado

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
