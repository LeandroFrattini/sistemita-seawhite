"""Stowage Plan (plano de estiba): completa las plantillas de 5 y 7 bodegas, la general
y la de Heinlein, a partir de lo que se carga en la seccion "Plano de estiba".

Cada bodega lleva una o dos cargas (bodega compartida); cada carga es de un puerto y
tiene sus kilos. Los totales por puerto y el total general se calculan solos.
"""
from __future__ import annotations

from pathlib import Path

from .fechas import en_parts_heinlein, parse_number
from .xlsx_fill import M, Xlsx

TEMPLATES = Path(__file__).parent / "templates"


def _dots(n: int | float) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


# ------------------------------------------------------------------ datos ---
def model(ctx) -> dict:
    """Ordena lo cargado en la pantalla: puertos usados, cargas por bodega y totales."""
    pl = ctx.plano or {}
    n = 7 if int(pl.get("holds") or 5) == 7 else 5
    ports = []
    for i, p in enumerate((pl.get("ports") or [])[:3]):
        name = (p.get("port") or "").strip()
        if name:
            ports.append({"idx": i, "name": name.upper(), "product": (p.get("product") or "").strip().upper(),
                          "shipper": (p.get("shipper") or "").strip().upper(), "total": 0})
    if ports:  # el ultimo puerto es el actual: si no se completo, usa la Carga y el Shipper de la escala
        cur = ports[-1]
        cur["product"] = cur["product"] or ctx.c("carga").upper()
        cur["shipper"] = cur["shipper"] or (ctx.c("shipper") or ctx.c("exportador")).upper()
    by_idx = {p["idx"]: p for p in ports}
    cubic = ctx.vessel.get("cubicaje") or []
    bodegas = pl.get("bodegas") or []
    holds = []
    for h in range(1, n + 1):
        b = bodegas[h - 1] if h - 1 < len(bodegas) and isinstance(bodegas[h - 1], dict) else {}
        cargos = []
        for key in (("a", "b") if b.get("shared") else ("a",)):
            ent = b.get(key) or {}
            port = by_idx.get(ent.get("p"))
            kg = parse_number(str(ent.get("kg") or ""))
            if port is not None and kg:
                cargos.append({"port": port, "kg": int(kg)})
                port["total"] += int(kg)
        # en una bodega compartida, la carga del ultimo puerto (el actual) va arriba y la del anterior abajo
        cargos.sort(key=lambda c: 0 if c["port"] is (ports[-1] if ports else None) else 1)
        cf = parse_number(str(cubic[h - 1])) if h - 1 < len(cubic) and cubic[h - 1] else None
        holds.append({"n": h, "estado": "SLACK" if b.get("estado") == "SLACK" else "FULL", "cargos": cargos,
                      "cf": int(cf) if cf else None})
    return {"n": n, "ports": ports, "holds": holds, "grand": sum(p["total"] for p in ports),
            "current": ports[-1] if ports else None}


def last_port_total(ctx) -> int | None:
    """Total cargado en el ultimo puerto (el actual): sirve para la cantidad del Cargo Manifest."""
    m = model(ctx)
    return m["current"]["total"] if m["current"] and m["current"]["total"] else None


def _date_parts(ctx):
    d = ctx.dates.get("stowage_plan")
    if not d:
        return None
    month, day, suffix, year = en_parts_heinlein(d)
    return month.upper(), day, suffix.upper(), year


def _logo(x: Xlsx, ctx, box, w, h, pad=6.0):
    a = ctx.agency
    if a is not None and a.logo:
        x.add_logo(a.logo, a.logo_mime, box, w, h, pad_pt=pad)


def _blank_rows(x: Xlsx, rows) -> None:
    for r in rows:
        for c in x._row(r).findall(M + "c"):
            x._wipe(c)


