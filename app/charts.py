"""Datos para los graficos de torta (donut) de "Nuestros barcos".

Los graficos se dibujan en SVG desde la plantilla (sin librerias externas), asi
que aca solo se arma la lista de porciones: cantidad, porcentaje, color y los
valores de trazo del circulo."""
from collections import Counter

# Paleta apta para daltonismo (Okabe-Ito). Todo dato tambien se ve en la
# leyenda con su numero, el color nunca es lo unico que distingue una porcion.
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#B8A600", "#8C564B"]
COLOR_OTROS = "#7f8c9a"
COLOR_SIN_CLIENTE = "#b9c4cf"


def filtrar_por_tipo(names, tipo_por_nombre: dict[str, str], tipo: str) -> tuple[list[str], list[str]]:
    """Deja los clientes del tipo pedido (AGENCY o ESTIBA) segun la planilla de Clientes.

    `tipo_por_nombre` es {nombre en minusculas: tipo} de los clientes activos de la planilla.
    Devuelve (nombres que quedan, nombres que se dejan afuera por no tener cliente o tener uno
    que no esta en la planilla; los vacios quedan como ""). Los de OTRO tipo no cuentan como
    "afuera": se ven cambiando el selector."""
    kept: list[str] = []
    fuera: list[str] = []
    for n in names:
        key = (n or "").strip().casefold()
        t = tipo_por_nombre.get(key) if key else None
        if t is None:
            fuera.append((n or "").strip())
        elif t == tipo:
            kept.append(n)
    return kept, fuera


def describir_fuera(fuera: list[str]) -> str:
    """'ISA, Alpemar, (sin cliente)': nombres distintos, en orden de aparicion."""
    vistos: list[str] = []
    for n in fuera:
        etiqueta = n or "(sin cliente)"
        if etiqueta not in vistos:
            vistos.append(etiqueta)
    return ", ".join(vistos)


def build_donut(names, max_slices: int = len(PALETTE)) -> dict:
    """Cuenta barcos por cliente. Los `max_slices` clientes con mas barcos van
    cada uno en su porcion; el resto se junta en "Otros". Los barcos sin cliente
    van aparte. Clientes con distinto uso de mayusculas se cuentan como uno."""
    label_of: dict[str, str] = {}
    counts: Counter = Counter()
    for raw in names:
        label = (raw or "").strip()
        key = label.casefold()
        if label:
            label_of.setdefault(key, label)
        counts[key] += 1

    total = sum(counts.values())
    sin_cliente = counts.pop("", 0)
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], label_of[kv[0]].casefold()))
    head, tail = ordered[:max_slices], ordered[max_slices:]

    slices = [
        {"label": label_of[key], "count": n, "color": PALETTE[i]} for i, (key, n) in enumerate(head)
    ]
    otros = sum(n for _, n in tail)
    if otros:
        cuantos = f"{len(tail)} cliente" + ("s" if len(tail) != 1 else "")
        slices.append({"label": f"Otros ({cuantos})", "count": otros, "color": COLOR_OTROS})
    if sin_cliente:
        slices.append({"label": "Sin cliente", "count": sin_cliente, "color": COLOR_SIN_CLIENTE})

    # circulo de radio 15.9155 => circunferencia 100: el trazo mide "porcentaje"
    # directamente. Empieza a las 12 (offset 25) y se deja un hueco chico entre porciones.
    acumulado = 0.0
    for s in slices:
        pct = s["count"] / total * 100 if total else 0.0
        s["pct"] = pct
        s["pct_txt"] = f"{pct:.0f}%"
        dash = pct if len(slices) == 1 else max(pct - 0.7, 0.3)
        s["dash"] = dash
        s["gap"] = 100 - dash
        s["offset"] = 25 - acumulado
        acumulado += pct
    return {"total": total, "slices": slices}
