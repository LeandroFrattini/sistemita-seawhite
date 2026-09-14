"""Armado del contenido de los reportes por barco/cliente.

Dos formatos:
  * EXCEL     -> mail HTML con la cabecera de texto + la tabla del bloque de
                 esa terminal (sin LOCAL/PRINCIPAL) pegada en el cuerpo + pie.
  * WBL_TEXT  -> todo texto: cabecera + Prospects (calculados de ETA/ETB/ETC
                 del barco de referencia) + line-up renglon por renglon + pie.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date as _date

from .config import settings
from .dates import fmt_dm, fmt_long, parse_date
from .models import VESSEL_REPORT_TYPES

ROADS_LABEL = "Bahia Blanca roads"
MONO = "font-family:'Courier New',monospace;font-size:16px;"


def _text_to_html(text: str) -> str:
    """Convierte texto plano a HTML que Outlook respeta: saltos de linea reales
    (<br>) y espacios consecutivos preservados (Outlook ignora white-space)."""
    out = html.escape(text).replace("\t", "    ")
    out = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group(0)), out)
    return out.replace("\n", "<br>")

MAIL_COLS = [
    ("__TERMINAL__", "vessel_name"),
    ("Vessel type", "vessel_type"),
    ("IMO", "imo"),
    ("ETA", "eta"),
    ("ETB", "etb"),
    ("ETC", "etc"),
    ("Operation", "operation"),
    ("Quantity", "quantity"),
    ("GRADE", "grade"),
    ("SHIPPER", "shipper"),
    ("DESTINATION", "destination"),
]


def vessel_prefix(vessel_type: str) -> str:
    return "MT" if (vessel_type or "").strip().lower() == "tanker" else "MV"


@dataclass
class BuiltReport:
    subject: str
    to_name: str
    to_emails: list[str]
    report_format: str
    html_body: str
    text_body: str
    vessel_name: str
    client_name: str
    cc_emails: list[str] = field(default_factory=list)


def build_subject(call, lineup) -> str:
    pfx = vessel_prefix(call.vessel_type)
    date_tag = (lineup.lineup_date or "").replace("/", ".")
    return f"{pfx} {call.vessel_name.upper()} - LINE UP {date_tag}"


# --------------------------------------------------------------------------- #
# Formato EXCEL (mail HTML con tabla)
# --------------------------------------------------------------------------- #
def _excel_header_text(call, client, lineup) -> str:
    pfx = vessel_prefix(call.vessel_type)
    date_tag = (lineup.lineup_date or "").replace("/", ".")
    return (
        f"TO {client.display_to.upper()}\n"
        f"FM {settings.mail_from_name}\n\n"
        f"REF {pfx} {call.vessel_name.upper()}\n\n"
        f"{date_tag}\n\n"
        f"GOOD DAY, PLS NOTE BELOW TODAY´S LINE UP:"
    )


def _excel_table_html(terminal, term_calls) -> str:
    # <p style="margin:0"> en cada celda: sin eso Outlook agrega ~8pt de espacio
    # despues de cada parrafo y las filas salen altas.
    cell_css = "margin:0;line-height:1.15;mso-line-height-rule:exactly;"

    head_cells = "".join(
        f'<th style="border:1px solid #7f9f6a;padding:1px 8px;text-align:left;'
        f'background:#c6e0b4;">'
        f'<p style="{cell_css}font-weight:bold;">'
        f"{html.escape(terminal.code if h == '__TERMINAL__' else h)}</p></th>"
        for h, _ in MAIL_COLS
    )
    body_rows = []
    for call in term_calls:
        tds = []
        for h, attr in MAIL_COLS:
            val = "" if getattr(call, attr, "") is None else str(getattr(call, attr, ""))
            tds.append(
                f'<td style="border:1px solid #cfcfcf;padding:1px 8px;white-space:nowrap;">'
                f'<p style="{cell_css}">{html.escape(val)}</p></td>'
            )
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        '<table cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse;font-family:\'Courier New\','
        "monospace;font-size:15px;margin:10px 0;\">"
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def _excel_table_text(terminal, term_calls) -> str:
    headers = [terminal.code if h == "__TERMINAL__" else h for h, _ in MAIL_COLS]
    rows = [headers]
    for call in term_calls:
        rows.append([str(getattr(call, attr, "") or "") for _, attr in MAIL_COLS])
    widths = [max(len(r[i]) for r in rows) for i in range(len(headers))]
    return "\n".join("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows)


def _wrap_body(inner_html: str, signature_html: str = "") -> str:
    """Envuelve todo el reporte en UN solo bloque para que Outlook no meta
    la firma en el medio. Si hay firma configurada, se agrega al final."""
    sig = f'<div style="margin-top:14px;">{signature_html}</div>' if signature_html.strip() else ""
    return (
        f'<div style="{MONO}">'
        f"{inner_html}"
        "<div><br></div>"
        f"{sig}</div>"
    )


def build_excel_report(call, client, lineup, terminal, term_calls, signature_html: str = "") -> BuiltReport:
    header = _excel_header_text(call, client, lineup)
    footer = settings.report_footer
    html_body = _wrap_body(
        f"<div>{_text_to_html(header)}</div>"
        "<div><br></div>"
        f"{_excel_table_html(terminal, term_calls)}"
        "<div><br></div>"
        f"<div>{_text_to_html(footer)}</div>",
        signature_html,
    )
    text_body = f"{header}\n\n{_excel_table_text(terminal, term_calls)}\n\n{footer}"
    return BuiltReport(
        subject=build_subject(call, lineup),
        to_name=client.display_to,
        to_emails=client.email_list,
        report_format="EXCEL",
        html_body=html_body,
        text_body=text_body,
        vessel_name=call.vessel_name,
        client_name=client.name,
    )


# --------------------------------------------------------------------------- #
# Formato WBL (todo texto)
# --------------------------------------------------------------------------- #
def _prospects_block(call, terminal) -> str:
    berth = terminal.berth_label or terminal.code
    lines: list[str] = []

    eta_d = parse_date(call.eta)
    if eta_d:
        lines.append(f"{fmt_long(eta_d)} – ETA at {ROADS_LABEL}")
    elif call.eta.strip():
        lines.append(f"{call.eta.strip()} – ETA at {ROADS_LABEL}")

    etb_d = parse_date(call.etb)
    if etb_d:
        lines.append(f"{fmt_long(etb_d)} – ETB {berth}")
    elif call.etb.strip():
        lines.append(f"{call.etb.strip()} – ETB {berth}")

    etc_d = parse_date(call.etc)
    if etc_d:
        lines.append(f"{fmt_long(etc_d)} – ETC/S {berth}")
    elif call.etc.strip():
        lines.append(f"{call.etc.strip()} – ETC/S {berth}")

    return "Prospects:\n" + "\n".join(lines)


def _wbl_eta_col(call) -> str:
    d = parse_date(call.eta)
    if d:
        return f"Eta {fmt_dm(d)}"
    return call.eta.strip()


def _wbl_etb_col(call) -> str:
    if call.etb.strip().lower() == "alongside":
        return "Alongside"
    d = parse_date(call.etb)
    if d:
        return f"Etb {fmt_dm(d)}"
    return call.etb.strip()


def _wbl_etc_col(call) -> str:
    d = parse_date(call.etc)
    return f"Ets {fmt_dm(d)}" if d else (f"Ets {call.etc.strip()}" if call.etc.strip() else "")


def _wbl_lineup_block(terminal, term_calls) -> str:
    berth = terminal.berth_label or terminal.code
    names = [c.vessel_name for c in term_calls]
    eta_cols = [_wbl_eta_col(c) for c in term_calls]
    qty_cols = [f"{c.quantity} {c.grade}".strip() for c in term_calls]
    name_w = max((len(n) for n in names), default=10) + 2
    eta_w = max((len(e) for e in eta_cols), default=8)
    qty_w = max((len(q) for q in qty_cols), default=8)

    rows = []
    for c, eta_c, qty_c in zip(term_calls, eta_cols, qty_cols):
        rows.append(
            f"{c.vessel_name.ljust(name_w)}- {eta_c.ljust(eta_w)} - "
            f"{qty_c.ljust(qty_w)} - {_wbl_etb_col(c)} {_wbl_etc_col(c)}".rstrip()
        )
    return f"Line up at {berth} goes:\n\n" + "\n".join(rows)


def build_wbl_report(call, client, lineup, terminal, term_calls, signature_html: str = "") -> BuiltReport:
    pfx = vessel_prefix(call.vessel_type).capitalize()  # "Mv" / "Mt"
    date_tag = (lineup.lineup_date or "").replace("/", ".")
    from_name = settings.mail_from_name.title()

    text_body = (
        f"To {client.display_to}\n"
        f"Fm {from_name}\n\n"
        f"Ref {pfx} {call.vessel_name}\n\n"
        f"{date_tag}\n\n"
        f"Good day, pls note line up:\n\n"
        f"{_prospects_block(call, terminal)}\n\n\n"
        f"{_wbl_lineup_block(terminal, term_calls)}\n\n\n"
        f"{settings.report_footer}"
    )
    html_body = _wrap_body(
        f'<div style="line-height:1.35;">{_text_to_html(text_body)}</div>',
        signature_html,
    )
    return BuiltReport(
        subject=build_subject(call, lineup),
        to_name=client.display_to,
        to_emails=client.email_list,
        report_format="WBL_TEXT",
        html_body=html_body,
        text_body=text_body,
        vessel_name=call.vessel_name,
        client_name=client.name,
    )


def build_report(call, client, lineup, terminal, term_calls, signature_html: str = "") -> BuiltReport:
    if client.report_format == "WBL_TEXT":
        return build_wbl_report(call, client, lineup, terminal, term_calls, signature_html)
    return build_excel_report(call, client, lineup, terminal, term_calls, signature_html)


# --------------------------------------------------------------------------- #
# Formato FLAMMABLE (texto monoespaciado, agrupado por muelle)
# --------------------------------------------------------------------------- #
FLAMMABLE_FOOTER = (
    "ALL BERTH ASSIGNMENTS ARE SUBJECT TO CONFIRMATION AND MAY VARY "
    "DEPENDING ON THE DECISION OF THE SHIPPERS/RECEIVERS."
)
FL_HEADERS = ["PIER / VESSEL", "ETA", "OPS (OPS – QTTS – PRODUCT – SHIPPER/RECEIVER)",
              "DESTINY", "ETB", "ETS"]


def _fl_eta(call) -> str:
    d = parse_date(call.eta)
    base = f"ETA {d.strftime('%d/%m')}" if d else (call.eta or "").strip().upper()
    if getattr(call, "second_call", False):
        base = f"{base} 2ND CALL".strip()
    return base


def _fl_etb(call) -> str:
    d = parse_date(call.etb)
    if d:
        return f"ETB {d.strftime('%d/%m')}"
    t = (call.etb or "").strip().upper()
    return t or "---------"


def _fl_ets(call) -> str:
    d = parse_date(call.etc)
    if d:
        return f"ETS {d.strftime('%d/%m')}"
    return (call.etc or "").strip().upper()


def _fl_ops(call) -> str:
    parts = [call.operation, call.quantity, call.grade, call.shipper]
    return " – ".join((p or "").strip() or "TBC" for p in parts)


def _fl_row(call) -> list[str]:
    return [call.vessel_name, _fl_eta(call), _fl_ops(call),
            (call.destination or "TBC"), _fl_etb(call), _fl_ets(call)]


def flammable_table_text(piers: list[tuple]) -> str:
    """piers = [(terminal, [calls]), ...]  ->  bloque de texto con header comun."""
    all_rows = [_fl_row(c) for _, calls in piers for c in calls]
    widths = []
    for i, head in enumerate(FL_HEADERS):
        cells = [head] + [r[i] for r in all_rows]
        widths.append(max(len(x) for x in cells) + 3)

    def fmt(cells: list[str]) -> str:
        return "".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    out = [fmt(FL_HEADERS), ""]
    for term, calls in piers:
        title = term.code
        if term.status_note:
            title = f"{term.code}   ({term.status_note})"
        out.append(title)
        out.append("-" * 18)
        for c in calls:
            out.append(fmt(_fl_row(c)))
        out.append("")
    return "\n".join(out).rstrip()


def _flammable_wrap(text_body: str, signature_html: str = "") -> tuple[str, str]:
    html_body = _wrap_body(
        f'<div style="line-height:1.35;">{_text_to_html(text_body)}</div>', signature_html
    )
    return text_body, html_body


def build_flammable_full(lineup, piers: list[tuple]) -> tuple[str, str, str]:
    """Line-up completo (para la lista fija). Devuelve (subject, text, html)."""
    d = parse_date(lineup.lineup_date)
    title_date = d.strftime("%d.%m.%Y") if d else (lineup.lineup_date or "")
    subj_date = d.strftime("%d.%m.%y") if d else (lineup.lineup_date or "")
    text_body = (
        f"BAHIA BLANCA FLAMMABLE STATIONS LINE UP - {title_date}\n\n"
        f"GOOD DAY,\n\n"
        f"PLS FIND BELOW UPDATED LINE UPS:\n\n"
        f"+++\n\n"
        f"{flammable_table_text(piers)}\n\n"
        f"{FLAMMABLE_FOOTER}"
    )
    _, html_body = _flammable_wrap(text_body)
    return f"BAHIA BLANCA FLAMMABLE STATIONS LINE UP - {subj_date}", text_body, html_body


def build_flammable_report(call, client, lineup, terminal, term_calls, signature_html: str = "") -> BuiltReport:
    d = parse_date(lineup.lineup_date)
    date_tag = d.strftime("%d.%m.%y") if d else (lineup.lineup_date or "")
    pfx = vessel_prefix(call.vessel_type)
    text_body = (
        f"TO {client.display_to.upper()}\n"
        f"FM {settings.mail_from_name}\n\n"
        f"REF {pfx} {call.vessel_name.upper()}\n\n"
        f"{date_tag}\n\n"
        f"GOOD DAY,\n\n"
        f"PLS FIND BELOW UPDATED LINE UPS:\n\n"
        f"+++\n\n"
        f"{flammable_table_text([(terminal, term_calls)])}\n\n"
        f"{FLAMMABLE_FOOTER}"
    )
    _, html_body = _flammable_wrap(text_body, signature_html)
    return BuiltReport(
        subject=build_subject(call, lineup),
        to_name=client.display_to,
        to_emails=client.email_list,
        report_format="FLAMMABLE",
        html_body=html_body,
        text_body=text_body,
        vessel_name=call.vessel_name,
        client_name=client.name,
    )


# --------------------------------------------------------------------------- #
# Reportes operativos por legajo (Berthing / Commenced Loading / Loading
# Shifts / Sailed, combinables). Wording de Berthing, Commenced Loading y
# Loading Shifts calcado de los modelos reales que paso Leandro (MV YM
# QUEST, MV SUBRA, MV IONIC KIBOU, MV DISCOVERER). Sailed todavia no tiene
# modelo real -- queda con una apertura generica.
# --------------------------------------------------------------------------- #
PORT_LABEL = "BAHÍA BLANCA"
PORT_LABEL_TITLE = "Bahía Blanca"

_MONTHS_UP = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MONTHS_FULL = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _event_date_header(event_at: str) -> str:
    """'SEP 08TH, 2026' -- se intenta sacar la fecha de lo que se cargo en
    "Fecha y hora"; si no se puede parsear (por ej. si tiene la hora
    pegada), se usa la fecha de hoy."""
    d = parse_date(event_at) or _date.today()
    return f"{_MONTHS_UP[d.month - 1]} {d.day:02d}{_ordinal_suffix(d.day).upper()}, {d.year}"


def _parse_qty(raw) -> float:
    try:
        return float(str(raw).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _fmt_mt(value: float) -> str:
    return f"{value:,.3f}"


def _append_statement_of_facts(text_body: str, statement_of_facts: str) -> str:
    sof = (statement_of_facts or "").strip()
    if not sof:
        return text_body
    return text_body + "\n\n\nStatement of Facts:\n\n" + sof


def build_sof_text(entries: list) -> str:
    """Arma el Statement of Facts (formato calcado de MV DOVER: "25/1442 -
    texto", agrupado por mes) a partir de las entradas cargadas una por una
    en el popup del legajo. Las entradas ya vienen ordenadas por fecha/hora
    (ver VesselFile.sof_entries)."""
    lines: list[str] = []
    current_month: tuple[int, int] | None = None
    for e in entries:
        d = parse_date(e.event_date)
        if d and (d.year, d.month) != current_month:
            current_month = (d.year, d.month)
            if lines:
                lines.append("")
            lines.append(f"{_MONTHS_FULL[d.month - 1]}, {d.year}")
        day = f"{d.day:02d}" if d else (e.event_date or "")
        tf = (e.time_from or "").replace(":", "")
        tt = (e.time_to or "").replace(":", "")
        time_part = f"{day}/{tf}" if tf else day
        if tt:
            time_part += f"/{tt}"
        lines.append(f"{time_part} - {e.text}" if time_part else e.text)
    return "\n".join(lines)


def _wbl_hold_label(label: str) -> str:
    """"H2" -> "Hold 2" (formato WBL); si no matchea el patron, se deja tal cual."""
    m = re.match(r"^[Hh](\d+)$", label.strip())
    return f"Hold {m.group(1)}" if m else label


def build_shift_report(
    vf, client, shift: dict, notes: str, signature_html: str = "", statement_of_facts: str = "",
) -> BuiltReport:
    """Loading/Discharging Shift -- formato calcado de MV IONIC KIBOU (Atlas)
    y MV DISCOVERER (Oceanway, con breakdown por bodega), o el de MV DOVER
    si el cliente es WBL (report_format WBL_TEXT). Un mail por cliente -- si
    el barco tiene varias agencias, se llama una vez por cada una, cada
    quien con su propio wording."""
    pfx_slash = vessel_prefix(vf.vessel_type)
    pfx_slash = pfx_slash[0] + "/" + pfx_slash[1]
    terminal_name = (vf.terminal.name if vf.terminal else vf.terminal_code) or "TERMINAL"
    terminal_name = terminal_name.upper()

    to_name = client.display_to.upper() if client else "(SIN CLIENTE)"
    to_emails = client.email_list if client else []
    is_wbl = bool(client and client.report_format == "WBL_TEXT")

    d = parse_date(shift.get("date", "")) or _date.today()
    date_txt = f"{_MONTHS_FULL[d.month - 1]} {d.day}{_ordinal_suffix(d.day)}"
    grade = (shift.get("cargo_grade") or "").strip() or "(SIN MERCADERIA CARGADA)"
    holds: list[tuple[str, float]] = shift.get("holds") or []
    shift_total = sum(q for _, q in holds)
    prior_total = float(shift.get("prior_total") or 0)
    total_loaded = prior_total + shift_total
    stowage_plan = float(shift.get("stowage_plan") or 0)
    balance = stowage_plan - total_loaded
    gangs_text = shift.get("gangs_text") or "gangs appointed"
    time_from = shift.get("time_from", "")
    time_to = shift.get("time_to", "")

    if is_wbl:
        tf_nc = time_from.replace(":", "")
        tt_nc = time_to.replace(":", "")
        lines = [
            f"Dear All, {shift.get('greeting') or 'Good day'}",
            "Pls note",
            "",
            "",
            f"Loading report: Loading operations by {gangs_text} ({date_txt})",
            "",
            f"Cargo loaded shift {tf_nc}-{tt_nc} – Loading shift – {gangs_text}",
        ]
        for label, qty in holds:
            lines.append(f"{_wbl_hold_label(label)}: {_fmt_mt(qty)} mt {grade}")
        lines += [
            "",
            "",
            f"Ttl shift:\t{_fmt_mt(shift_total)} mt",
            f"Ttl on board:\t{_fmt_mt(total_loaded)} mt",
            f"Stowage plan:\t{_fmt_mt(stowage_plan)} mt (as per pre-stowage plan)",
            f"Balance to go:\t{_fmt_mt(balance)} mt",
            "",
            f"Delays: {(shift.get('delays') or 'NIL').strip()}",
        ]
        if (notes or "").strip():
            lines += ["", "Remarks:", notes.strip()]
        prospect = (shift.get("prospect") or "").strip()
        if prospect:
            lines += ["", "Prospects:", prospect]
        text_body = (
            f"TO {to_name}\n"
            f"FM {settings.mail_from_name}\n\n"
            f"Ref: {pfx_slash} {vf.vessel_name.upper()}\n"
            f"Berth: {terminal_name}\n\n"
            + "\n".join(lines)
        )
        subject = f"{pfx_slash} {vf.vessel_name.upper()} - {d.day:02d}/{tt_nc or tf_nc} Hrs"
    else:
        lines = [
            f"Dear all, {shift.get('greeting') or 'Good day'}",
            "Pls note,",
            "",
            f"Shift {date_txt} / {time_from} - {time_to} hrs ({gangs_text}):",
            "",
        ]
        for label, qty in holds:
            lines.append(f"{label}/\t{_fmt_mt(qty)} MT – {grade}")
        lines += [
            "",
            f"Total shift =\t{_fmt_mt(shift_total)} MT – {grade}",
            f"Total loaded =\t{_fmt_mt(total_loaded)} MT – {grade}",
            f"Stowage Plan =\t{_fmt_mt(stowage_plan)} MT – {grade} (As per declared by master)",
            f"Balance to go =\t{_fmt_mt(balance)} MT – {grade}",
            "",
            f"Delays: {(shift.get('delays') or '-').strip()}",
        ]
        if (notes or "").strip():
            lines += ["", "Remarks:", notes.strip()]
        if shift.get("include_breakdown"):
            prior_holds: dict[str, float] = dict(shift.get("prior_holds") or {})
            cumulative: dict[str, float] = dict(prior_holds)
            for label, qty in holds:
                cumulative[label] = cumulative.get(label, 0.0) + qty
            lines += ["", "Breakdown by Holds:"]
            for label, qty in cumulative.items():
                lines.append(f"{label} = {_fmt_mt(qty)} Mt")
        prospect = (shift.get("prospect") or "").strip()
        if prospect:
            lines += ["", "====================", "Tentative prospect (AGW WP UCE):", prospect]
        text_body = (
            f"TO {to_name}\n"
            f"FM {settings.mail_from_name}\n\n"
            f"Ref: {pfx_slash} {vf.vessel_name.upper()}\n"
            f"Port: {PORT_LABEL_TITLE}\n"
            f"Terminal: {terminal_name}\n\n"
            + "\n".join(lines)
        )
        subject = f"{pfx_slash} {vf.vessel_name.upper()} - LOADING SHIFT {date_txt.upper()}"

    text_body = _append_statement_of_facts(text_body, statement_of_facts)
    html_body = _wrap_body(
        f'<div style="line-height:1.35;">{_text_to_html(text_body)}</div>', signature_html
    )
    return BuiltReport(
        subject=subject,
        to_name=to_name,
        to_emails=to_emails,
        report_format="VESSEL_STATUS",
        html_body=html_body,
        text_body=text_body,
        vessel_name=vf.vessel_name,
        client_name=to_name,
    )


def _operation_word(operation: str) -> str:
    return "DISCHARGING" if (operation or "").strip().lower().startswith("disch") else "LOADING"


def _status_phrase(types: set[str], op_word: str, labels: dict[str, str]) -> str:
    """Frase corta usada tanto en el asunto como en el cuerpo ('BERTHED AND
    COMMENCED LOADING', 'BERTHED', 'SAILED', ...)."""
    has_berth = "BERTHING" in types
    has_load = "COMMENCED_LOADING" in types
    if has_berth and has_load:
        return f"BERTHED AND COMMENCED {op_word}"
    if has_berth:
        return "BERTHED"
    if has_load:
        return f"COMMENCED {op_word}"
    if "SAILED" in types:
        return "SAILED"
    if "LOADING_SHIFTS" in types:
        return "SHIFT REPORT"
    return " + ".join(labels.get(t, t) for t in types).upper() or "REPORT"


def status_template(
    vf, report_types: list[str], event_at: str, operation: str = "Load",
    is_wbl: bool = False, greeting: str = "good day",
) -> str:
    """Plantilla prearmada (apertura + fecha) para que se cargue en el cuadro
    de texto del formulario y se pueda ir editando de a una linea, en vez de
    completar campos sueltos a ciegas.

    Para WBL (calcado de MV BAI GUAN / MV ANAHITA) no hay una frase de
    apertura tipo "PLS NOTE BERTHED..." ni fecha aparte -- se va directo a
    "Pls note" y el detalle es el propio Statement of Facts (agregalo con
    el boton "+ Agregar evento" y tildá "Incluir Statement of Facts")."""
    if is_wbl:
        return f"Dear All, {greeting}\nPls note\n"

    labels = dict(VESSEL_REPORT_TYPES)
    types = set(report_types)
    op_word = _operation_word(operation)
    terminal_name = (vf.terminal.name if vf.terminal else vf.terminal_code) or ""
    terminal_name = terminal_name.upper() or "TERMINAL"

    phrase = _status_phrase(types, op_word, labels)
    if types & {"BERTHING", "COMMENCED_LOADING"}:
        opener = f"PLS NOTE {phrase} OPS AT {terminal_name} TERMINAL"
    elif "SAILED" in types:
        opener = f"PLS NOTE VSL SAILED FROM {terminal_name} TERMINAL"
    elif "LOADING_SHIFTS" in types:
        opener = "PLS NOTE FOLLOWING SHIFT REPORT:"
    else:
        opener = "PLS NOTE:"
    return f"DEAR ALL, GOOD DAY\n{opener}\n\n{_event_date_header(event_at)}\n"


def status_header(vf, client) -> tuple[str, bool]:
    """Header TO/FM/REF + (PORT/TERMINAL o Berth), armado distinto segun el
    formato del cliente (WBL_TEXT vs EXCEL) -- lo usa tanto el reporte real
    como la vista previa de arriba del cuadro de Detalle. Devuelve
    (header_sin_salto_final, is_wbl)."""
    pfx = vessel_prefix(vf.vessel_type)
    terminal_name = (vf.terminal.name if vf.terminal else vf.terminal_code) or ""
    terminal_name = terminal_name.upper() or "TERMINAL"
    to_name = client.display_to.upper() if client else "(SIN CLIENTE)"
    is_wbl = bool(client and client.report_format == "WBL_TEXT")
    if is_wbl:
        pfx_slash = pfx[0] + "/" + pfx[1]
        header = (
            f"TO {to_name}\n"
            f"FM {settings.mail_from_name}\n\n"
            f"Ref: {pfx_slash} {vf.vessel_name.upper()}\n"
            f"Berth: {terminal_name}"
        )
    else:
        header = (
            f"TO: {to_name}\n"
            f"FM: {settings.mail_from_name}\n"
            f"REF: {pfx} {vf.vessel_name.upper()}\n\n"
            f"PORT: {PORT_LABEL}\n"
            f"TERMINAL: {terminal_name}"
        )
    return header, is_wbl


def build_vessel_status_report(
    vf, client, report_types: list[str], event_at: str, figure: str, notes: str,
    signature_html: str = "", operation: str = "Load", statement_of_facts: str = "",
) -> BuiltReport:
    """Un mail por cliente -- si el barco tiene varias agencias, se llama una
    vez por cada una (mismo patron que el line-up diario).

    "notes" es el cuerpo completo tal cual quedo en el cuadro de texto del
    formulario (normalmente la plantilla de status_template() + los cambios
    que se le hicieron a mano); si vino vacio se usa la plantilla sola."""
    labels = dict(VESSEL_REPORT_TYPES)
    types = set(report_types)
    phrase = _status_phrase(types, _operation_word(operation), labels)

    to_name = client.display_to.upper() if client else "(SIN CLIENTE)"
    to_emails = client.email_list if client else []
    header, is_wbl = status_header(vf, client)
    pfx = vessel_prefix(vf.vessel_type)
    terminal_name = (vf.terminal.name if vf.terminal else vf.terminal_code) or ""
    terminal_name = terminal_name.upper() or "TERMINAL"

    body = (notes or "").strip() or status_template(vf, report_types, event_at, operation, is_wbl=is_wbl)
    if (figure or "").strip():
        body += f"\n\nFIGURE: {figure.strip()}".upper()

    text_body = header + "\n\n" + body
    subject_suffix = "BERTH" if is_wbl else "TERMINAL"
    text_body = _append_statement_of_facts(text_body, statement_of_facts)
    html_body = _wrap_body(
        f'<div style="line-height:1.35;">{_text_to_html(text_body)}</div>', signature_html
    )
    if "SAILED" in types:
        subject_terminal = f" FROM {terminal_name} {subject_suffix}"
    elif types & {"BERTHING", "COMMENCED_LOADING"}:
        subject_terminal = f" AT {terminal_name} {subject_suffix}"
    else:
        subject_terminal = ""
    return BuiltReport(
        subject=f"{pfx} {vf.vessel_name.upper()} - {phrase}{subject_terminal}",
        to_name=to_name,
        to_emails=to_emails,
        report_format="VESSEL_STATUS",
        html_body=html_body,
        text_body=text_body,
        vessel_name=vf.vessel_name,
        client_name=to_name,
    )
