"""Avisos de «datos completados, queda para proformar» (para Administracion)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import avisos
from ..auth import current_user
from ..database import get_db
from ..models import User

router = APIRouter()


@router.get("/avisos/proformar")
def avisos_proformar(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {"avisos": avisos.pendientes(db, user)}


@router.post("/avisos/proformar/{operated_id}/ocultar")
def avisos_ocultar(operated_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if avisos.puede_ver(user):
        avisos.ocultar(db, user, operated_id)
    return {"ok": True}
