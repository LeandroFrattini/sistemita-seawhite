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

from sqlalchemy.orm import Session

from .calendario import conjuntos
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
    """0, 50 o 100 segun el dia y la hora del servicio. El dia no laborable no cuenta para LDS (se toma como habil)."""
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


def costo_servicio(servicio: str, momento: datetime, eslora: float, feriados: set[str], lanchas: int = 0) -> dict:
    """Costo de un amarre o un desamarre: servicio + lancha(s), con el recargo que corresponda.
    `lanchas` en 0 = automatico (una, o dos si la eslora supera 150 m); si no, la cantidad indicada."""
    if servicio not in ("amarre", "desamarre"):
        raise ValueError("servicio debe ser 'amarre' o 'desamarre'")
    pct = recargo_pct(momento, feriados)
    col = _columna(pct)
    lanchas = lanchas if lanchas > 0 else (2 if eslora > ESLORA_DOS_LANCHAS else 1)
    base = TARIFA[servicio][col]
    lancha_unit = TARIFA["lancha"][col]
    return {
        "servicio": servicio, "momento": momento.isoformat(timespec="minutes"), "recargo_pct": pct,
        "tipo_dia": tipo_dia(momento.date(), feriados),
        "base_usd": base, "lancha_unit_usd": lancha_unit, "lanchas": lanchas,
        "total_usd": base + lancha_unit * lanchas,
    }


def _dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def escala_costo(dias: int) -> dict:
    """Escala (pasarela de tierra): colocacion + retiro + alquiler por dia. No lleva recargo horario en el tarifario."""
    alquiler = ESCALA["alquiler_diario"] * dias
    return {"colocacion": ESCALA["colocacion"], "retiro": ESCALA["retiro"], "alquiler_diario": ESCALA["alquiler_diario"],
            "dias": dias, "alquiler": alquiler, "total_usd": ESCALA["colocacion"] + ESCALA["retiro"] + alquiler}


def calcular(db: Session, *, eslora: float, amarre: str, desamarre: str, lanchas_amarre: int = 0, lanchas_desamarre: int = 0,
             escala: bool = False, escala_dias: int = 0) -> dict:
    """Amarre, desamarre y (si se pide) escala. Sin fecha valida el servicio queda en None (no se inventa un importe).
    Dias de la escala: los indicados o, si no, los dias de calendario entre el amarre y el desamarre (ambos inclusive)."""
    feriados, _ = conjuntos(db)
    out = {"lanchas_auto": 2 if eslora > ESLORA_DOS_LANCHAS else 1, "amarre": None, "desamarre": None, "escala": None}
    for clave, raw, lanchas in (("amarre", amarre, lanchas_amarre), ("desamarre", desamarre, lanchas_desamarre)):
        m = _dt(raw)
        if m:
            out[clave] = costo_servicio(clave, m, eslora, feriados, lanchas)
    if escala:
        a, d = _dt(amarre), _dt(desamarre)
        auto = (d.date() - a.date()).days + 1 if a and d and d >= a else 0
        dias = escala_dias if escala_dias > 0 else auto
        out["escala"] = {**escala_costo(dias), "dias_auto": auto} if dias else {"dias_auto": auto, "total_usd": None}
    return out
