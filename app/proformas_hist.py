"""Historial de proformas finales: guardar (crear o actualizar), listar y reabrir.

Se guarda el estado completo (el mismo que lleva el Excel en la hoja _estado), asi una proforma se puede abrir y modificar sin rehacerla.
Si dos personas tocan la misma, quien guarda segundo recibe un aviso (Conflicto) en vez de pisar en silencio. El barco de prueba nunca se guarda.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import chequeo, proforma_final as pf
from .models import ProformaFinalReg

log = logging.getLogger("proformas_hist")
MAX_LISTA = 500


class Conflicto(Exception):
    """Alguien guardo esa proforma despues de que se abrio (o ya existe otra del mismo barco)."""

    def __init__(self, mensaje: str, duplicada: int | None = None):
        super().__init__(mensaje)
        self.mensaje, self.duplicada = mensaje, duplicada


def marca(dt: datetime) -> str:
    """Identifica la version exacta de un registro (para detectar que alguien lo cambio mientras estaba abierto)."""
    return dt.isoformat()


def _quien_cuando(usuario: str, dt: datetime) -> str:
    from .templating import localdt

    return f"{usuario or '—'} el {localdt(dt)}"


def _totales(db: Session, s: dict) -> tuple[float | None, float | None]:
    try:
        ch = chequeo.armar(db, s)
        return ch["total_usd"], ch["total_ars"]
    except Exception:  # sin dolar o datos incompletos: se guarda igual, sin total
        log.exception("proformas: no se pudo calcular el total")
        return None, None


def guardar(db: Session, state_raw: dict, usuario: str, proforma_id: int | None = None, base: str = "", forzar: bool = False) -> ProformaFinalReg | None:
    """Crea o actualiza. Devuelve el registro, o None si es el barco de prueba (no se guarda). Levanta Conflicto / ValueError."""
    s = pf.clean_state(state_raw)
    if pf.es_barco_de_prueba(s["buque"]):
        return None
    if not s["buque"]["nombre"]:
        raise ValueError("Elegí el barco (paso 1) antes de guardar.")
    usd, ars = _totales(db, s)
    ahora = datetime.utcnow()
    reg = db.get(ProformaFinalReg, proforma_id) if proforma_id else None
    if proforma_id and reg is None:
        raise ValueError("Esa proforma ya no está en el historial. Guardala como una nueva (recargá la página).")
    clave, op = pf.barco_clave(s["buque"]), s["buque"].get("operated_id")
    if reg is None:
        if op and not forzar:
            otra = db.scalar(select(ProformaFinalReg).where(ProformaFinalReg.operated_id == op).order_by(ProformaFinalReg.id.desc()))
            if otra is not None:
                raise Conflicto(f"Ya hay una proforma de {otra.buque}: la hizo {_quien_cuando(otra.creado_por, otra.creado_en)}"
                                f" (última modificación: {_quien_cuando(otra.modificado_por, otra.modificado_en)}).", otra.id)
        reg = ProformaFinalReg(creado_por=usuario, creado_en=ahora)
        db.add(reg)
    elif not forzar and base and marca(reg.modificado_en) != base:
        from .templating import localdt

        raise Conflicto(f"{reg.modificado_por or 'Otra persona'} guardó cambios en esta proforma el {localdt(reg.modificado_en)}, mientras la tenías abierta.", reg.id)
    reg.buque, reg.agencia = s["buque"]["nombre"], s["agencia"]["nombre"]
    reg.barco_clave, reg.operated_id = clave, op
    reg.servicio = s["buque"].get("servicio") or "FULL"
    reg.total_usd, reg.total_ars = usd, ars
    reg.estado = json.dumps(s, ensure_ascii=False, separators=(",", ":"))
    reg.modificado_por, reg.modificado_en = usuario, ahora
    reg.ediciones = (reg.ediciones or 0) + (0 if reg.id is None else 1)
    db.commit()
    db.refresh(reg)
    return reg


def listar(db: Session) -> list[ProformaFinalReg]:
    return list(db.scalars(select(ProformaFinalReg).order_by(ProformaFinalReg.modificado_en.desc(), ProformaFinalReg.id.desc()).limit(MAX_LISTA)))


def estado_de(reg: ProformaFinalReg) -> dict:
    return pf.clean_state(json.loads(reg.estado or "{}"))


def meta(reg: ProformaFinalReg) -> dict:
    """Lo que la pantalla necesita saber de la proforma abierta."""
    return {"id": reg.id, "buque": reg.buque, "creada": _quien_cuando(reg.creado_por, reg.creado_en), "modificada": _quien_cuando(reg.modificado_por, reg.modificado_en),
            "mod": marca(reg.modificado_en), "ediciones": reg.ediciones or 0}
