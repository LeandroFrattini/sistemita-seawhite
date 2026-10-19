"""Paso 10 de la proforma final: migraciones y sanitary free pratique (con sus taxis).

Lo que se cobra sale de lo que se tildo en el voucher:
- Migraciones IN y OUT (IMMIGRATION TAX EXPENSES): USD 1.250 por movimiento; USD 1.875 si ese movimiento fue en boya (AT BUOY 11). Solo las migraciones van en boya.
- Taxi para el oficial de migraciones, IN y OUT: ARS por taxi.
- Free pratique (sanidad): ARS = (TRN - 1001) / 1000 x 6942,9 + 416.574 (mismos parametros que el proformador inicial).
- Taxi para sanidad: ARS por taxi.
Los importes se pueden escribir a mano (vacio = el de la tabla). Los valores fijos se editan en Administracion -> Formulas.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ProformaConceptoFijo
from .proformador_calc import get_param

# (clave, texto, moneda, puede ir en boya)
ITEMS = [
    ("mig_in", "Migraciones IN (immigration tax expenses)", "USD", True),
    ("mig_out", "Migraciones OUT (immigration tax expenses)", "USD", True),
    ("taxi_in", "Taxi para el oficial de migraciones IN", "ARS", False),
    ("taxi_out", "Taxi para el oficial de migraciones OUT", "ARS", False),
    ("free_pratique", "Free pratique (sanidad)", "ARS", False),
    ("taxi_sanidad", "Taxi para sanidad", "ARS", False),
]
CLAVES = [k for k, *_ in ITEMS]
MIGRACION_USD = 1250.0
TAXI_ARS = 222000.0   # el de la proforma mas reciente (SHI DAI 9); la de PORT ALBERNI cobro 160.000


def _movimientos(linea: str) -> tuple[bool, bool]:
    """(IN, OUT) de una linea del voucher: 'IN/OUT', 'IN' o 'OUT'."""
    t = linea.upper()
    if "IN/OUT" in t:
        return True, True
    return bool(re.search(r"\bIN\b", t)), bool(re.search(r"\bOUT\b", t))


def desde_voucher(servicios: list[str]) -> dict[str, dict]:
    """Que se uso segun las lineas del voucher: {clave: {on, boya}} (solo las que se usaron)."""
    out: dict[str, dict] = {}
    for linea in servicios or []:
        t = linea.upper().strip()
        boya = "AT BUOY" in t
        if t.startswith("IMMIGRATION"):
            i, o = _movimientos(t)
            if i:
                out["mig_in"] = {"on": True, "boya": boya}
            if o:
                out["mig_out"] = {"on": True, "boya": boya}
        elif t.startswith("TAXI HIRED FOR IMMIGRATION"):
            i, o = _movimientos(t)
            if i:
                out["taxi_in"] = {"on": True, "boya": False}
            if o:
                out["taxi_out"] = {"on": True, "boya": False}
        elif t.startswith("TAXI HIRED FOR SANITARY"):
            out["taxi_sanidad"] = {"on": True, "boya": False}
        elif "FREE PRATIQUE" in t:
            out["free_pratique"] = {"on": True, "boya": False}
    return out


def precio_auto(db: Session, clave: str, boya: bool, trn: float) -> float:
    """Importe de la tabla para ese concepto (en su moneda)."""
    if clave in ("mig_in", "mig_out"):
        if boya:
            return get_param(db, "immigration_boya_usd", 1875.0)
        fijo = db.scalar(select(ProformaConceptoFijo).where(ProformaConceptoFijo.clave == f"immigration_{clave[4:]}"))
        return fijo.valor_usd if fijo else MIGRACION_USD
    if clave in ("taxi_in", "taxi_out", "taxi_sanidad"):
        return get_param(db, "taxi_ars", TAXI_ARS)
    if clave == "free_pratique":
        if not trn:
            return 0.0
        coef = get_param(db, "libre_platica_coef", 6942.9)
        base = get_param(db, "libre_platica_base", 416574.0)
        resta = get_param(db, "libre_platica_resta_trn", 1001.0)
        return max(trn - resta, 0.0) / 1000 * coef + base
    return 0.0


def calcular(db: Session, *, trn: float, items: list[dict], dolar: float) -> dict:
    """Importe de cada concepto tildado, total en USD (migraciones), total en ARS (taxis y free pratique) y el total en dolares."""
    por_clave = {i["key"]: i for i in items}
    filas, usd, ars = [], 0.0, 0.0
    for clave, texto, moneda, puede_boya in ITEMS:
        it = por_clave.get(clave, {})
        boya = bool(it.get("boya")) and puede_boya
        auto = precio_auto(db, clave, boya, trn)
        manual = float(it.get("precio") or 0)
        precio = manual if manual > 0 else auto
        on = bool(it.get("on"))
        total = precio if on else 0.0
        if moneda == "USD":
            usd += total
        else:
            ars += total
        filas.append({"key": clave, "texto": texto, "moneda": moneda, "puede_boya": puede_boya, "on": on, "boya": boya, "precio_auto": round(auto, 2),
                      "precio": round(precio, 2), "manual": manual > 0, "total": round(total, 2)})
    return {"filas": filas, "total_usd": round(usd, 2), "total_ars": round(ars, 2),
            "ars_en_usd": round(ars / dolar, 2) if dolar else None, "total_usd_equiv": round(usd + ars / dolar, 2) if dolar else None,
            "faltan_trn": any(f["key"] == "free_pratique" and f["on"] for f in filas) and not trn}


def _num(v, tope: float) -> float:
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return round(n, 4) if 0 <= n <= tope else 0.0


def clean(raw) -> dict:
    """Estado del paso: siempre los seis conceptos, en orden (el estado puede venir de un Excel ajeno o viejo)."""
    raw = raw if isinstance(raw, dict) else {}
    por_clave = {}
    for it in (raw.get("items") if isinstance(raw.get("items"), list) else [])[:20]:
        if isinstance(it, dict) and it.get("key") in CLAVES:
            por_clave.setdefault(it["key"], it)
    items = []
    for clave, _t, _m, puede_boya in ITEMS:
        it = por_clave.get(clave, {})
        items.append({"key": clave, "on": bool(it.get("on")), "boya": bool(it.get("boya")) and puede_boya, "precio": _num(it.get("precio"), 1e12)})
    return {"armado": bool(raw.get("armado")), "items": items, "usd": _num(raw.get("usd"), 1e12), "ars": _num(raw.get("ars"), 1e13)}