# ----------------------------------------------------------------- general ---
GENERAL = {
    7: dict(
        file="plano_g7.xlsx", cols={7: "F", 6: "I", 5: "L", 4: "O", 3: "R", 2: "U", 1: "X"}, status_row=15,
        clear=range(17, 27), a=18, b=23, single=21, lines=["port", "prod", "kg", "unit"], cf_row=27, cf_cells={},
        name="A8", dest="X10", date="I10", date_end=".-", logo=((2, 1, 5, 5), 144.0, 66.0),
        slots=[dict(title="E32", hdr=33, line=34, unhide=(32, 33, 34)), dict(title="E37", hdr=38, line=39),
               dict(title="E43", hdr=44, line=45)],
        kg_col="X", ks_col="Z", grand="X46", grand_ks="Z46", blank=[28, 29, 30, 31, 35, 36, 40, 41, 42], spacer=(31, 9.0),
        unmerge=["U34:Y34", "F30:I30", "U30:Y30", "F40:L40", "V40:Y40"],
    ),
    5: dict(
        file="plano_g5.xlsx", cols={5: "F", 4: "I", 3: "L", 2: "O", 1: "R"}, status_row=14,
        clear=range(16, 28), a=17, b=23, single=19, lines=["port", "prodA", "prodB", "kg", "unit"], cf_row=28,
        cf_cells={3: "K"}, name="A7", dest="J9", date="C50", date_end="", logo=((2, 1, 5, 5), 144.0, 66.0),
        slots=[dict(title="E33", hdr=34, line=35, unhide=(33, 34, 35)), dict(title="E39", hdr=40, line=41),
               dict(title="E43", hdr=44, line=45)],
        kg_col="R", ks_col="T", grand="R46", grand_ks="T46", blank=[29, 30, 31, 32, 36, 37, 38, 42], spacer=(32, 9.0),
        unmerge=["F31:I31", "Q31:S31", "F35:J35", "Q35:S35", "F38:J38", "Q38:S38"],
    ),
}


def gen_general(ctx) -> bytes:
    m = model(ctx)
    cfg = GENERAL[m["n"]]
    x = Xlsx(TEMPLATES / cfg["file"])
    for rng in cfg["unmerge"]:
        x.unmerge(rng)

    x.set_text(cfg["name"], f"M{ctx.letter} {ctx.name}")
    x.set_text(cfg["dest"], ctx.c("destino").upper())
    parts = _date_parts(ctx)
    x.set_text(cfg["date"], f"{parts[0]} {parts[1]}{parts[2]} {parts[3]}{cfg['date_end']}" if parts else "")
    _logo(x, ctx, *cfg["logo"])

    # ---- bodegas
    canon = cfg["cols"][max(cfg["cols"])]  # columna de la primera bodega: de ahi se copian los formatos
    for hold in m["holds"]:
        col = cfg["cols"][hold["n"]]
        for r in cfg["clear"]:
            x.set_text(f"{col}{r}", "")
        status = hold["estado"]
        total_kg = sum(c["kg"] for c in hold["cargos"])
        if status == "FULL" and hold["cf"] and total_kg:  # FULL - SF: CF / toneladas totales de la bodega
            status = f"FULL - SF: {hold['cf'] / (total_kg / 1000):.2f}"
        x.set_text(f"{col}{cfg['status_row']}", status)
        if len(hold["cargos"]) == 2:
            starts = [cfg["a"], cfg["b"]]
        else:
            starts = [cfg["single"]]
        for start, cargo in zip(starts, hold["cargos"]):
            values = {"port": cargo["port"]["name"], "prod": f"{cargo['port']['product']} IN BULK".strip(),
                      "prodA": cargo["port"]["product"], "prodB": "IN BULK", "kg": cargo["kg"], "unit": "KILOS"}
            for i, kind in enumerate(cfg["lines"]):
                x.copy_style(f"{canon}{cfg['a'] + i}", f"{col}{start + i}")
                if kind == "kg":
                    x.set_number(f"{col}{start + i}", cargo["kg"])
                else:
                    x.set_text(f"{col}{start + i}", values[kind])
                    if kind in ("port", "prod", "prodA"):
                        x.shrink(f"{col}{start + i}")  # un nombre largo se achica en vez de pasarse de la bodega
        cf_col = cfg["cf_cells"].get(hold["n"], col)
        x.set_text(f"{cf_col}{cfg['cf_row']}", f"{_dots(hold['cf'])} CF" if hold["cf"] else "")

    # ---- totales por puerto (de arriba hacia abajo; los puertos usan los lugares de abajo)
    for r in cfg["blank"]:
        _blank_rows(x, [r])
    slots = cfg["slots"]
    used = slots[len(slots) - len(m["ports"]):] if m["ports"] else []
    canon_slot = slots[-1]
    kg_col, ks_col = cfg["kg_col"], cfg["ks_col"]
    for slot in slots:
        t_row = int(slot["title"][1:])
        for r in (t_row, slot["hdr"], slot["line"]):
            _blank_rows(x, [r])
    if len(m["ports"]) >= 3:  # el primer cuadro usa filas que estaban ocultas
        for r in slots[0].get("unhide", ()):
            x.show_row(r, 12.0)
        x.show_row(*cfg["spacer"])
    ct, ch, cl = int(canon_slot["title"][1:]), canon_slot["hdr"], canon_slot["line"]
    for slot, port in zip(used, m["ports"]):
        t_row, h_row, l_row = int(slot["title"][1:]), slot["hdr"], slot["line"]
        for col in ("E", "B", "F", kg_col, ks_col):
            for src, dst in ((ct, t_row), (ch, h_row), (cl, l_row)):
                if slot is not canon_slot:
                    x.copy_style(f"{col}{src}", f"{col}{dst}")
        x.set_text(f"E{t_row}", f"TOTAL CARGOES LOADED AT THE PORT OF {port['name']}:")
        x.set_text(f"B{h_row}", "SHIPPERS")
        x.set_text(f"F{h_row}", "COMMODITIES")
        x.set_text(f"B{l_row}", port["shipper"])
        x.set_text(f"F{l_row}", f"{port['product']} IN BULK, said to weigh:".strip())
        x.set_number(f"{kg_col}{l_row}", port["total"])
        x.set_text(f"{ks_col}{l_row}", "ks")
    x.set_number(cfg["grand"], m["grand"])
    x.set_text(cfg["grand_ks"], "ks")
    return x.to_bytes()


