"""Practicaje (pilotaje) de la proforma final: la misma formula y las mismas tablas que el proformador inicial.

UF = Eslora x Manga x Puntal / 800; se multiplica por el coeficiente segun el calado del movimiento (en PIES, tabla
ProformaPilotageTramo) y se suman el recorrido (km) y el service fijo. Entrada y salida se calculan por separado, cada
una con su calado. Si la manga supera 39,9 m va el tarifario de dos practicos: se duplica la tarifa de gobierno.
Los parametros (coeficientes, km, descuento, service) se editan en Proformador -> Formulas.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .proformador_calc import calcular_pilotage, coeficiente_pilotage_por_calado, get_param

MANGA_DOS_PRACTICOS = 39.9
PIES_POR_METRO = 3.28084


def _movimiento(db: Session, uf: float, calado_pies: float, dos_practicos: bool) -> dict | None:
    if not calado_pies or not uf:
        return None
    factor = coeficiente_pilotage_por_calado(db, calado_pies)
    if not factor:
        return None
    coef_maniobra = get_param(db, "pilotage_coef_maniobra", 14.0)
    coef_navegacion = get_param(db, "pilotage_coef_navegacion", 8.0)
    coef_km = get_param(db, "pilotage_coef_km", 12.0)
    km = get_param(db, "pilotage_km_recorrido", 53.0)
    descuento = get_param(db, "pilotage_descuento", 0.2)
    service = get_param(db, "pilotage_service_usd", 6600.0)
    maniobra = uf * coef_maniobra * factor
    navegacion = (uf * coef_navegacion + coef_km * km) * factor
    gobierno = (maniobra + navegacion) * (1 - descuento)
    if dos_practicos:
        gobierno *= 2
    total = calcular_pilotage(db, uf, calado_pies, dos_practicos=dos_practicos)  # la formula de siempre: es la que manda
    return {
        "calado_pies": calado_pies, "factor": factor, "maniobra": round(maniobra, 2), "navegacion": round(navegacion, 2),
        "descuento_pct": round(descuento * 100, 2), "gobierno": round(gobierno, 2), "service": round(service, 2),
        "total": round(total, 2),
    }


def calcular(db: Session, eslora: float, manga: float, puntal: float, calado_entrada: float, calado_salida: float,
             dos_manual: bool = False) -> dict:
    """Practicaje de entrada y de salida con el desglose, o lo que falta cargar.
    Lleva dos practicos si la manga supera 39,9 m o si se pidio a mano (dos_manual)."""
    uf = (eslora * manga * puntal / 800) if (eslora and manga and puntal) else 0.0
    dos = manga > MANGA_DOS_PRACTICOS or bool(dos_manual)
    faltan = [n for n, v in (("eslora", eslora), ("manga", manga), ("puntal", puntal)) if not v]
    return {
        "uf": round(uf, 4), "dos_practicos": dos, "faltan": faltan,
        "dos_por_manga": manga > MANGA_DOS_PRACTICOS,
        "remark": "BASIS OUR TARIFF WITH SERVICE PROVIDER" + ((" (TWO PILOTS -- BEAM OVER 40M)" if manga > MANGA_DOS_PRACTICOS else " (TWO PILOTS)") if dos else ""),
        "in": _movimiento(db, uf, calado_entrada, dos),
        "out": _movimiento(db, uf, calado_salida, dos),
    }
