import re

from app.charts import COLOR_OTROS, COLOR_SIN_CLIENTE, PALETTE, build_donut
from app.database import SessionLocal
from app.models import OperatedVessel, Terminal, VesselCall
from app.service import get_draft_lineup

from .conftest import login, make_user


# --- logica de las porciones -------------------------------------------------- #

def test_cuenta_por_cliente_y_ordena_de_mayor_a_menor():
    d = build_donut(["AMI", "Blue Star", "AMI", "Oceanway", "AMI", "Blue Star"])
    assert d["total"] == 6
    assert [(s["label"], s["count"]) for s in d["slices"]] == [("AMI", 3), ("Blue Star", 2), ("Oceanway", 1)]
    assert [s["color"] for s in d["slices"]] == PALETTE[:3]
    assert [s["pct_txt"] for s in d["slices"]] == ["50%", "33%", "17%"]


def test_mayusculas_y_espacios_cuentan_como_el_mismo_cliente():
    d = build_donut(["Blue Star", " blue star ", "BLUE STAR"])
    assert [(s["label"], s["count"]) for s in d["slices"]] == [("Blue Star", 3)]
    assert d["slices"][0]["dash"] == 100 and d["slices"][0]["gap"] == 0  # una sola porcion: circulo completo


def test_sin_cliente_va_aparte_y_al_final():
    d = build_donut(["AMI", "", None, "AMI", "  "])
    assert d["total"] == 5
    assert [(s["label"], s["count"]) for s in d["slices"]] == [("AMI", 2), ("Sin cliente", 3)]
    assert d["slices"][-1]["color"] == COLOR_SIN_CLIENTE


def test_los_clientes_de_mas_se_juntan_en_otros():
    names = [f"Cliente {i}" for i in range(9) for _ in range(9 - i)]  # 9 clientes
    d = build_donut(names, max_slices=7)
    assert len(d["slices"]) == 8
    otros = d["slices"][-1]
    assert otros["label"] == "Otros (2 clientes)" and otros["color"] == COLOR_OTROS
    assert otros["count"] == 2 + 1
    assert sum(s["count"] for s in d["slices"]) == d["total"]


def test_vacio_no_rompe_y_los_arcos_cierran_el_circulo():
    assert build_donut([]) == {"total": 0, "slices": []}
    d = build_donut(["A", "A", "B", "C", "C", "C"])
    assert abs(sum(s["pct"] for s in d["slices"]) - 100) < 1e-9
    # cada arco arranca donde termino el anterior (empieza a las 12: offset 25)
    assert d["slices"][0]["offset"] == 25
    assert abs(d["slices"][1]["offset"] - (25 - d["slices"][0]["pct"])) < 1e-9


# --- la pantalla ------------------------------------------------------------------ #

def _operado(nombre, principal, period):
    return OperatedVessel(vessel_name=nombre, principal=principal, period=period, terminal_code="ADM")


def _svg_label(html: str, titulo: str) -> str:
    """aria-label del grafico cuyo titulo es `titulo` (trae 'cliente cantidad, ...')."""
    for m in re.finditer(r'aria-label="([^"]*)"', html):
        if m.group(1).startswith(titulo + ":"):
            return m.group(1)
    return ""


def test_pantalla_dos_graficos_y_filtro_por_mes(client):
    make_user("op")
    login(client, "op", "claveLarga-2026")
    with SessionLocal() as db:
        db.add_all([
            _operado("A", "AMI", "2026-08"), _operado("B", "AMI", "2026-08"), _operado("C", "Blue Star", "2026-08"),
            _operado("D", "Oceanway", "2026-09"), _operado("E", "AMI", "2026-09"),
        ])
        db.commit()

    todos = client.get("/nuestros-barcos")
    assert todos.status_code == 200
    assert "Barcos operados por cliente" in todos.text and "Barcos anunciados por cliente" in todos.text
    assert todos.text.count('class="donut"') == 1  # anunciados vacio: solo el de operados
    assert "No hay barcos anunciados" in todos.text
    assert "AMI 3" in _svg_label(todos.text, "Barcos operados por cliente")
    assert "Todos los meses" in todos.text

    agosto = client.get("/nuestros-barcos?mes=2026-08")
    lab = _svg_label(agosto.text, "Barcos operados por cliente")
    assert "AMI 2" in lab and "Blue Star 1" in lab and "Oceanway" not in lab
    assert "Agosto 2026" in agosto.text

    vacio = client.get("/nuestros-barcos?mes=2019-01")
    assert "No hay barcos operados en ese período." in vacio.text


def test_pantalla_anunciados_son_los_nuestros_del_lineup(client):
    make_user("op")
    login(client, "op", "claveLarga-2026")
    client.get("/nuestros-barcos")  # crea el line-up borrador
    with SessionLocal() as db:
        lineup = get_draft_lineup(db, "GRAIN")
        term = db.query(Terminal).filter(Terminal.kind == "GRAIN", Terminal.active.is_(True)).first()
        for i, (nombre, cliente, nuestro) in enumerate([
            ("V1", "AMI", True), ("V2", "AMI", True), ("V3", "Oceanway", True), ("V4", "AMI", False),
        ]):
            db.add(VesselCall(lineup_id=lineup.id, terminal_id=term.id, sort_order=i, vessel_name=nombre,
                              vessel_type="Bulk Carrier", is_ours=nuestro, principal_text=cliente))
        db.commit()

    r = client.get("/nuestros-barcos")
    lab = _svg_label(r.text, "Barcos anunciados por cliente")
    assert "AMI 2" in lab and "Oceanway 1" in lab  # el barco que no es nuestro no cuenta
    assert re.search(r'class="donut-num">3</text>', r.text)  # total en el centro del donut


def test_hasta_ocho_clientes_van_cada_uno_en_su_porcion():
    d = build_donut([f"Cliente {i}" for i in range(8)])
    assert len(d["slices"]) == 8 and all(s["label"].startswith("Cliente") for s in d["slices"])


def test_plural_de_otros():
    uno = build_donut([f"C{i}" for i in range(9)])                  # 9 clientes: 1 queda en "Otros"
    assert uno["slices"][-1]["label"] == "Otros (1 cliente)"