# ---------------------------------------------------------------- Heinlein ---
HEIN = {
    5: dict(file="plano_h5.xlsx", cols={5: "F", 4: "G", 3: "H", 2: "I", 1: "J"}, hold_cols=list("DEFGHIJ"),
            port="J3", date="J4", dest="J5", name="D9", flag="B19", foot="A41",
            title=("D", "J"), prod=("C", "F"), tot=("G", "H"), kgs="I", draft="J", mtrs="K"),
    7: dict(file="plano_h7.xlsx", cols={7: "C", 6: "D", 5: "E", 4: "F", 3: "G", 2: "H", 1: "I"}, hold_cols=list("CDEFGHI"),
            port="H3", date="H4", dest="H5", name="C9", flag="A19", foot="A41",
            title=("C", "I"), prod=("C", "D"), tot=("E", "F"), kgs="G", draft="H", mtrs="I"),
}
_ALL_COLS = [chr(c) for c in range(ord("A"), ord("N") + 1)]


def gen_heinlein(ctx) -> bytes:
    m = model(ctx)
    cfg = HEIN[m["n"]]
    x = Xlsx(TEMPLATES / cfg["file"])
    ports = m["ports"]
    cur_name = m["current"]["name"] if m["current"] else "BAHIA BLANCA"
    mv = f'M/{ctx.letter} "{ctx.name}"'
    parts = _date_parts(ctx)
    x.set_text(cfg["port"], f"{cur_name}, ARGENTINA.")
    x.set_text(cfg["date"], f"{parts[0]} {parts[1]}{parts[2]}, {parts[3]}." if parts else "")
    x.set_text(cfg["dest"], ctx.c("destino").upper())
    x.set_text(cfg["name"], mv)
    x.set_text(cfg["foot"], mv)
    x.set_text(cfg["flag"], ctx.v("flag").upper())

    # ---- bodegas
    canon = cfg["cols"][max(cfg["cols"])]
    single = {"prod": 19, "bulk": 20, "port": 23, "PORT": 24, "kg": 27, "KGS": 28}
    block = [("prod", 19), ("bulk", 20), ("port", 23), ("PORT", 24), ("kg", 27), ("KGS", 28)]  # filas modelo (estilos)
    for col in cfg["hold_cols"]:
        for r in range(18, 31):
            x.set_text(f"{col}{r}", "")
    for hold in m["holds"]:
        col = cfg["cols"][hold["n"]]
        x.set_text(f"{col}17", hold["estado"])
        cargos = hold["cargos"]
        if len(cargos) == 2:
            layouts = [dict(zip(("prod", "bulk", "port", "PORT", "kg", "KGS"), range(18, 24))),
                       dict(zip(("prod", "bulk", "port", "PORT", "kg", "KGS"), range(24, 30)))]
        else:
            layouts = [single]
        for lay, cargo in zip(layouts, cargos):
            vals = {"prod": cargo["port"]["product"], "bulk": "IN BULK", "port": cargo["port"]["name"], "PORT": "PORT",
                    "kg": cargo["kg"], "KGS": "KGS"}
            for kind, model_row in block:
                ref = f"{col}{lay[kind]}"
                x.copy_style(f"{canon}{model_row}", ref)
                if kind == "kg":
                    x.set_number(ref, cargo["kg"])
                    x.set_numfmt(ref, 3)
                else:
                    x.set_text(ref, vals[kind])
                    if kind in ("prod", "port"):
                        x.shrink(ref)  # un nombre largo se achica en vez de pasarse de la bodega
        if len(cargos) == 2:
            x.set_bottom_border(f"{col}23")
        if cargos and hold["estado"] == "FULL" and hold["cf"]:  # SF = CF / toneladas totales de la bodega
            x.copy_style(f"{canon}30", f"{col}30")
            x.set_text(f"{col}30", f"SF: {hold['cf'] / (sum(c['kg'] for c in cargos) / 1000):.2f}")

    # ---- totales
    P = len(ports)
    if P >= 3:
        x.insert_rows(37, 2 * (P - 2))
    a, b = cfg["title"]
    pa, pb = cfg["prod"]
    ta, tb = cfg["tot"]
    for r in (32, 33, 34):
        x.blank_row(r)
    for rng in (f"{a}32:{b}32", f"{pa}34:{pb}34", f"{ta}34:{tb}34"):
        x.unmerge(rng)
    if P == 0:
        return x.to_bytes()
    final = 34 if P == 1 else 32 + 2 * P
    value_rows = [] if P == 1 else [33 + 2 * i for i in range(P)]
    title_rows = [32 + 2 * i for i in range(P)]
    # estilos modelo: se copian de las filas 34 (valores) y 32 (titulo) ANTES de pisarlas
    for r in value_rows + [final]:
        if r != 34:
            for col in _ALL_COLS:
                x.copy_style(f"{col}34", f"{col}{r}")
    for r in title_rows:
        if r != 32:
            for col in _ALL_COLS:
                x.copy_style(f"{col}32", f"{col}{r}")
    for r in title_rows + value_rows + [final]:
        x.show_row(r, 15.0 if r in title_rows else 12.75)
    for t, port in zip(title_rows, ports):
        x.merge(f"{a}{t}:{b}{t}")
        x.set_text(f"{a}{t}", f"TOTAL CARGO LOADED AT {port['name']} PORT")
    for v, port in zip(value_rows, ports):
        x.merge(f"{pa}{v}:{pb}{v}")
        x.merge(f"{ta}{v}:{tb}{v}")
        x.set_text(f"{pa}{v}", f"{port['product']} IN BULK".strip())
        x.set_number(f"{ta}{v}", port["total"])
        x.set_numfmt(f"{ta}{v}", 3)
        x.set_text(f"{cfg['kgs']}{v}", "KGS")
    x.merge(f"{pa}{final}:{pb}{final}")
    x.merge(f"{ta}{final}:{tb}{final}")
    x.set_text(f"{pa}{final}", (f"{ports[0]['product']} IN BULK".strip() if P == 1 else "TOTAL LOADED IN BULK"))
    x.set_number(f"{ta}{final}", m["grand"])
    x.set_numfmt(f"{ta}{final}", 3)
    x.set_text(f"{cfg['kgs']}{final}", "KGS   -   DRAFT:")
    x.set_text(f"{cfg['draft']}{final}", "")  # el calado se completa a mano
    x.set_text(f"{cfg['mtrs']}{final}", "MTRS F.W.")
    return x.to_bytes()
