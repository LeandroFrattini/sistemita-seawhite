"""Calendario (Administracion): feriados y dias no laborables, para los precios que cambian segun el dia."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Feriado

TIPOS = {"FERIADO": "Feriado", "NO_LABORABLE": "Día no laborable"}


def conjuntos(db: Session) -> tuple[set[str], set[str]]:
    """(feriados, dias no laborables) como conjuntos de fechas ISO, listos para tipo_dia()."""
    feriados: set[str] = set()
    no_laborables: set[str] = set()
    for f in db.scalars(select(Feriado)):
        (no_laborables if f.tipo == "NO_LABORABLE" else feriados).add(f.fecha)
    return feriados, no_laborables
