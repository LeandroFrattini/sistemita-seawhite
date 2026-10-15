"""Uso de muelle, uso de fondeadero y vias navegables (channel toll) de la proforma final.

Dias: cada dia se divide en tres bloques, de 00 a 08 (0,33), de 08 a 16 (0,34) y de 16 a 24 (0,33). Si el barco
esta presente en cualquier parte de un bloque, se cobra el bloque entero. Ejemplo: del 15/10 00:30 al 16/10 13:30 son
0,33 + 0,34 + 0,33 (15/10) + 0,33 + 0,34 (16/10) = 1,67 dias.

- Uso de muelle (port dues) = USD 0,46 x TRN x dias de estadia en el muelle.
- Uso de fondeadero = USD 0,15 x TRN x dias de fondeo, con la misma logica de dias (el barco que toma bunker en boya).
- Vias navegables (channel toll) = USD 2,05 x coeficiente segun el TRN x toneladas cargadas. Si es SOLO bunker, las
  toneladas se reemplazan por el 20 % del TRN.
Las tarifas y la tabla de coeficientes son las del proformador inicial (se editan en Proformador -> Formulas).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .proformador_calc import coeficiente_channel_toll, get_param

BLOQUES = [(0, 8, 0.33), (8, 16, 0.34), (16, 24, 0.33)]  # (desde hora, hasta hora, peso del bloque en el dia)
PCT_TRN_SOLO_BUNKER = 0.2


def _dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def dias(entrada: str, salida: str) -> dict:
    """Dias de estadia por bloques de 8 horas (los bloques son [desde, hasta): a las 16:00 en punto ya es el otro bloque)."""
    a, b = _dt(entrada), _dt(salida)
    if not a or not b or b <= a:
        return {"total": 0.0, "detalle": []}
    detalle = []
    total = 0.0
    dia = a.date()
    while dia <= b.date():
        base = datetime.combine(dia, datetime.min.time())
        bloques = []
        for h1, h2, peso in BLOQUES:
            ini, fin = base + timedelta(hours=h1), base + timedelta(hours=h2)
            if a < fin and b > ini:
                bloques.append({"desde": f"{h1:02d}", "hasta": f"{h2:02d}", "peso": peso})
        if bloques:
            sub = round(sum(x["peso"] for x in bloques), 2)
            detalle.append({"fecha": dia.isoformat(), "bloques": bloques, "subtotal": sub})
            total += sub
        dia += timedelta(days=1)
    return {"total": round(total, 2), "detalle": detalle}


def calcular(db: Session, *, trn: float, cantidad: float, entrada: str, salida: str, fondeo: bool,
             fondeo_entrada: str, fondeo_salida: str, solo_bunker: bool, factor_via: float = 1.0) -> dict:
    wharfage = get_param(db, "wharfage_usd_trn_dia", 0.46)
    fondeadero = get_param(db, "fondeadero_usd_trn_dia", 0.15)
    tarifa_via = get_param(db, "channel_toll_usd_tn", 2.05)

    d_muelle = dias(entrada, salida)
    muelle = {"tarifa": wharfage, "dias": d_muelle["total"], "detalle": d_muelle["detalle"],
              "total": round(wharfage * trn * d_muelle["total"], 2) if trn and d_muelle["total"] else None}

    fond = None
    if fondeo:
        d_f = dias(fondeo_entrada, fondeo_salida)
        fond = {"tarifa": fondeadero, "dias": d_f["total"], "detalle": d_f["detalle"],
                "total": round(fondeadero * trn * d_f["total"], 2) if trn and d_f["total"] else None}

    coef = coeficiente_channel_toll(db, trn) if trn else 0
    base = (PCT_TRN_SOLO_BUNKER * trn) if solo_bunker else cantidad
    vias = {"tarifa": tarifa_via, "coef": coef, "base": round(base, 4), "solo_bunker": solo_bunker, "factor": factor_via,
            "total": round(tarifa_via * coef * base * factor_via, 2) if trn and base else None}
    return {"muelle": muelle, "fondeo": fond, "vias": vias}
