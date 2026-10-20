"""Lo que cobro cada sereno en cada barco: se anota al bajar el Excel de serenos de un barco y sirve para armar el resumen de cada sereno (barcos, jornales, bruto y neto)."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Sereno, SerenoPago


def registrar(db: Session, *, barco_clave: str, buque: str, recibos: list[dict], usuario: str) -> int:
    """Anota lo cobrado por cada sereno en este barco (por mes). Reemplaza lo que ya habia de ese barco. Devuelve cuantos renglones quedaron."""
    ids = {s.nombre: s.id for s in db.scalars(select(Sereno))}
    for r in db.scalars(select(SerenoPago).where(SerenoPago.barco_clave == barco_clave)):
        db.delete(r)
    agg: dict[tuple[str, str], dict] = {}
    for r in recibos:
        k = (r["nombre"], r["mes"].strftime("%Y-%m"))
        a = agg.setdefault(k, {"jornales": 0, "bruto": 0.0, "descuentos": 0.0, "viaticos": 0.0, "neto": 0.0, "fechas": set()})
        a["jornales"] += r["jornales"]
        a["bruto"] += r["bruto"]
        a["descuentos"] += r["ded"]
        a["viaticos"] += r["viat"]
        a["neto"] += r["neto"]
        a["fechas"] |= r["fechas"]
    for (nombre, mes), a in agg.items():
        db.add(SerenoPago(barco_clave=barco_clave, buque=buque[:120], sereno_id=ids.get(nombre), nombre=nombre, mes=mes, desde=min(a["fechas"]), hasta=max(a["fechas"]),
                          jornales=a["jornales"], bruto=round(a["bruto"], 2), descuentos=round(a["descuentos"], 2), viaticos=round(a["viaticos"], 2),
                          neto=round(a["neto"], 2), usuario=usuario[:60]))
    db.commit()
    return len(agg)


def _filtro(sereno: Sereno):
    return or_(SerenoPago.sereno_id == sereno.id, (SerenoPago.sereno_id.is_(None)) & (SerenoPago.nombre == sereno.nombre))


def meses_con_pagos(db: Session, sereno: Sereno) -> list[str]:
    return sorted({m for (m,) in db.execute(select(SerenoPago.mes).where(_filtro(sereno)))}, reverse=True)


def resumen(db: Session, sereno: Sereno, mes: str = "") -> dict:
    """Barcos que atendio el sereno (en el mes, o en todos) con jornales, bruto, descuentos, viaticos y neto, y los totales."""
    q = select(SerenoPago).where(_filtro(sereno))
    if mes:
        q = q.where(SerenoPago.mes == mes)
    filas = list(db.scalars(q.order_by(SerenoPago.mes, SerenoPago.desde, SerenoPago.buque)))
    tot = {k: round(sum(getattr(f, k) for f in filas), 2) for k in ("bruto", "descuentos", "viaticos", "neto")}
    tot["jornales"] = sum(f.jornales for f in filas)
    tot["barcos"] = len({f.barco_clave for f in filas})
    return {"filas": filas, "totales": tot, "mes": mes}


def quitar(db: Session, sereno: Sereno, barco_clave: str) -> None:
    for r in db.scalars(select(SerenoPago).where(_filtro(sereno), SerenoPago.barco_clave == barco_clave)):
        db.delete(r)
    db.commit()
