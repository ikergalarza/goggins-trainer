from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user, authorize_user
from app.models.user import User
from app.models.personal_record import PersonalRecord

router = APIRouter(prefix="/api/records", tags=["records"])


class RecordIn(BaseModel):
    category: str
    value_seconds: Optional[int] = None
    value_numeric: Optional[float] = None
    unit: Optional[str] = None
    date_achieved: date
    strava_activity_id: Optional[str] = None
    notes: Optional[str] = None


@router.get("/{user_id}")
def list_records(user_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    authorize_user(user_id, current)
    records = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == user_id)
        .order_by(PersonalRecord.date_achieved.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "category": r.category,
            "value_seconds": r.value_seconds,
            "value_numeric": r.value_numeric,
            "unit": r.unit,
            "date_achieved": r.date_achieved.isoformat() if r.date_achieved else None,
            "strava_activity_id": r.strava_activity_id,
            "notes": r.notes,
        }
        for r in records
    ]


@router.post("/{user_id}")
def create_record(user_id: int, body: RecordIn, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    authorize_user(user_id, current)
    record = PersonalRecord(
        user_id=user_id,
        **body.model_dump(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "message": "Marca guardada"}


@router.delete("/{user_id}/{record_id}")
def delete_record(user_id: int, record_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    authorize_user(user_id, current)
    record = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.id == record_id, PersonalRecord.user_id == user_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Marca no encontrada")
    db.delete(record)
    db.commit()
    return {"message": "Marca eliminada"}
