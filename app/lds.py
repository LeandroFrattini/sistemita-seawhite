"""Lanchas del Sur (LDS): amarre y desamarre. Tarifario 2026, buques extranjeros (USD).

Reglas confirmadas por el usuario:
- Al costo de AMARRE se le suma SIEMPRE la lancha (y dos lanchas si la eslora supera 150 m); igual para el DESAMARRE.
- Recargo segun dia y hora (los feriados salen del Calendario):
    dia habil 07:00-19:00: sin recargo   | dia habil 19:00-07:00: 50 %
    sabado 07:00-13:00: sin recargo      | sabado 13:00-24:00: 100 %
    sabado 00:00-07:00: se toma como dia habil de 19 a 07 (50 %)
    domingo y feriado, todo el dia: 100 %
  Domingo 23:00 = 100 %; lunes 03:00 = noche de dia habil (50 %), salvo que el lunes sea feriado.
- ESCALA (colocacion, retiro, alquiler diario) solo si en el voucher se selecciona SHORE GANGWAY.
- Buques argentinos (tarifa DCI 22): por ahora no se cargan.
"""
from __future__ import annotations

from datetime import datetime

from .proforma_final import tipo_dia

# (habil, extra 50 %, extra 100 %)
TARIFA = {
    "amarre": (1900.0, 2850.0, 3800.0),
    "lancha": (1070.0, 1610.0, 2140.0),
    "desamarre": (1900.0, 2850.0, 3800.0),
}
ESCALA = {"colocacion": 490.0, "retiro": 490.0, "alquiler_diario": 280.0}
ESLORA_DOS_LANCHAS = 150.0  # "eslora de mas de 150 lleva dos lanchas"


def recargo_pct(momento: datetime, feriados: set[str]) -> int:
    """0, 50 o 100 segun el dia y la hora del servicio."""
    tipo = tipo_dia(momento.date(), feriados)
    h = momento.hour + momento.minute / 60
    if tipo in ("DOMINGO", "FERIADO"):
        return 100
    if tipo == "SABADO":
        if h < 7:
            return 50
        return 0 if h < 13 else 100
    return 0 if 7 <= h < 19 else 50


def _columna(pct: int) -> int:
    return {0: 0, 50: 1, 100: 2}[pct]


def costo_servicio(servicio: str, momento: datetime, eslora: float, feriados: set[str]) -> dict:
    """Costo de un amarre o un desamarre: servicio + lancha(s), con el recargo que corresponda."""
    if servicio not in ("amarre", "desamarre"):
        raise ValueError("servicio debe ser 'amarre' o 'desamarre'")
    pct = recargo_pct(momento, feriados)
    col = _columna(pct)
    lanchas = 2 if eslora > ESLORA_DOS_LANCHAS else 1
    base = TARIFA[servicio][col]
    lancha_unit = TARIFA["lancha"][col]
    return {
        "servicio": servicio, "momento": momento.isoformat(timespec="minutes"), "recargo_pct": pct,
        "tipo_dia": tipo_dia(momento.date(), feriados),
        "base_usd": base, "lancha_unit_usd": lancha_unit, "lanchas": lanchas,
        "total_usd": base + lancha_unit * lanchas,
    }
