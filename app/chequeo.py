"""Paso 11 de la proforma final: chequeo general. Arma la proforma consolidada (renglones numerados, en pesos y en dolares) con todo lo cargado
en los pasos anteriores, mas lo que solo se ve aca: SENASA, Maritime Center y Miscellaneous (siempre el mismo monto), los renglones libres y LAW NR 25413.

- El FEE sale de lo tildado en el paso 2 (por agencia) y no entra en la base de LAW.
- LAW NR 25413 = 1,2 % de la suma de los renglones que se facturan, SIN el fee (y sin lo que va FOR YOUR ACCOUNT). El importe se puede escribir a mano.
- Lo que va FOR YOUR ACCOUNT (por cuenta del armador) no se factura: se lista aparte, al pie.
- Cada renglon lleva el numero de paso donde se corrige; todo el resto de los importes ya se pudo modificar en su paso.
El dolar es el unico del paso 1: los renglones en pesos se pasan a dolares dividiendo, y los de dolares a pesos multiplicando.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import migraciones
from .proformador_calc import get_param

# (clave, texto de la proforma, parametro del monto, valor por defecto en USD)
FIJOS = [
    ("senasa", "COMPULSORY SENASA INSPECTION EXPENSES", "senasa_usd", 45.0),
    ("maritime", "MARITIME CENTER EXPENSES", "maritime_center_usd", 80.0),
    ("misc", "MISCELLANEOUS EXPENSES", "miscelaneos_usd", 250.0),
]
CLAVES_FIJOS = [k for k, *_ in FIJOS]
LAW_PCT = 1.2
# orden de los renglones, como en las proformas reales (lo de LDS arriba si se factura; despues port dues y channel toll, tally, serenos, migraciones...)
ORDEN = ["mooring", "unmooring", "gangway", "draft", "port_dues", "anchor", "channel_toll", "pilot_in", "pilot_out", "tally", "serenos", "mig_in", "mig_out",
         "free_pratique", "aduana_", "taxi_in", "taxi_out", "taxi_sanidad", "senasa", "maritime", "misc", "extra_"]


def _lugar(clave: str) -> int:
    for i, k in enumerate(ORDEN):
        if clave == k or (k.endswith("_") and clave.startswith(k)):
            return i
    return len(ORDEN)


PIE_SIN_IMPORTE = [("tugboats", "TUGBOATS IN/OUT"), ("osro", "COMPULSORY OSRO EXPENSES")]
MAX_EXTRAS = 12


def _num(v, tope: float) -> float:
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return round(n, 4) if 0 <= n <= tope else 0.0


def clean(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = {"armado": bool(raw.get("armado"))}
    for k in CLAVES_FIJOS:
        it = raw.get(k) if isinstance(raw.get(k), dict) else {}
        out[k] = {"on": bool(it.get("on")), "precio": _num(it.get("precio"), 1e9), "cuenta_ajena": bool(it.get("cuenta_ajena")), "omitido": bool(it.get("omitido")) and not it.get("cuenta_ajena")}
    law = raw.get("law") if isinstance(raw.get("law"), dict) else {}
    out["law"] = {"on": bool(law.get("on", True)) if "on" in law else True, "precio": _num(law.get("precio"), 1e9)}
    extras = []
    for e in (raw.get("extras") if isinstance(raw.get("extras"), list) else [])[:MAX_EXTRAS]:
        if not isinstance(e, dict):
            continue
        texto = " ".join(str(e.get("texto") or "").split())[:120].upper()
        if texto:
            extras.append({"texto": texto, "moneda": "ARS" if e.get("moneda") == "ARS" else "USD", "monto": _num(e.get("monto"), 1e12), "cuenta_ajena": bool(e.get("cuenta_ajena")),
                           "omitido": bool(e.get("omitido")) and not e.get("cuenta_ajena")})
    out["extras"] = extras
    pie = raw.get("pie") if isinstance(raw.get("pie"), dict) else {}
    out["pie"] = {k: (bool(pie.get(k)) if k in pie else True) for k, _t in PIE_SIN_IMPORTE}
    return out


def desde_voucher(servicios: list[str]) -> dict:
    """El SENASA sale tildado si el voucher lo trae."""
    return {"senasa": any(s.upper().startswith("EXPENSES FOR COMPULSORY SENASA") for s in servicios or [])}


def _r2(n: float) -> float:
    return round(n + 0.0, 2)


def armar(db: Session, s: dict) -> dict:
    """La proforma consolidada a partir del estado completo `s` (ya limpio con proforma_final.clean_state)."""
    dolar = s["dolar"]["valor"] or 0.0
    b, ch = s["buque"], s["chequeo"]
    lineas: list[dict] = []

    omitidas: list[dict] = []

    def add(clave, texto, moneda, monto, destino, paso, base_law=True):
        """`destino` es el concepto del estado: se factura, va al pie (cuenta_ajena) o no figura en ningun lado (omitido)."""
        if not (monto and monto > 0):
            return
        l = {"clave": clave, "texto": texto, "moneda": moneda, "monto": monto, "ajena": bool(destino.get("cuenta_ajena")), "paso": paso, "base_law": base_law}
        (omitidas if destino.get("omitido") and not destino.get("cuenta_ajena") else lineas).append(l)

    pr = s["practicaje"]
    add("pilot_in", "PILOT SERVICE IN", "USD", pr["in"]["usd"], pr["in"], 4)
    add("pilot_out", "PILOT SERVICE OUT", "USD", pr["out"]["usd"], pr["out"], 4)
    add("port_dues", "PORT DUES", "USD", s["muelle"]["usd"], s["muelle"], 5)
    if s["fondeo"]["on"]:
        add("anchor", "ANCHOR DUES", "USD", s["fondeo"]["usd"], s["fondeo"], 5)
    add("channel_toll", "CHANNEL TOLL", "USD", s["vias"]["usd"], s["vias"], 5)
    add("mooring", "MOORING SERVICE (LDS)", "USD", s["lds_amarre"]["usd"], s["lds_amarre"], 6)
    add("unmooring", "UNMOORING SERVICE (LDS)", "USD", s["lds_desamarre"]["usd"], s["lds_desamarre"], 6)
    if s["escala"]["on"]:
        add("gangway", "SHORE GANGWAY (LDS)", "USD", s["escala"]["usd"], s["escala"], 6)
    if s["lds_draft"]["on"]:
        add("draft", "LAUNCH FOR DRAFT SURVEY (LDS)", "USD", s["lds_draft"]["usd"], s["lds_draft"], 6)
    add("tally", "HEAD TALLY CLERK", "ARS", s["tally"]["total_ars"], s["tally"], 8)
    add("serenos", "WATCHMEN SERVICES", "ARS", s["serenos"]["total_ars"], s["serenos"], 9)
    calc = migraciones.calcular(db, trn=b["trn"], items=s["migraciones"]["items"], dolar=dolar)
    textos_mig = {"mig_in": "IMMIGRATION TAX EXPENSES IN", "mig_out": "IMMIGRATION TAX EXPENSES OUT", "taxi_in": "TAXI HIRED FOR IMMIGRATION OFFICER IN",
                  "taxi_out": "TAXI HIRED FOR IMMIGRATION OFFICER OUT", "free_pratique": "FREE PRATIQUE DUES", "taxi_sanidad": "TAXI HIRED FOR SANITARY AUTHORITY"}
    for f in calc["filas"]:
        add(f["key"], textos_mig[f["key"]] + (" AT BUOY 11" if f["boya"] else ""), f["moneda"], f["total"], f, 10)
    for i in s["aduana"]["items"]:
        if i["on"]:
            add("aduana_" + i["key"], "CUSTOM HOUSE OVERTIME " + (i["texto"] or "OTHER"), "USD", i["cant"] * i["precio"], i, 7)
    for clave, texto, param, defecto in FIJOS:
        if ch[clave]["on"]:
            add(clave, texto, "USD", ch[clave]["precio"] or get_param(db, param, defecto), ch[clave], 11)
    for k, e in enumerate(ch["extras"]):
        add(f"extra_{k}", e["texto"], e["moneda"], e["monto"], e, 11)
    fees = []
    for f in s["agencia"]["fees"]:
        if f["on"] and f["monto_usd"] > 0:
            fees.append({"clave": "fee", "texto": f["texto"], "moneda": "USD", "monto": f["monto_usd"], "ajena": False, "paso": 2, "base_law": False})

    def a_usd(l):
        return l["monto"] if l["moneda"] == "USD" else (l["monto"] / dolar if dolar else None)

    def a_ars(l):
        return l["monto"] if l["moneda"] == "ARS" else l["monto"] * dolar

    lineas.sort(key=lambda l: _lugar(l["clave"]))  # estable: respeta el orden dentro de cada grupo
    facturadas = [l for l in lineas if not l["ajena"]]
    base_usd = sum(a_usd(l) or 0.0 for l in facturadas if l["base_law"])
    pct = get_param(db, "law_25413_pct", LAW_PCT)
    law_auto = base_usd * pct / 100
    law_monto = (ch["law"]["precio"] or law_auto) if ch["law"]["on"] else 0.0
    todas = facturadas + fees
    if law_monto > 0:
        todas = todas + [{"clave": "law", "texto": "LAW NR 25413", "moneda": "USD", "monto": law_monto, "ajena": False, "paso": 11, "base_law": False}]
    for n, l in enumerate(todas, start=1):
        l["n"] = n
        l["usd"] = _r2(a_usd(l)) if a_usd(l) is not None else None
        l["ars"] = _r2(a_ars(l))
    total_usd = sum(l["usd"] or 0.0 for l in todas)
    ajenas = [dict(l, usd=_r2(a_usd(l)) if a_usd(l) is not None else None, ars=_r2(a_ars(l))) for l in lineas if l["ajena"]]
    omitidas_out = [dict(l, usd=_r2(a_usd(l)) if a_usd(l) is not None else None, ars=_r2(a_ars(l))) for l in sorted(omitidas, key=lambda x: _lugar(x["clave"]))]
    pie = [t for k, t in PIE_SIN_IMPORTE if ch["pie"].get(k)]
    return {"lineas": todas, "ajenas": ajenas, "omitidas": omitidas_out, "pie": pie, "dolar": dolar,
            "total_usd": _r2(total_usd) if dolar or all(l["moneda"] == "USD" for l in todas) else None, "total_ars": _r2(sum(l["ars"] for l in todas)),
            "law": {"pct": pct, "base_usd": _r2(base_usd), "auto_usd": _r2(law_auto), "usd": _r2(law_monto), "manual": bool(ch["law"]["precio"]) and ch["law"]["on"]},
            "fijos": {k: _r2(get_param(db, p, d)) for k, _t, p, d in FIJOS}, "sin_dolar": not dolar}
