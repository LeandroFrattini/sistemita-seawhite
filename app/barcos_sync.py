"""Lo que se completa o corrige en la proforma final (paso 3) vuelve a «Nuestros barcos» y a los datos del buque.

Nuestros barcos -> proforma ya funcionaba (el paso 3 trae los horarios que cargo Operaciones). Esto es la vuelta: si quien proforma completa o
corrige el amarre, el comienzo, el final, el zarpe o la carga de un barco, queda en la fila de ese barco en «Operados» (y esa fila se pinta de verde
cuando quedan los datos completos), y el TRN, las medidas y la bandera quedan en el historial del buque por IMO, para la proxima escala.
Solo se escribe lo que se cargo (un campo vacio no borra nada) y solo en un barco real de la lista (no en el de prueba ni en uno escrito a mano).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import DocVessel, OperatedVessel

log = logging.getLogger("app.barcos_sync")

# (clave en el paso 3, columna de la fila de Operados)
HORARIOS = (("amarre", "amarre"), ("inicio", "inicio_operacion"), ("fin", "fin_operacion"), ("zarpe", "zarpe"))


def hermanas_creadas_juntas(db: Session, row: OperatedVessel) -> list[OperatedVessel]:
    """Las otras filas del mismo movimiento de barco (una por cliente, creadas juntas al sacarlo del line-up): mismo barco, mismo muelle, mismo momento."""
    return list(db.scalars(select(OperatedVessel).where(
        OperatedVessel.id != row.id,
        func.lower(OperatedVessel.vessel_name) == (row.vessel_name or "").strip().lower(),
        OperatedVessel.terminal_code == row.terminal_code,
        OperatedVessel.berth_label == row.berth_label,
        OperatedVessel.operated_at >= row.operated_at - timedelta(seconds=10),
        OperatedVessel.operated_at <= row.operated_at + timedelta(seconds=10),
    )))


def _num(v: float) -> str:
    """Numero para el historial del buque: sin separador de miles y con coma decimal (como lo lee el resto del sistema)."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}".replace(".", ",")


def sincronizar(db: Session, b: dict, usuario: str = "") -> dict:
    """`b` es el buque del estado de la proforma (ya limpio con proforma_final.clean_buque). Devuelve {"operado": [...], "buque": [...]} con lo que cambio.
    No hace commit si no cambio nada. Nunca debe romper la proforma: quien llama lo envuelve en try/except."""
    cambios: dict = {"operado": [], "buque": [], "completo": False}
    if "BARCO DE PRUEBA" in (b.get("nombre") or "").upper():
        return cambios
    # ---------------------------------------------------------------- la fila de Operados (y sus hermanas: los otros clientes del mismo movimiento)
    row = db.get(OperatedVessel, b["operated_id"]) if b.get("operated_id") else None
    if row is not None:
        filas = [row, *hermanas_creadas_juntas(db, row)]
        nuevos = {col: (b.get(k) or "").strip() for k, col in HORARIOS}
        nuevos["cantidad_operada"] = (b.get("cantidad") or "").strip()
        servicio = "HUSBANDRY" if b.get("servicio") == "HUSBANDRY" else "FULL"
        for col, val in nuevos.items():
            if val and val != (getattr(row, col) or ""):
                cambios["operado"].append(col)
                for f in filas:
                    setattr(f, col, val)
        if servicio != (row.servicio or "FULL"):
            cambios["operado"].append("servicio")
            for f in filas:
                f.servicio = servicio
        if servicio == "HUSBANDRY":  # sin operacion de carga: comienzo, final y carga no corresponden (como en «Completar datos»)
            for f in filas:
                f.inicio_operacion = f.fin_operacion = f.cantidad_operada = ""
        # la mercaderia y el shipper solo se completan si la fila no los tenia (no se pisa lo que vino del line-up)
        for col, k in (("grade", "carga"), ("shipper", "shipper")):
            val = (b.get(k) or "").strip()
            if val and not (getattr(row, col) or "").strip():
                cambios["operado"].append(col)
                for f in filas:
                    if not (getattr(f, col) or "").strip():
                        setattr(f, col, val)
    # ---------------------------------------------------------------- los datos del buque, por IMO (TRN, medidas, bandera)
    imo = (b.get("imo") or "").strip()
    if imo:
        dv = db.scalar(select(DocVessel).where(DocVessel.imo == imo))
        datos = {"trn": b.get("trn") or 0, "trb": b.get("trb") or 0, "eslora": b.get("eslora") or 0, "manga": b.get("manga") or 0, "puntal": b.get("puntal") or 0}
        a_guardar = {k: _num(v) for k, v in datos.items() if v and v > 0}
        if (b.get("bandera") or "").strip():
            a_guardar["flag"] = b["bandera"].strip()[:80]
        if a_guardar:
            if dv is None:
                dv = DocVessel(imo=imo, name=(b.get("nombre") or "").strip()[:120])
                db.add(dv)
            for campo, val in a_guardar.items():
                actual = (getattr(dv, campo, "") or "").strip()
                if campo == "flag":
                    distinto = val != actual
                else:
                    from .docgen.fechas import parse_number
                    distinto = (parse_number(actual) or 0) != (parse_number(val) or 0)
                if distinto:
                    setattr(dv, campo, val)
                    cambios["buque"].append(campo)
    if row is not None:
        cambios["completo"] = row.datos_completos(False)  # la fila de Operados ya tiene todo y se ve en verde
    if cambios["operado"] or cambios["buque"]:
        db.commit()
        log.info("barco %s: la proforma de %s actualizo Operados %s y datos del buque %s", b.get("nombre"), usuario, cambios["operado"], cambios["buque"])
    return cambios
