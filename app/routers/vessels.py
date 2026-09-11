"""Legajos de barcos propios: ID persistente, historial y reportes
operativos (Berthing / Commenced Loading / Loading Shifts / Sailed)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..eml import build_eml, safe_filename
from ..models import User, VesselCall, VesselFile, VesselReport, VESSEL_REPORT_TYPES
from ..reports import build_vessel_status_report
from ..service import CC_KEY, DEFAULT_CC, get_setting, split_emails
from ..templating import templates

router = APIRouter()


@router.get("/barcos", response_class=HTMLResponse)
def vessel_files_page(
    request: Request, estado: str = "open",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    stmt = select(VesselFile).order_by(VesselFile.id.desc())
    if estado in ("open", "closed"):
        stmt = stmt.where(VesselFile.status == estado)
    files = list(db.scalars(stmt))
    counts = {
        row[0]: row[1]
        for row in db.execute(select(VesselFile.status, func.count()).group_by(VesselFile.status))
    }
    counts.setdefault("open", 0)
    counts.setdefault("closed", 0)
    return templates.TemplateResponse(
        request, "vessels/list.html",
        {"user": user, "files": files, "estado": estado, "counts": counts},
    )


@router.get("/barcos/{file_id}", response_class=HTMLResponse)
def vessel_file_page(
    file_id: int, request: Request,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    vf = db.get(VesselFile, file_id)
    if not vf:
        return RedirectResponse("/barcos", status_code=302)
    live_call = db.scalar(
        select(VesselCall)
        .where(VesselCall.vessel_name == vf.vessel_name, VesselCall.terminal_id == vf.terminal_id)
        .order_by(VesselCall.id.desc())
    )
    return templates.TemplateResponse(
        request, "vessels/detail.html",
        {
            "user": user,
            "vf": vf,
            "live_call": live_call,
            "report_types": VESSEL_REPORT_TYPES,
            "type_labels": dict(VESSEL_REPORT_TYPES),
            "clients": vf.recipient_clients(),
        },
    )


@router.post("/barcos/{file_id}/reportes")
async def create_vessel_report(
    file_id: int, request: Request,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    vf = db.get(VesselFile, file_id)
    if not vf:
        return RedirectResponse("/barcos", status_code=302)

    form = await request.form()
    tipos = [t for t in form.getlist("tipos") if t in dict(VESSEL_REPORT_TYPES)]
    event_at = str(form.get("event_at", "")).strip()
    figure = str(form.get("figure", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if tipos:
        live_call = db.scalar(
            select(VesselCall)
            .where(VesselCall.vessel_name == vf.vessel_name, VesselCall.terminal_id == vf.terminal_id)
            .order_by(VesselCall.id.desc())
        )
        operation = live_call.operation if live_call else "Load"
        report = build_vessel_status_report(vf, tipos, event_at, figure, notes, operation=operation)
        cc_emails = [e for e in split_emails(get_setting(db, CC_KEY, DEFAULT_CC)) if e not in report.to_emails]
        db.add(
            VesselReport(
                vessel_file_id=vf.id,
                report_types=",".join(tipos),
                event_at=event_at,
                figure=figure,
                notes=notes,
                subject=report.subject,
                text_body=report.text_body,
                html_body=report.html_body,
                to_emails=", ".join(report.to_emails),
                cc_emails=", ".join(cc_emails),
                sent_by=user.username,
            )
        )
        if "SAILED" in tipos:
            vf.status = "closed"
            vf.closed_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}#historial", status_code=302)


@router.post("/barcos/{file_id}/cerrar")
def close_vessel_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    vf = db.get(VesselFile, file_id)
    if vf:
        vf.status = "closed"
        vf.closed_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}", status_code=302)


@router.post("/barcos/{file_id}/reabrir")
def reopen_vessel_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    vf = db.get(VesselFile, file_id)
    if vf:
        vf.status = "open"
        vf.closed_at = None
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}", status_code=302)


@router.get("/barcos/{file_id}/reportes/{report_id}.eml")
def vessel_report_eml(
    file_id: int, report_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    r = db.get(VesselReport, report_id)
    if not r or r.vessel_file_id != file_id:
        return Response(status_code=404)
    # sin firma de la app: la pone Outlook (ver nota en reports.py sobre
    # por que se saco la firma de respaldo de los .eml)
    data = build_eml(
        subject=r.subject, to_emails=r.to_list, cc_emails=r.cc_list,
        html_body=r.html_body, text_body=r.text_body,
    )
    fname = safe_filename(r.subject) + ".eml"
    return Response(
        content=data, media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
