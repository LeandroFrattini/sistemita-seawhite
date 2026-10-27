"""Tabla de mareas tentativa del Line-up (hoy y los dos dias siguientes)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import mareas
from ..auth import current_user
from ..database import get_db
from ..models import User

router = APIRouter()


@router.get("/mareas/proximos")
def mareas_proximos(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return mareas.proximos(db, 3)
