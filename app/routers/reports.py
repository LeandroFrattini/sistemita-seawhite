import io
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..eml import build_eml, safe_filename
from ..models import Client, ReportLog, User, VesselCall
from ..reports import BuiltReport, build_flammable_full, build_flammable_report, build_report
from ..service import (
    CC_KEY,
    DEFAULT_CC,
    SIGNATURE_KEY,
    active_terminals,
    calls_for_lineup,
    get_draft_lineup,
    get_setting,
    group_by_terminal,
    split_emails,
)
from ..templating import templates

router = APIRouter()

FLAMMABLE_LIST_KEY = "flammable_list_emails"


def _collect(db: Session, *, kind: str = "GRAIN", with_signature: bool = False):
    """[(call, client, BuiltReport)] para los barcos propios con destinatarios."""
    lineup = get_draft_lineup(db, kind)
    terminals = active_terminals(db, kind)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    term_by_id = {t.id: t for t in terminals}
    signature_html = get_setting(db, SIGNATURE_KEY, "") if with_signature else ""
    cc_emails = split_emails(get_setting(db, CC_KEY, DEFAULT_CC))
    builder = build_flammable_report if kind == "FLAMMABLE" else build_report

    out: list[tuple[VesselCall, Client, BuiltReport]] = []
    for call in calls:
        if not call.is_ours:
            continue
        terminal = term_by_id.get(call.terminal_id)
        if not terminal:
            continue
        term_calls = grouped.get(call.terminal_id, [])
        for client in call.recipient_clients():
            report = builder(call, client, lineup, terminal, term_calls, signature_html)
            report.cc_emails = [e for e in cc_emails if e not in report.to_emails]
            out.append((call, client, report))
    return lineup, out


def _flammable_full(db: Session, *, with_signature: bool = False):
    lineup = get_draft_lineup(db, "FLAMMABLE")
    terminals = active_terminals(db, "FLAMMABLE")
    grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
    piers = [(t, grouped.get(t.id, [])) for t in terminals]
    subject, text_body, html_body = build_flammable_full(lineup, piers)
    # La lista fija va en COPIA OCULTA (BCC) para no exponer las casillas
    # entre si. El TO va a la casilla propia (operations@seawhite...).
    bcc_emails = split_emails(get_setting(db, FLAMMABLE_LIST_KEY, ""))
    to_emails = split_emails(get_setting(db, CC_KEY, DEFAULT_CC)) or ["operations@seawhite.com.ar"]
    bcc_emails = [e for e in bcc_emails if e not in to_emails]
    return lineup, subject, text_body, html_body, to_emails, bcc_emails


@router.get("/reports")
def reports_page(request: Request, kind: str = "GRAIN", db: Session = Depends(get_db), user: User = Depends(current_user)):
    kind = "FLAMMABLE" if kind.upper() == "FLAMMABLE" else "GRAIN"
    lineup, rows = _collect(db, kind=kind)
    items = [
        {
            "call_id": call.id,
            "client_id": client.id,
            "vessel": call.vessel_name,
            "client": client.name,
            "to_name": report.to_name,
            "format": report.report_format,
            "subject": report.subject,
            "emails": report.to_emails,
            "cc_emails": report.cc_emails,
            "missing_email": not report.to_emails,
            "html_body": report.html_body,
            "text_body": report.text_body,
        }
        for call, client, report in rows
    ]
    ctx = {"user": user, "lineup": lineup, "items": items, "kind": kind}
    if kind == "FLAMMABLE":
        _, subject, text_body, html_body, to_emails, bcc_emails = _flammable_full(db)
        ctx["full"] = {
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
            "to": "; ".join(to_emails),
            "bcc": "; ".join(bcc_emails),
            "missing_list": not bcc_emails,
        }
    return templates.TemplateResponse(request, "reports/preview.html", ctx)


@router.get("/reports/flammable-full.eml")
def flammable_full_eml(db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup, subject, text_body, html_body, to_emails, bcc_emails = _flammable_full(db, with_signature=True)
    data = build_eml(
        subject=subject, to_emails=to_emails, bcc_emails=bcc_emails,
        html_body=html_body, text_body=text_body,
    )
    return Response(
        content=data,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(subject)}.eml"'},
    )


@router.get("/reports/{call_id}/client/{client_id}.eml")
def one_eml(call_id: int, client_id: int, kind: str = "GRAIN", db: Session = Depends(get_db), user: User = Depends(current_user)):
    kind = "FLAMMABLE" if kind.upper() == "FLAMMABLE" else "GRAIN"
    lineup, rows = _collect(db, kind=kind, with_signature=True)
    for call, client, report in rows:
        if call.id == call_id and client.id == client_id:
            data = build_eml(
                subject=report.subject,
                to_emails=report.to_emails,
                cc_emails=report.cc_emails,
                html_body=report.html_body,
                text_body=report.text_body,
            )
            fname = safe_filename(f"{report.subject} - {client.name}") + ".eml"
            _log(db, user, lineup, report)
            return Response(
                content=data,
                media_type="message/rfc822",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'},
            )
    return JSONResponse({"error": "reporte no encontrado"}, status_code=404)


@router.get("/reports/all.zip")
def all_zip(kind: str = "GRAIN", db: Session = Depends(get_db), user: User = Depends(current_user)):
    kind = "FLAMMABLE" if kind.upper() == "FLAMMABLE" else "GRAIN"
    lineup, rows = _collect(db, kind=kind, with_signature=True)
    if not rows:
        return JSONResponse({"error": "no hay reportes para generar"}, status_code=400)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for call, client, report in rows:
            data = build_eml(
                subject=report.subject,
                to_emails=report.to_emails,
                cc_emails=report.cc_emails,
                html_body=report.html_body,
                text_body=report.text_body,
            )
            fname = safe_filename(f"{report.subject} - {client.name}") + ".eml"
            zf.writestr(fname, data)
            _log(db, user, lineup, report)
    buf.seek(0)
    tag = (lineup.lineup_date or "").replace("/", ".")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Reportes {kind} {tag}.zip"'},
    )


def _log(db: Session, user: User, lineup, report: BuiltReport) -> None:
    db.add(
        ReportLog(
            generated_by=user.username,
            lineup_date=lineup.lineup_date,
            vessel_name=report.vessel_name,
            client_name=report.client_name,
            to_emails=", ".join(report.to_emails),
            report_format=report.report_format,
            status="generated",
        )
    )
    db.commit()
