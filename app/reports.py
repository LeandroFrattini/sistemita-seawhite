"""Armado del contenido de los reportes por barco/cliente.

Dos formatos:
  * EXCEL     -> mail HTML con la cabecera de texto + la tabla del bloque de
                 esa terminal (sin LOCAL/PRINCIPAL) pegada en el cuerpo + pie.
  * WBL_TEXT  -> todo texto: cabecera + Prospects (calculados de ETA/ETB/ETC
                 del barco de referencia) + line-up renglon por renglon + pie.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from .config import settings
from .dates import fmt_dm, fmt_long, parse_date

ROADS_LABEL = "Bahia Blanca roads"

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
    head_cells = "".join(
        f'<th style="border:1px solid #7f9f6a;padding:2px 8px;text-align:left;'
        f'background:#c6e0b4;font-weight:bold;">'
        f"{html.escape(terminal.code if h == '__TERMINAL__' else h)}</th>"
        for h, _ in MAIL_COLS
    )
    body_rows = []
    for call in term_calls:
        tds = []
        for h, attr in MAIL_COLS:
            val = "" if getattr(call, attr, "") is None else str(getattr(call, attr, ""))
            tds.append(
                f'<td style="border:1px solid #cfcfcf;padding:2px 8px;'
                f'white-space:nowrap;">{html.escape(val)}</td>'
            )
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    return (
        '<table style="border-collapse:collapse;font-family:\'Courier New\','
        "monospace;font-size:12px;margin:10px 0;\">"
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
        '<div style="font-family:\'Courier New\',monospace;font-size:13px;">'
        f"{inner_html}"
        "<div><br></div>"
        f"{sig}</div>"
    )


def build_excel_report(call, client, lineup, terminal, term_calls, signature_html: str = "") -> BuiltReport:
    header = _excel_header_text(call, client, lineup)
    footer = settings.report_footer
    html_body = _wrap_body(
        f'<div style="white-space:pre-wrap;">{html.escape(header)}</div>'
        f"{_excel_table_html(terminal, term_calls)}"
        f'<div style="white-space:pre-wrap;">{html.escape(footer)}</div>',
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
        f'<div style="white-space:pre-wrap;">{html.escape(text_body)}</div>',
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
