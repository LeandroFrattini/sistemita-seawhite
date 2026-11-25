"""Utilidades -> Números importantes: arma las secciones de la pantalla a partir de los datos fijos de numeros_data.py."""
from __future__ import annotations

from . import numeros_data as d

SIN_EMPRESA = "Sin empresa indicada"


def _por_empresa(filas, campo_empresa: int = 0) -> list[dict]:
    """Agrupa conservando el orden de aparición; lo que no tiene empresa va al final."""
    grupos: dict[str, list] = {}
    for f in filas:
        grupos.setdefault(f[campo_empresa] or SIN_EMPRESA, []).append(f)
    orden = [k for k in grupos if k != SIN_EMPRESA] + ([SIN_EMPRESA] if SIN_EMPRESA in grupos else [])
    return [{"empresa": k, "filas": grupos[k], "sin_empresa": k == SIN_EMPRESA} for k in orden]


def remolcadores() -> list[dict]:
    return [{**g, "filas": [{"nombre": f[1], "matricula": f[2]} for f in g["filas"]]} for g in _por_empresa(d.REMOLCADORES)]


def practicos() -> list[dict]:
    return [{**g, "filas": [{"nombre": f[1], "matricula": f[2], "datos": f[3]} for f in g["filas"]]} for g in _por_empresa(d.PRACTICOS)]


def clientes_por_practico() -> list[dict]:
    out: dict[str, list[str]] = {}
    for cliente, empresa in d.PRACTICO_POR_CLIENTE:
        out.setdefault(empresa, []).append(cliente)
    return [{"empresa": e, "clientes": sorted(c)} for e, c in sorted(out.items())]


def telefonos() -> list[dict]:
    """Los cuatro listados de teléfonos como tarjetas: título, columnas y renglones (el último valor de cada renglón es el teléfono)."""
    return [
        {"titulo": "Controles", "cols": ("Empresa", "Contacto", "Teléfono"), "filas": [list(f) for f in d.CONTROLES]},
        {"titulo": "Terminales", "cols": ("Terminal", "Contacto", "Teléfono"), "filas": [list(f) for f in d.TERMINALES]},
        {"titulo": "Estiba", "cols": ("Nombre", "Teléfono"), "filas": [list(f) for f in d.ESTIBA]},
        {"titulo": "Draft", "cols": ("Nombre", "Teléfono"), "filas": [list(f) for f in d.DRAFT]},
    ]


def total() -> dict:
    return {"remolcadores": len(d.REMOLCADORES), "practicos": len(d.PRACTICOS),
            "telefonos": len(d.CONTROLES) + len(d.TERMINALES) + len(d.ESTIBA) + len(d.DRAFT)}
