"""Social: ranking del grupo y comentario vacilón de Goggins.

Cualquier usuario autenticado ve el ranking (solo agregados por disciplina y
nombre de pila). El roast se cachea por huella del ranking; regenerarlo a
mano tiene un límite por usuario para que nadie dispare el gasto de IA.
"""
import logging
import time
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services import social

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/social", tags=["social"])

# Límite simple en memoria: N regeneraciones por usuario por ventana. Suficiente
# para un grupo pequeño en un único proceso (Railway); si hubiera varias
# réplicas sería por réplica, que sigue acotando el gasto.
ROAST_LIMIT = 3
ROAST_WINDOW_S = 600
_roast_hits: dict[int, deque] = {}


def _check_roast_limit(user_id: int) -> None:
    now = time.monotonic()
    q = _roast_hits.setdefault(user_id, deque())
    while q and now - q[0] > ROAST_WINDOW_S:
        q.popleft()
    if len(q) >= ROAST_LIMIT:
        raise HTTPException(status_code=429, detail="Goggins ya ha hablado bastante. Vuelve en unos minutos.")
    q.append(now)


@router.get("/leaderboard")
def get_leaderboard(
    weeks: int = Query(default=1, ge=1, le=4),
    roast: bool = Query(default=True),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    board = social.leaderboard(db, weeks=weeks, me_id=current.id)
    out = dict(board)
    out["roast"] = social.get_roast(db, board) if roast else None
    return out


@router.post("/roast")
def regenerate_roast(
    weeks: int = Query(default=1, ge=1, le=4),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fuerza un comentario nuevo de Goggins (ignora la caché). Limitado por usuario."""
    _check_roast_limit(current.id)
    board = social.leaderboard(db, weeks=weeks, me_id=current.id)
    r = social.get_roast(db, board, force=True)
    if r is None:
        raise HTTPException(status_code=503, detail="Goggins no está disponible ahora mismo. Prueba en un rato.")
    return {"roast": r}
