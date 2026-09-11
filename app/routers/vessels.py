"""Legajos de barcos propios: ID persistente, historial y reportes
operativos (Berthing / Commenced Loading / Loading Shifts / Sailed)."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..eml import build_eml, safe_filename
from ..models import User, VesselCall, VesselCargo, VesselFile, VesselReport, VESSEL_REPORT_TYPES
from ..reports import _parse_qty, build_shift_report, build_vessel_status_report, status_template
from ..service import CC_KEY, DEFAULT_CC, get_setting, split_emails
from ..templating import templates

router = APIRouter()


def _prior_shift_totals(db: Session, vessel_file_id: int, cargo_id: int) -> tuple[float, dict[str, float]]:
    """Suma lo cargado en Loading Shifts anteriores de esta misma mercaderia
    (para "Total loaded" y el breakdown acumulado por bodega)."""
    total = 0.0
    holds: dict[str, float] = {}
    rows = db.scalars(
        select(VesselReport).where(
            VesselReport.vessel_file_id == vessel_file_id,
            VesselReport.report_types == "LOADING_SHIFTS",
        )
    )
    for r in rows:
        try:
            data = json.loads(r.shift_data or "{}")
        except ValueError:
            continue
        if data.get("cargo_id") != cargo_id:
            continue
        for label, qty in data.get("holds") or []:
            qty = float(qty)
            total += qty
            holds[label] = holds.get(label, 0.0) + qty
    return total, holds


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
            "cargos": vf.cargos,
        },
    )


@router.get("/barcos/{file_id}/plantilla")
def report_template(
    file_id: int, request: Request,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    vf = db.get(VesselFile, file_id)
    if not vf:
        return {"template": ""}
    tipos = [t for t in request.query_params.getlist("tipos") if t in dict(VESSEL_REPORT_TYPES)]
    event_at = request.query_params.get("event_at", "")
    live_call = db.scalar(
        select(VesselCall)
        .where(VesselCall.vessel_name == vf.vessel_name, VesselCall.terminal_id == vf.terminal_id)
        .order_by(VesselCall.id.desc())
    )
    operation = live_call.operation if live_call else "Load"
    return {"template": status_template(vf, tipos, event_at, operation)}


@router.post("/barcos/{file_id}/cargos")
def create_cargo(
    file_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
    grade: str = Form(...), stowage_plan: str = Form("0"),
):
    vf = db.get(VesselFile, file_id)
    if vf and grade.strip():
        db.add(
            VesselCargo(
                vessel_file_id=vf.id, grade=grade.strip(),
                stowage_plan=_parse_qty(stowage_plan), sort_order=len(vf.cargos),
            )
        )
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}#reporte", status_code=302)


@router.post("/barcos/{file_id}/cargos/{cargo_id}")
def update_cargo(
    file_id: int, cargo_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
    grade: str = Form(...), stowage_plan: str = Form("0"),
):
    cargo = db.get(VesselCargo, cargo_id)
    if cargo and cargo.vessel_file_id == file_id:
        cargo.grade = grade.strip()
        cargo.stowage_plan = _parse_qty(stowage_plan)
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}#reporte", status_code=302)


@router.post("/barcos/{file_id}/cargos/{cargo_id}/borrar")
def delete_cargo(
    file_id: int, cargo_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    cargo = db.get(VesselCargo, cargo_id)
    if cargo and cargo.vessel_file_id == file_id:
        db.delete(cargo)
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}#reporte", status_code=302)


@router.post("/barcos/{file_id}/statement")
def save_statement_of_facts(
    file_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
    statement_of_facts: str = Form(""),
):
    vf = db.get(VesselFile, file_id)
    if vf:
        vf.statement_of_facts = statement_of_facts.strip()
        db.commit()
    return RedirectResponse(f"/barcos/{file_id}#reporte", status_code=302)


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
    sof = vf.statement_of_facts if form.get("include_sof") == "on" else ""

    if tipos == ["LOADING_SHIFTS"]:
        cargo_id = int(form.get("cargo_id") or 0)
        cargo = db.get(VesselCargo, cargo_id)
        if not cargo or cargo.vessel_file_id != vf.id:
            return RedirectResponse(f"/barcos/{file_id}#reporte", status_code=302)

        labels = form.getlist("hold_label")
        qtys = form.getlist("hold_qty")
        holds = [
            (lbl.strip(), _parse_qty(qty))
            for lbl, qty in zip(labels, qtys)
            if lbl.strip() and _parse_qty(qty) > 0
        ]
        prior_total, prior_holds = _prior_shift_totals(db, vf.id, cargo.id)
        shift = {
            "cargo_id": cargo.id,
            "cargo_grade": cargo.grade,
            "stowage_plan": cargo.stowage_plan,
            "date": event_at,
            "time_from": str(form.get("shift_from", "")).strip(),
            "time_to": str(form.get("shift_to", "")).strip(),
            "gangs_text": str(form.get("gangs_text", "")).strip(),
            "greeting": str(form.get("greeting", "")).strip() or "Good day",
            "holds": holds,
            "prior_total": prior_total,
            "prior_holds": prior_holds,
            "delays": str(form.get("delays", "")).strip(),
            "prospect": str(form.get("prospect", "")).strip(),
            "include_breakdown": form.get("include_breakdown") == "on",
        }
        clients = vf.recipient_clients() or [None]
        cc_setting = split_emails(get_setting(db, CC_KEY, DEFAULT_CC))
        for i, client in enumerate(clients):
            report = build_shift_report(vf, client, shift, notes, statement_of_facts=sof)
            cc_emails = [e for e in cc_setting if e not in report.to_emails]
            db.add(
                VesselReport(
                    vessel_file_id=vf.id,
                    report_types="LOADING_SHIFTS",
                    event_at=event_at,
                    figure=figure,
                    notes=notes,
                    # el total acumulado solo se cuenta una vez por turno --
                    # si hay varios clientes, solo el primer mail guarda el
                    # shift_data "real" (los demas quedan vacios)
                    shift_data=json.dumps(shift) if i == 0 else "",
                    subject=report.subject,
                    text_body=report.text_body,
                    html_body=report.html_body,
                    to_emails=", ".join(report.to_emails),
                    cc_emails=", ".join(cc_emails),
                    sent_by=user.username,
                )
            )
        db.commit()
    elif tipos:
        live_call = db.scalar(
            select(VesselCall)
            .where(VesselCall.vessel_name == vf.vessel_name, VesselCall.terminal_id == vf.terminal_id)
            .order_by(VesselCall.id.desc())
        )
        operation = live_call.operation if live_call else "Load"
        clients = vf.recipient_clients() or [None]
        cc_setting = split_emails(get_setting(db, CC_KEY, DEFAULT_CC))
        for client in clients:
            report = build_vessel_status_report(
                vf, client, tipos, event_at, figure, notes, operation=operation, statement_of_facts=sof,
            )
            cc_emails = [e for e in cc_setting if e not in report.to_emails]
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
