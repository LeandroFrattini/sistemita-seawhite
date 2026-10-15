"""Proforma final (Administracion): estado del asistente, Excel descargable y lectura de ese mismo Excel.

El sistema NO guarda las proformas finales: el asistente vive en el navegador y se baja como Excel. Ese Excel
lleva una hoja oculta (_estado) con todos los datos, asi la pagina puede volver a leerlo para rehacer o modificar
una proforma vieja. Se guarda una "foto" de los valores usados (dolar, fee, cargas sociales), por eso una proforma
vieja se reabre con los valores de su momento y no con los de hoy.
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

VERSION = 3
MARCA = "SEAWHITE-PROFORMA-FINAL"
HOJA_ESTADO = "_estado"
MAX_BYTES = 5 * 1024 * 1024
_CHUNK = 30000  # una celda de Excel admite 32767 caracteres
MAX_FEES = 40

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

PASOS = [
    (1, "Barco y dólar", "Elegí el barco y la cotización"),
    (2, "Agencia a facturar", "Fee y cargas sociales"),
    (3, "Datos del buque", "Horarios y opciones que activan cálculos"),
    (4, "Uso de muelle, fondeadero y vías navegables", "Con sus reglas y límites"),
    (5, "Amarre y desamarre", "Tarifa fija según el horario"),
    (6, "Habilitaciones de aduana", "Conceptos y valores"),
    (7, "Tally", "En base a lo ya completado"),
    (8, "Serenos", "Turnos y cargas sociales"),
    (9, "Migraciones y sanitary free pratique", "Según lo tildado en el paso 3"),
    (10, "Chequeo general", "Revisar y modificar todo"),
]


def tipo_dia(d: date, feriados: set[str], no_laborables: set[str] | frozenset = frozenset()) -> str:
    """FERIADO | SABADO | DOMINGO | NO_LABORABLE | SEMANA.

    El feriado manda sobre todo. El dia no laborable solo se distingue de un dia de semana: si cae sabado o
    domingo se toma como sabado o domingo (a confirmar con el usuario)."""
    if d.isoformat() in feriados:
        return "FERIADO"
    base = {5: "SABADO", 6: "DOMINGO"}.get(d.weekday(), "SEMANA")
    if base == "SEMANA" and d.isoformat() in no_laborables:
        return "NO_LABORABLE"
    return base


def con_cargas(costo: float, pct: float) -> float:
    """Costo con cargas sociales: el % se SUMA (165 sobre 100 da 265)."""
    return costo * (1 + pct / 100)


def _num(v, tope: float) -> float:
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return round(n, 4) if 0 <= n <= tope else 0.0


def _fecha(v) -> str:
    try:
        return date.fromisoformat(str(v)).isoformat()
    except (TypeError, ValueError):
        return ""


def _datetime(v) -> str:
    """Fecha y hora como la guarda 'Completar datos' (yyyy-mm-ddThh:mm), o vacio."""
    try:
        return datetime.strptime(str(v), "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return ""


def _texto(v, largo: int) -> str:
    return " ".join(str(v or "").split())[:largo]


def clean_buque(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    try:
        op_id = int(raw.get("operated_id")) if raw.get("operated_id") not in (None, "") else None
    except (TypeError, ValueError):
        op_id = None
    return {
        "operated_id": op_id,
        "nombre": _texto(raw.get("nombre"), 120),
        "imo": _texto(raw.get("imo"), 20),
        "sitio": _texto(raw.get("sitio"), 120),
        "amarre": _datetime(raw.get("amarre")),
        "inicio": _datetime(raw.get("inicio")),
        "fin": _datetime(raw.get("fin")),
        "zarpe": _datetime(raw.get("zarpe")),
        "cantidad": _texto(raw.get("cantidad"), 40),
    }


def clean_state(raw) -> dict:
    """Se queda solo con los campos conocidos y con valores validos (el estado puede venir de un Excel ajeno)."""
    raw = raw if isinstance(raw, dict) else {}
    dolar = raw.get("dolar") if isinstance(raw.get("dolar"), dict) else {}
    ag = raw.get("agencia") if isinstance(raw.get("agencia"), dict) else {}
    try:
        ag_id = int(ag.get("id")) if ag.get("id") not in (None, "") else None
    except (TypeError, ValueError):
        ag_id = None
    fees = []
    for f in (ag.get("fees") if isinstance(ag.get("fees"), list) else [])[:MAX_FEES]:
        if not isinstance(f, dict):
            continue
        texto = " ".join(str(f.get("texto") or "").split())[:200]
        if texto:
            fees.append({"texto": texto, "monto_usd": _num(f.get("monto_usd"), 10_000_000), "on": bool(f.get("on"))})
    # v1 tenia un solo "cargas_pct" y un solo "fee_usd": se leen como serenos y como un renglon de fee
    serenos = ag.get("serenos_pct", ag.get("cargas_pct"))
    if not fees and _num(ag.get("fee_usd"), 10_000_000):
        fees.append({"texto": "FEE", "monto_usd": _num(ag.get("fee_usd"), 10_000_000), "on": True})
    return {
        "v": VERSION,
        "buque": clean_buque(raw.get("buque")),
        "dolar": {
            "valor": _num(dolar.get("valor"), 1_000_000),
            "fecha": _fecha(dolar.get("fecha")),
            "origen": "BNA" if dolar.get("origen") == "BNA" else "MANUAL",
        },
        "agencia": {
            "id": ag_id,
            "nombre": str(ag.get("nombre") or "").strip()[:120],
            "serenos_pct": _num(serenos, 1000),
            "tally_pct": _num(ag.get("tally_pct"), 1000),
            "fees": fees,
        },
    }


def total_fee(state: dict) -> float:
    return round(sum(f["monto_usd"] for f in state["agencia"]["fees"] if f["on"]), 2)


def build_excel(state: dict) -> bytes:
    """Excel de la proforma: hoja visible con lo cargado + hoja oculta con el estado completo."""
    s = clean_state(state)
    wb = Workbook()
    ws = wb.active
    ws.title = "Proforma"
    azul = PatternFill("solid", fgColor="1F67B0")
    ws["A1"] = "PROFORMA FINAL"
    ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
    ws["A1"].fill = azul
    ws.merge_cells("A1:C1")
    b = s["buque"]
    filas = [
        ("Buque", b["nombre"], (b["sitio"] + (" · IMO " + b["imo"] if b["imo"] else "")).strip(" ·")),
        ("Amarre", b["amarre"].replace("T", " "), ""),
        ("Inicio de operación", b["inicio"].replace("T", " "), ""),
        ("Fin de operación", b["fin"].replace("T", " "), ""),
        ("Zarpe", b["zarpe"].replace("T", " "), ""),
        ("Cantidad operada", b["cantidad"], ""),
        ("Dólar (divisa BNA)", s["dolar"]["valor"] or "", "Cotización del " + (s["dolar"]["fecha"] or "—")
         + (" · traído del BNA" if s["dolar"]["origen"] == "BNA" else " · cargado a mano")),
        ("Agencia a facturar", s["agencia"]["nombre"], ""),
    ]
    r = 3
    for a, b, c in filas:
        ws.cell(r, 1, a).font = Font(bold=True)
        ws.cell(r, 2, b)
        ws.cell(r, 3, c)
        r += 1
    ws.cell(r, 1, "Fee aplicado").font = Font(bold=True)
    elegidos = [f for f in s["agencia"]["fees"] if f["on"]]
    if not elegidos:
        ws.cell(r, 2, "—")
        r += 1
    for f in elegidos:
        ws.cell(r, 2, f["monto_usd"])
        ws.cell(r, 3, f["texto"])
        r += 1
    ws.cell(r, 1, "Total fee (USD)").font = Font(bold=True)
    ws.cell(r, 2, total_fee(s))
    r += 1
    ws.cell(r, 1, "Cargas sociales Serenos (%)").font = Font(bold=True)
    ws.cell(r, 2, s["agencia"]["serenos_pct"])
    ws.cell(r, 3, "Se suman al costo: sobre 100 con 165 % da 265")
    r += 1
    ws.cell(r, 1, "Cargas sociales Head Tally (%)").font = Font(bold=True)
    ws.cell(r, 2, s["agencia"]["tally_pct"])
    r += 2
    ws.cell(r, 1, "Los pasos 3 a 10 se suman a esta planilla a medida que se arman en el sistema.").alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 52

    est = wb.create_sheet(HOJA_ESTADO)
    est["A1"] = f"{MARCA} v{VERSION}"
    texto = json.dumps(s, ensure_ascii=False, separators=(",", ":"))
    for i in range(0, len(texto), _CHUNK):
        est.cell(2 + i // _CHUNK, 1, texto[i:i + _CHUNK])
    est.sheet_state = "hidden"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def read_excel(data: bytes) -> dict:
    """Lee el estado de un Excel bajado por este sistema. ValueError si no lo es."""
    if len(data) > MAX_BYTES:
        raise ValueError("El archivo es demasiado grande para ser una proforma del sistema.")
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise ValueError("No se pudo abrir el archivo. Tiene que ser un Excel (.xlsx) bajado desde este sistema.")
    if HOJA_ESTADO not in wb.sheetnames:
        raise ValueError("Este Excel no fue generado por el sistema (falta la hoja con los datos de la proforma).")
    ws = wb[HOJA_ESTADO]
    if not str(ws["A1"].value or "").startswith(MARCA):
        raise ValueError("Este Excel no fue generado por el sistema.")
    partes = []
    for row in ws.iter_rows(min_row=2, max_col=1, values_only=True):
        if row[0] is None:
            break
        partes.append(str(row[0]))
    try:
        return clean_state(json.loads("".join(partes)))
    except ValueError:
        raise ValueError("Los datos guardados en el Excel están dañados o fueron modificados.")
