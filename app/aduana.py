"""Mail a Aduana con la salida del barco (SALIDA ADUANERA): asunto y datos, listo para abrir en Outlook como borrador (.eml)."""
from __future__ import annotations

from datetime import datetime

from .models import OperatedVessel

DATOS = ("Buque", "Muelle", "Día y Hora de salida", "Condición", "Destino")
# a quienes va el mail de la salida aduanera
DESTINATARIOS = ["mechegaray@arca.gob.ar", "esuss@arca.gob.ar", "alejarroyo@arca.gob.ar", "icostanzi@arca.gob.ar"]


def _ultimo(txt: str) -> str:
    """'ADM → MEGA' (un barco que paso por varios muelles) -> 'MEGA': de donde sale es el ultimo."""
    partes = [p.strip() for p in str(txt or "").replace("->", "→").split("→") if p.strip()]
    return partes[-1] if partes else ""


def salida_texto(zarpe: str) -> str:
    """'2026-10-02T21:01' -> '02/10/2026 – 21:01 hs'."""
    try:
        d = datetime.strptime(str(zarpe or ""), "%Y-%m-%dT%H:%M")
    except ValueError:
        return ""
    return d.strftime("%d/%m/%Y – %H:%M hs")


def condicion(operacion: str) -> str:
    """Si cargo, sale CARGADO; si descargo, sale en lastre."""
    return "EN LASTRE" if str(operacion or "").strip().lower().startswith("disch") else "CARGADO"


def titulo_buque(nombre: str) -> str:
    n = " ".join(str(nombre or "").split()).upper()
    return n if n.startswith(("MV ", "M/V ", "M.V. ")) else ("MV " + n if n else "MV")


def sin_mv(nombre: str) -> str:
    n = " ".join(str(nombre or "").split()).upper()
    for pref in ("MV ", "M/V ", "M.V. "):
        if n.startswith(pref):
            return n[len(pref):]
    return n


def armar(o: OperatedVessel) -> dict:
    """Asunto y texto del mail para un barco operado. Los datos que no estan quedan vacios (se completan en el borrador)."""
    muelle = _ultimo(o.terminal_code) or _ultimo(o.berth_label)
    filas = [("Buque", sin_mv(o.vessel_name)), ("Muelle", muelle.upper()), ("Día y Hora de salida", salida_texto(o.zarpe)),
             ("Condición", condicion(o.operation)), ("Destino", str(o.destination or "").strip().upper())]
    return {"asunto": f"{titulo_buque(o.vessel_name)} - SALIDA ADUANERA // SEA WHITE", "filas": filas,
            "texto": "\n".join(f"{k}: {v}" for k, v in filas), "faltan": [k for k, v in filas if not v]}
