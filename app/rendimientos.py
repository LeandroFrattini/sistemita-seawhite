"""Ritmos de carga y descarga: los datos de rendimientos_data.py armados para mostrarlos por muelle o por producto (Utilidades de Operaciones)."""
from __future__ import annotations

from .rendimientos_data import RENDIMIENTOS, SIN_DATOS

# Los muelles agrupados por lo que se opera en ellos (para no mostrar una lista larga y plana)
GRUPOS = [
    ("Granos, subproductos y aceites", ["ADM AGRO TERMINAL", "CARGILL TERMINAL", "DREYFUS", "PIER 2/3 GALVAN", "PIER 5/6 TBB", "PIER 9 TBB"]),
    ("Fertilizantes y carga general", ["PIER 21", "PIER 5 GALVAN", "PROFERTIL TERMINAL"]),
    ("Inflamables y químicos", ["JETTY 1", "JETTY 2", "JETTY 3", "MEGA TERMINAL"]),
]


def fmt(n: int) -> str:
    """9000 -> '9.000'; 0 -> '—' (no se opera en ese sentido)."""
    return f"{n:,}".replace(",", ".") if n else "—"


def por_muelle() -> list[dict]:
    """[{titulo, muelles: [{nombre, filas: [{producto, rubro, carga, descarga, nota}]}]}] con los muelles en su grupo y los productos en orden alfabetico."""
    filas_de: dict[str, list[dict]] = {}
    for _cod, producto, rubro, muelle, carga, descarga, nota in RENDIMIENTOS:
        filas_de.setdefault(muelle, []).append({"producto": producto, "rubro": rubro, "carga": fmt(carga), "descarga": fmt(descarga), "nota": nota})
    conocidos = {m for _t, ms in GRUPOS for m in ms}
    grupos = [(t, [m for m in ms if m in filas_de]) for t, ms in GRUPOS]
    otros = sorted(m for m in filas_de if m not in conocidos)
    if otros:
        grupos.append(("Otros muelles", otros))
    def tarjeta(m: str) -> dict:
        filas = sorted(filas_de[m], key=lambda f: f["producto"])
        # solo se muestran las columnas que tienen algun dato en este muelle (si no se descarga nada, no hay columna de descarga)
        return {"nombre": m, "filas": filas, "tiene_carga": any(f["carga"] != "—" for f in filas), "tiene_descarga": any(f["descarga"] != "—" for f in filas)}

    return [{"titulo": t, "muelles": [tarjeta(m) for m in ms]} for t, ms in grupos if ms]


def por_producto() -> list[dict]:
    """[{cod, nombre, rubro, muelles: [{nombre, carga, descarga, mejor_carga, mejor_descarga, nota}]}] ordenado por rubro y producto.
    Marca el muelle de mayor rendimiento de carga (y de descarga) cuando el producto se opera en mas de uno."""
    prods: dict[str, dict] = {}
    for cod, producto, rubro, muelle, carga, descarga, nota in RENDIMIENTOS:
        p = prods.setdefault(producto, {"cod": cod, "nombre": producto, "rubro": rubro, "_m": []})
        p["_m"].append((muelle, carga, descarga, nota))
    out = []
    for p in prods.values():
        ms = p.pop("_m")
        max_c, max_d = max(m[1] for m in ms), max(m[2] for m in ms)
        n_c, n_d = sum(1 for m in ms if m[1] > 0), sum(1 for m in ms if m[2] > 0)
        p["muelles"] = [{"nombre": m, "carga": fmt(c), "descarga": fmt(d), "nota": nota,
                         "mejor_carga": n_c > 1 and c == max_c, "mejor_descarga": n_d > 1 and d == max_d} for m, c, d, nota in ms]
        p["tiene_carga"], p["tiene_descarga"] = n_c > 0, n_d > 0
        out.append(p)
    return sorted(out, key=lambda p: (p["rubro"], p["nombre"]))


def sin_datos() -> list[dict]:
    return [{"cod": c, "nombre": n, "rubro": r} for c, n, r in sorted(SIN_DATOS, key=lambda x: (x[2], x[1]))]
