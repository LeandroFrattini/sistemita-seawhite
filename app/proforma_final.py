"""Proforma final (Administracion): estado del asistente, Excel descargable y lectura de ese mismo Excel.

El sistema NO guarda las proformas finales: el asistente vive en el navegador y se baja como Excel. Ese Excel
lleva una hoja oculta (_estado) con todos los datos, asi la pagina puede volver a leerlo para rehacer o modificar
una proforma vieja. Se guarda una "foto" de los valores usados (dolar, fee, cargas sociales), por eso una proforma
vieja se reabre con los valores de su momento y no con los de hoy.
"""
from __future__ import annotations

import io
import json
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

VERSION = 1
MARCA = "SEAWHITE-PROFORMA-FINAL"
HOJA_ESTADO = "_estado"
MAX_BYTES = 5 * 1024 * 1024
_CHUNK = 30000  # una celda de Excel admite 32767 caracteres

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

PASOS = [
    (1, "Dólar", "Divisa Banco Nación"),
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


def tipo_dia(d: date, feriados: set[str]) -> str:
    """SEMANA | SABADO | DOMINGO | FERIADO (el feriado manda sobre sabado y domingo)."""
    if d.isoformat() in feriados:
        return "FERIADO"
    return {5: "SABADO", 6: "DOMINGO"}.get(d.weekday(), "SEMANA")


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


def clean_state(raw) -> dict:
    """Se queda solo con los campos conocidos y con valores validos (el estado puede venir de un Excel ajeno)."""
    raw = raw if isinstance(raw, dict) else {}
    dolar = raw.get("dolar") if isinstance(raw.get("dolar"), dict) else {}
    ag = raw.get("agencia") if isinstance(raw.get("agencia"), dict) else {}
    try:
        ag_id = int(ag.get("id")) if ag.get("id") not in (None, "") else None
    except (TypeError, ValueError):
        ag_id = None
    return {
        "v": VERSION,
        "dolar": {
            "valor": _num(dolar.get("valor"), 1_000_000),
            "fecha": _fecha(dolar.get("fecha")),
            "origen": "BNA" if dolar.get("origen") == "BNA" else "MANUAL",
        },
        "agencia": {
            "id": ag_id,
            "nombre": str(ag.get("nombre") or "").strip()[:120],
            "fee_usd": _num(ag.get("fee_usd"), 10_000_000),
            "cargas_pct": _num(ag.get("cargas_pct"), 100),
        },
    }


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
    filas = [
        ("Dólar (divisa BNA)", s["dolar"]["valor"] or "", "Cotización del " + (s["dolar"]["fecha"] or "—")
         + (" · traído del BNA" if s["dolar"]["origen"] == "BNA" else " · cargado a mano")),
        ("Agencia a facturar", s["agencia"]["nombre"], ""),
        ("Fee (USD)", s["agencia"]["fee_usd"], ""),
        ("Cargas sociales (%)", s["agencia"]["cargas_pct"], "Se suman al final, sobre Tally y Serenos"),
    ]
    for i, (a, b, c) in enumerate(filas, start=3):
        ws.cell(i, 1, a).font = Font(bold=True)
        ws.cell(i, 2, b)
        ws.cell(i, 3, c)
    ws["A8"] = "Los pasos 3 a 10 se suman a esta planilla a medida que se arman en el sistema."
    ws["A8"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A8:C8")
    ws.column_dimensions["A"].width = 26
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
