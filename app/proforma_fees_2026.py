"""Fee y cargas sociales por agencia, transcriptos de "Clientes 2026" (FEE.pdf), renglon por renglon, tal cual.

Cada renglon se carga con el texto original. El monto se sugiere con el primer numero del texto; si el texto trae
mas de un numero, un "+", "(ver)" o no es claro, queda marcado "revisar" para que Administracion lo confirme.
Cargas sociales: % que se suma al costo (165 -> un costo de 100 pasa a valer 265). serenos / head tally (encargado).
"""
from __future__ import annotations

import re

# (nombres posibles del cliente en minuscula, cargas serenos, cargas head tally, [renglones])
FEES_2026 = [
    (("abbey",), 165, 167, [
        "FEE bunker USD 450", "FEE ARMADOR: 600", "FEE AGENTE: USD 1000",
        "VENTONITA / BARITINA: USD 1500 - USD 150",
    ]),
    (("atlas",), None, None, ["FEE USD 300 + gastos 1000 (ver)", "FEE BODEGAS USD 300"]),
    (("blue star", "bluestar"), 165, 167, [
        "USD 400 FEE BODEGAS", "ARMADOR FEE USD 450 MISC USD 150", "FEE USD 800 - MISCELLANEUS USD 250",
        "CREW USD 60 (EACH ONE)",
    ]),
    (("b2b", "back to back"), 165, 167, [
        "FEE AGENTES USD 750 - GASTOS USD 120", "FEE PEDIDORES USD 600 - GASTOS USD 120",
        "COMBUSTIBLE - bodega USD 350", "FEE USD 60 FOR EMBARK/DESEMBARK",
    ]),
    (("ecsa",), 130, 130, ["FEE USD 650", "FEE FOR EMB/DESEMBARK USD 50", "GASTOS USD 100"]),
    (("heinlein",), 165, 167, [
        "FEE AGENTES USD 750", "FEE PEDIDORES USD 600", "COMBUSTIBLE USD 350",
        "FEE USD 60 FOR EMBARK/DESEMBARK", "GASTOS USD 120",
    ]),
    (("mc larty", "mclarty", "mc larti"), 140, 140, ["FEE USD 800 + usd 100", "FEE ARMADOR USD 250", "FEE EMB/DESEMBARK USD 50"]),
    # Oceanway: la lista trae un solo valor (117 %): se carga igual en serenos y head tally
    (("oceanway",), 117, 117, ["FEE ALL INCLUDED USD 1000", "FEE ARMADOR USD 650"]),
    (("sea plat",), 165, 167, ["FEE USD 700", "FEE EMB/DESEMBARK 50", "GASTOS USD 300"]),
    (("seven seas",), 165, 167, ["USD 450 PEDIDOR - USD 1600 AGENCIA - USD 250 HOLDS"]),
    (("service management",), 165, 167, [
        "FEE USD 1200 - Exp USD 100", "FEE EMB/DESEMBARK USD 60", "Ferni H USD 500 - Orfeas USD 1000",
    ]),
    (("t&t", "krissax"), 165, 167, ["FEE USD 800 - MISCELLANEUS USD 250", "ARMADOR FEE USD 450 MISC USD 150"]),
    # World Bond = WBL
    (("wbl", "world bond"), 165, 167, [
        "FEE AGENCIA USD 900 - GASTOS USD 100", "FEE PEDIDORES USD 600 - USD 100",
        "FEE EMBARK/DESEMBARK USD 70", "BODEGAS FEE USD 375 - BUNKER 450",
    ]),
]

_NUM = re.compile(r"\d[\d.,]*")


def sugerir_monto(texto: str) -> tuple[float, bool]:
    """(monto sugerido, revisar). Primer numero del texto; revisar si no es un unico monto claro."""
    nums = _NUM.findall(texto)
    if not nums:
        return 0.0, True
    try:
        monto = float(nums[0].replace(",", "."))
    except ValueError:
        return 0.0, True
    t = texto.lower()
    return monto, len(nums) != 1 or "+" in texto or "(ver)" in t or "each one" in t


def buscar_en_lista(nombre_cliente: str):
    """La entrada de FEES_2026 que corresponde a un cliente, o None."""
    n = (nombre_cliente or "").strip().lower()
    for entrada in FEES_2026:
        if any(p in n for p in entrada[0]):
            return entrada
    return None
