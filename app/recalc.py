"""Recalculo en cascada de ETB / ETC dentro de una terminal.

Regla (definida con el usuario y verificada contra el Excel real):

* Los barcos se ordenan por `sort_order` dentro de cada terminal.
* ETA la carga el usuario siempre (puede ser fecha, "At roads" o vacio).
* Del PRIMER barco, ETB y ETC los carga el usuario.
* Para los siguientes:
    - se conserva la "duracion" de cada barco = ETC - ETB (dias de carga);
      si no se puede calcular se asume 1 dia.
    - nuevo ETB = max(ETC del barco anterior, ETA si es una fecha real)
    - nuevo ETC = nuevo ETB + duracion
* Si un barco tiene ETB = "Alongside" no se mueve: su ETC (que debe ser
  fecha) queda como ancla para el siguiente.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .dates import fmt_display, parse_date


@dataclass
class RecalcChange:
    vessel_call_id: int
    vessel_name: str
    field: str
    old: str
    new: str


def _duration_days(etb: str, etc: str) -> int:
    d1, d2 = parse_date(etb), parse_date(etc)
    if d1 and d2 and d2 >= d1:
        return (d2 - d1).days
    return 1


def recalc_terminal(calls: list) -> list[RecalcChange]:
    """`calls` es una lista de VesselCall ya ordenada. Muta etb/etc in place."""
    changes: list[RecalcChange] = []
    anchor: date | None = None  # ETC del ultimo barco resuelto

    for idx, call in enumerate(calls):
        etb_is_alongside = call.etb.strip().lower() == "alongside"

        if idx == 0 or anchor is None:
            # Primer barco (o todavia no hay ancla): se respeta lo cargado.
            etc_d = parse_date(call.etc)
            if etc_d:
                anchor = etc_d
            continue

        if etb_is_alongside:
            etc_d = parse_date(call.etc)
            if etc_d:
                anchor = etc_d
            continue

        duration = _duration_days(call.etb, call.etc)
        eta_d = parse_date(call.eta)

        new_etb = anchor
        if eta_d and eta_d > new_etb:
            new_etb = eta_d
        new_etc = new_etb + timedelta(days=duration)

        new_etb_s, new_etc_s = fmt_display(new_etb), fmt_display(new_etc)
        if new_etb_s != call.etb:
            changes.append(RecalcChange(call.id, call.vessel_name, "ETB", call.etb, new_etb_s))
            call.etb = new_etb_s
        if new_etc_s != call.etc:
            changes.append(RecalcChange(call.id, call.vessel_name, "ETC", call.etc, new_etc_s))
            call.etc = new_etc_s

        anchor = new_etc

    return changes


def recalc_lineup(calls_by_terminal: dict[int, list]) -> list[RecalcChange]:
    changes: list[RecalcChange] = []
    for calls in calls_by_terminal.values():
        changes.extend(recalc_terminal(calls))
    return changes
