import io
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..eml import build_eml, safe_filename
from ..models import Client, ReportLog, User, VesselCall
from ..reports import BuiltReport, build_report
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


def _collect(db: Session, *, with_signature: bool = False):
    """Devuelve [(call, client, BuiltReport)] para todos los barcos propios
    con al menos un cliente destinatario.

    with_signature=False (default): sin firma de la app. Se usa al abrir en
    Outlook (Outlook agrega su propia firma) y al copiar el cuerpo.
    with_signature=True: agrega la firma de la app. Se usa solo para el .eml.
    """
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    term_by_id = {t.id: t for t in terminals}
    signature_html = get_setting(db, SIGNATURE_KEY, "") if with_signature else ""
    cc_emails = split_emails(get_setting(db, CC_KEY, DEFAULT_CC))

    out: list[tuple[VesselCall, Client, BuiltReport]] = []
    for call in calls:
        if not call.is_ours:
            continue
        terminal = term_by_id.get(call.terminal_id)
        if not terminal:
            continue
        term_calls = grouped.get(call.terminal_id, [])
        for client in call.recipient_clients():
            report = build_report(call, client, lineup, terminal, term_calls, signature_html)
            report.cc_emails = [e for e in cc_emails if e not in report.to_emails]
            out.append((call, client, report))
    return lineup, out


@router.get("/reports")
def reports_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup, rows = _collect(db)
    items = [
        {
            "call_id": call.id,
            "client_id": client.id,
            "vessel": call.vessel_name,
            "vessel_type": call.vessel_type,
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
    return templates.TemplateResponse(
        request,
        "reports/preview.html",
        {"user": user, "lineup": lineup, "items": items},
    )


@router.get("/reports/{call_id}/client/{client_id}.eml")
def one_eml(call_id: int, client_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup, rows = _collect(db, with_signature=True)
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
def all_zip(db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup, rows = _collect(db, with_signature=True)
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
        headers={"Content-Disposition": f'attachment; filename="Reportes {tag}.zip"'},
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
