"""Uso de muelle, uso de fondeadero y vias navegables (channel toll) de la proforma final.

Dias: cada dia se divide en tres bloques, de 00 a 08 (0,33), de 08 a 16 (0,34) y de 16 a 24 (0,33). Si el barco
esta presente en cualquier parte de un bloque, se cobra el bloque entero. Ejemplo: del 15/10 00:30 al 16/10 13:30 son
0,33 + 0,34 + 0,33 (15/10) + 0,33 + 0,34 (16/10) = 1,67 dias.

- Uso de muelle (port dues) = USD 0,46 x TRN x dias de estadia en el muelle.
- Uso de fondeadero = USD 0,15 x TRN x dias de fondeo, con la misma logica de dias (el barco que toma bunker en boya).
- Vias navegables (channel toll) = USD 2,05 x coeficiente segun el TRN x toneladas cargadas. Si es SOLO bunker, las
  toneladas se reemplazan por el 20 % del TRN.
Las tarifas y la tabla de coeficientes son las del proformador inicial (se editan en Proformador -> Formulas).

Beneficio de fin de semana (solo uso de muelle): si el barco amarra un sabado, domingo o feriado DESPUES de las 21:00 y
no empieza a operar ese mismo dia, no se cobra el ultimo bloque (16 a 24) de ese dia ni los dias siguientes que sean
sabado, domingo o feriado, hasta el dia en que arranca la operacion. Ese dia (y todo dia habil, aunque el barco este
amarrado sin operar) se cobra entero. Si amarra antes de las 21:00 no hay beneficio. Los dias no laborables no cuentan.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .calendario import conjuntos
from .proforma_final import tipo_dia
from .proformador_calc import coeficiente_channel_toll, get_param

BLOQUES = [(0, 8, 0.33), (8, 16, 0.34), (16, 24, 0.33)]  # (desde hora, hasta hora, peso del bloque en el dia)
PCT_TRN_SOLO_BUNKER = 0.2
HORA_LIMITE_BENEFICIO = 21 * 60  # minutos del dia: amarrar DESPUES de las 21:00 (21:01 en adelante)
DIAS_SIN_COBRO = ("SABADO", "DOMINGO", "FERIADO")


def _dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def dias(entrada: str, salida: str, exentos: set | frozenset = frozenset()) -> dict:
    """Dias de estadia por bloques de 8 horas (los bloques son [desde, hasta): a las 16:00 en punto ya es el otro bloque).
    `exentos` son bloques (fecha ISO, hora desde) que no se cobran (beneficio de fin de semana); se listan igual, marcados."""
    a, b = _dt(entrada), _dt(salida)
    if not a or not b or b <= a:
        return {"total": 0.0, "perdonados": 0.0, "detalle": []}
    detalle = []
    total = perdonados = 0.0
    dia = a.date()
    while dia <= b.date():
        base = datetime.combine(dia, datetime.min.time())
        bloques = []
        for h1, h2, peso in BLOQUES:
            ini, fin = base + timedelta(hours=h1), base + timedelta(hours=h2)
            if a < fin and b > ini:
                bloques.append({"desde": f"{h1:02d}", "hasta": f"{h2:02d}", "peso": peso, "beneficio": (dia.isoformat(), h1) in exentos})
        if bloques:
            sub = round(sum(x["peso"] for x in bloques if not x["beneficio"]), 2)
            perd = round(sum(x["peso"] for x in bloques if x["beneficio"]), 2)
            detalle.append({"fecha": dia.isoformat(), "bloques": bloques, "subtotal": sub, "perdonado": perd})
            total += sub
            perdonados += perd
        dia += timedelta(days=1)
    return {"total": round(total, 2), "perdonados": round(perdonados, 2), "detalle": detalle}


def bloques_beneficio(db: Session, entrada: str, inicio: str) -> set:
    """Bloques (fecha ISO, hora desde) que NO se cobran por el beneficio de fin de semana; vacio si no corresponde."""
    a, op = _dt(entrada), _dt(inicio)
    if not a or not op or op.date() <= a.date():
        return set()
    feriados, _ = conjuntos(db)
    if tipo_dia(a.date(), feriados) not in DIAS_SIN_COBRO or a.hour * 60 + a.minute <= HORA_LIMITE_BENEFICIO:
        return set()
    libres = {(a.date().isoformat(), 16)}
    dia = a.date() + timedelta(days=1)
    while dia < op.date() and tipo_dia(dia, feriados) in DIAS_SIN_COBRO:
        libres |= {(dia.isoformat(), h1) for h1, _h2, _p in BLOQUES}
        dia += timedelta(days=1)
    return libres


def calcular(db: Session, *, trn: float, cantidad: float, entrada: str, salida: str, fondeo: bool,
             fondeo_entrada: str, fondeo_salida: str, solo_bunker: bool, factor_via: float = 1.0,
             inicio: str = "", aplicar_beneficio: bool = True) -> dict:
    wharfage = get_param(db, "wharfage_usd_trn_dia", 0.46)
    fondeadero = get_param(db, "fondeadero_usd_trn_dia", 0.15)
    tarifa_via = get_param(db, "channel_toll_usd_tn", 2.05)

    libres = bloques_beneficio(db, entrada, inicio)
    d_bruto = dias(entrada, salida, frozenset())
    d_muelle = dias(entrada, salida, libres if aplicar_beneficio else frozenset())
    # el beneficio se "detecta" solo si realmente toca algun bloque de la estadia (el barco puede haber zarpado antes)
    detectado = bool(libres) and dias(entrada, salida, libres)["perdonados"] > 0
    muelle = {"tarifa": wharfage, "dias": d_muelle["total"], "detalle": d_muelle["detalle"], "dias_brutos": d_bruto["total"],
              "beneficio": {"detectado": detectado, "aplicado": detectado and aplicar_beneficio, "dias": d_muelle["perdonados"]},
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
