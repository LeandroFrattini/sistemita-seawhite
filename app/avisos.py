"""Avisos para Administracion: cuando alguien completa los datos de un barco («Completar datos»), a las personas de Administracion
les aparece una notificacion verde arriba: «PEPITO completó los datos del barco MV X: queda para proformar».

El aviso sigue mientras la proforma de ese barco no este guardada en el historial; cada persona puede ocultar los suyos. Solo se avisa de los
datos completados desde que se prendio esta funcion (los barcos viejos no aparecen todos juntos), y cada uno ve lo que completaron los demas
(no lo que completo ella misma)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, AvisoOculto, OperatedVessel, ProformaFinalReg, User

DESDE_KEY = "avisos_proformar_desde"
MAX_AVISOS = 30


def puede_ver(user: User) -> bool:
    return bool(user.is_admin or user.is_administracion)


def _desde(db: Session) -> datetime:
    """Desde cuando se avisa: se fija la primera vez que se pregunta (los datos completados antes no generan aviso)."""
    row = db.get(AppSetting, DESDE_KEY)
    if row is None:
        row = AppSetting(key=DESDE_KEY, value=datetime.utcnow().isoformat())
        db.add(row)
        db.commit()
    try:
        return datetime.fromisoformat(row.value)
    except ValueError:
        return datetime.utcnow()


def pendientes(db: Session, user: User) -> list[dict]:
    """Los barcos con datos completados que todavia no tienen proforma y que esta persona no ocultó (los mas nuevos primero)."""
    if not puede_ver(user):
        return []
    desde = _desde(db)
    proformados = {x for x in db.scalars(select(ProformaFinalReg.operated_id).where(ProformaFinalReg.operated_id.is_not(None)))}
    ocultos = set(db.scalars(select(AvisoOculto.operated_id).where(AvisoOculto.user_id == user.id)))
    nombres = {u.username: (u.full_name or u.username) for u in db.scalars(select(User))}
    out = []
    for o in db.scalars(select(OperatedVessel).where(OperatedVessel.datos_completados_at.is_not(None), OperatedVessel.datos_completados_at >= desde)
                        .order_by(OperatedVessel.datos_completados_at.desc()).limit(MAX_AVISOS * 3)):
        if o.id in proformados or o.id in ocultos or o.completado_por == user.username:
            continue
        out.append({"id": o.id, "quien": nombres.get(o.completado_por, o.completado_por or "Alguien"), "barco": (o.vessel_name or "").strip().upper(),
                    "agencia": o.principal or "", "servicio": o.servicio or "FULL", "url": f"/administracion/proforma-final?barco={o.id}"})
        if len(out) >= MAX_AVISOS:
            break
    return out


def ocultar(db: Session, user: User, operated_id: int) -> None:
    if db.scalar(select(AvisoOculto.id).where(AvisoOculto.user_id == user.id, AvisoOculto.operated_id == operated_id)) is None:
        db.add(AvisoOculto(user_id=user.id, operated_id=operated_id))
        db.commit()
