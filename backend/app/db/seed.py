"""Seed del usuario maestro al arrancar."""
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.user import User
from app.services import auth

logger = logging.getLogger(__name__)


def seed_master() -> None:
    """Garantiza que existe el usuario maestro.

    Prioriza convertir en maestro al usuario que ya tiene los datos (id=1 o el
    que tenga el email del maestro). Solo fija la contraseña si no tiene una
    (para no pisar un cambio posterior de contraseña en cada reinicio).
    """
    email = settings.MASTER_EMAIL.strip().lower()
    db: Session = SessionLocal()
    try:
        master = (
            db.query(User).filter(func.lower(User.email) == email).first()
            or db.query(User).filter(User.id == 1).first()
        )
        if master is None:
            master = User(name="Iker", email=email)
            db.add(master)

        # Email: solo lo cambiamos si nadie más lo tiene ya.
        if (master.email or "").strip().lower() != email:
            clash = db.query(User).filter(func.lower(User.email) == email).first()
            if clash is None:
                master.email = email

        master.is_master = True
        # La contraseña solo se fija si se ha aportado por entorno y el maestro
        # aún no tiene una (no se pisa un cambio posterior, ni se hardcodea).
        if not master.hashed_password and settings.MASTER_PASSWORD:
            master.hashed_password = auth.hash_password(settings.MASTER_PASSWORD)

        db.commit()
        has_pw = bool(master.hashed_password)
        logger.info(
            f"[seed] Maestro asegurado: id={master.id} email={master.email} "
            f"con_contraseña={has_pw}"
        )
        if not has_pw:
            logger.warning(
                "[seed] El maestro NO tiene contraseña. Define MASTER_PASSWORD "
                "en el entorno y reinicia para poder iniciar sesión."
            )
    except Exception as e:
        logger.warning(f"[seed] No se pudo sembrar el maestro: {e}")
        db.rollback()
    finally:
        db.close()
