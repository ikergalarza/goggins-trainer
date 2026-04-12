from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class AiInsight(Base):
    """Resultado cacheado de un análisis de Claude.

    `kind` separa tipos: "fitness_state", "plan", "feedback_workout", etc.
    """
    __tablename__ = "ai_insights"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    kind = Column(String, nullable=False, index=True)
    summary = Column(Text, nullable=True)     # texto resumen para mostrar
    data = Column(JSON, nullable=True)        # JSON estructurado con métricas

    model = Column(String, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
