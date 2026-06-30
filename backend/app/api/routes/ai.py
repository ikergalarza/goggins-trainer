import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user, authorize_user
from app.models.user import User
from app.models.ai_insight import AiInsight
from app.services import fitness_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _serialize_insight(insight: AiInsight) -> dict:
    return {
        "id": insight.id,
        "kind": insight.kind,
        "summary": insight.summary,
        "data": insight.data,
        "model": insight.model,
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
    }


@router.get("/insights/{user_id}")
def get_latest_insight(user_id: int, kind: str = "fitness_state", current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Devuelve el último análisis cacheado para un tipo (por defecto fitness_state)."""
    authorize_user(user_id, current)
    insight = (
        db.query(AiInsight)
        .filter(AiInsight.user_id == user_id, AiInsight.kind == kind)
        .order_by(AiInsight.created_at.desc())
        .first()
    )
    if not insight:
        return None
    return _serialize_insight(insight)


@router.post("/analyze/{user_id}")
def analyze_fitness(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Genera un nuevo análisis de estado físico con Claude y lo cachea."""
    authorize_user(user_id, current)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        result = fitness_analysis.analyze(user, db)
    except RuntimeError as e:
        logger.error(f"[ai/analyze] {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"[ai/analyze] Error inesperado: {e}")
        raise HTTPException(status_code=500, detail=f"Error IA: {e}")

    insight = AiInsight(
        user_id=user_id,
        kind="fitness_state",
        summary=result["summary"],
        data=result["data"],
        model=result["model"],
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)

    return _serialize_insight(insight)
