"""Legajos de barcos propios: ID persistente, historial y reportes
operativos (Berthing / Commenced Loading / Loading Shifts / Sailed)."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..dates import parse_date
from ..eml import build_eml, safe_filename
from ..models import (
    EventTemplate,
    SofEntry,
    User,
    VesselCall,
    VesselCargo,
    VesselFile,
    VesselReport,
    VESSEL_REPORT_TYPES,
)
from ..reports import _parse_qty, build_shift_report, build_sof_text, build_vessel_status_report, status_template
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


_STATUS_SHORT = {
    "BERTHING": "Berthed",
    "COMMENCED_LOADING": "Ldg Commenced",
    "LOADING_SHIFTS": "Loading Shift",
    "SAILED": "Sailed",
}


def _current_status(vf: VesselFile) -> tuple[str, datetime | None]:
    """Ultimo evento del legajo (los reportes ya vienen ordenados por fecha
    desc), para mostrar de un vistazo en el listado -- igual que la columna
    "Current Status" del sistema que paso Leandro de referencia."""
    if not vf.reports:
        return ("Sin reportes", None)
    last = vf.reports[0]
    label = " + ".join(_STATUS_SHORT.get(t, t) for t in last.type_list) or "Reporte"
    return (label, last.sent_at)


def _next_status(vf: VesselFile, live_call: VesselCall | None) -> str:
    if not live_call:
        return ""
    last_types = set(vf.reports[0].type_list) if vf.reports else set()
    if "SAILED" in last_types:
        return ""
    if last_types & {"BERTHING", "COMMENCED_LOADING", "LOADING_SHIFTS"}:
        return f"ETC {live_call.etc}" if live_call.etc else ""
    if live_call.etb:
        return f"ETB {live_call.etb}"
    if live_call.eta:
        return f"ETA {live_call.eta}"
    return ""


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

    rows = []
    for f in files:
        live_call = db.scalar(
            select(VesselCall)
            .where(VesselCall.vessel_name == f.vessel_name, VesselCall.terminal_id == f.terminal_id)
            .order_by(VesselCall.id.desc())
        )
        status_label, status_at = _current_status(f)
        rows.append({
            "vf": f,
            "status_label": status_label,
            "status_at": status_at,
            "next_status": _next_status(f, live_call),
            "operation": live_call.operation if live_call else "",
            "load_orders": f"{live_call.quantity} {live_call.grade}".strip() if live_call else "",
            "eta_sort": (
                (parse_date(live_call.etb) or parse_date(live_call.eta)) if live_call else None
            ),
        })

    # ordenados por ETB (o ETA si no hay ETB) estimado -- el que llega antes
    # arriba; los que no tienen fecha cargada quedan al final
    rows.sort(key=lambda r: (r["eta_sort"] is None, r["eta_sort"] or date.max))

    return templates.TemplateResponse(
        request, "vessels/list.html",
        {"user": user, "rows": rows, "estado": estado, "counts": counts},
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
    event_categories = [
        c for (c,) in db.execute(
            select(EventTemplate.category).distinct().order_by(EventTemplate.category)
        )
        if c
    ]
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
            "event_categories": event_categories,
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
    # si TODOS los destinatarios son WBL, se prearma directamente en ese
    # estilo (Statement of Facts en vez de "PLS NOTE..."); si hay una mezcla
    # de formatos se usa el generico -- el mail final igual sale bien para
    # cada cliente, esto es solo lo que se ve en el cuadro antes de editar
    recipients = vf.recipient_clients()
    is_wbl = bool(recipients) and all(c.report_format == "WBL_TEXT" for c in recipients)
    return {"template": status_template(vf, tipos, event_at, operation, is_wbl=is_wbl)}


@router.get("/api/eventos")
def search_event_templates(
    q: str = "", db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Biblioteca de frases reutilizables (Admin -> Eventos) para insertar en
    el Detalle / Statement of Facts sin tipear todo de cero."""
    stmt = select(EventTemplate).where(EventTemplate.active)
    q = q.strip()
    if q:
        stmt = stmt.where(EventTemplate.text.ilike(f"%{q}%"))
    stmt = stmt.order_by(EventTemplate.category, EventTemplate.text).limit(30)
    return [{"id": e.id, "category": e.category, "text": e.text} for e in db.scalars(stmt)]


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


def _sof_entry_json(e: SofEntry) -> dict:
    return {
        "id": e.id, "event_date": e.event_date, "time_from": e.time_from, "time_to": e.time_to,
        "category": e.category, "location": e.location, "text": e.text,
    }


@router.post("/barcos/{file_id}/sof")
def create_sof_entry(
    file_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
    event_date: str = Form(""), time_from: str = Form(""), time_to: str = Form(""),
    category: str = Form(""), location: str = Form(""), text: str = Form(...),
):
    vf = db.get(VesselFile, file_id)
    if not vf or not text.strip():
        return JSONResponse({"ok": False, "error": "falta el barco o el texto"}, status_code=400)
    e = SofEntry(
        vessel_file_id=vf.id, event_date=event_date.strip(), time_from=time_from.strip(),
        time_to=time_to.strip(), category=category.strip(), location=location.strip(),
        text=text.strip(), created_by=user.username,
    )
    db.add(e)
    db.commit()
    return {"ok": True, "entry": _sof_entry_json(e)}


@router.post("/barcos/{file_id}/sof/{entry_id}")
def update_sof_entry(
    file_id: int, entry_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
    event_date: str = Form(""), time_from: str = Form(""), time_to: str = Form(""),
    category: str = Form(""), location: str = Form(""), text: str = Form(...),
):
    e = db.get(SofEntry, entry_id)
    if not e or e.vessel_file_id != file_id:
        return JSONResponse({"ok": False, "error": "no encontrado"}, status_code=404)
    e.event_date = event_date.strip()
    e.time_from = time_from.strip()
    e.time_to = time_to.strip()
    e.category = category.strip()
    e.location = location.strip()
    e.text = text.strip()
    db.commit()
    return {"ok": True, "entry": _sof_entry_json(e)}


@router.post("/barcos/{file_id}/sof/{entry_id}/borrar")
def delete_sof_entry(
    file_id: int, entry_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    e = db.get(SofEntry, entry_id)
    if e and e.vessel_file_id == file_id:
        db.delete(e)
        db.commit()
    return {"ok": True}


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
    sof = build_sof_text(vf.sof_entries) if form.get("include_sof") == "on" else ""

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
        batch_id = uuid.uuid4().hex
        for i, client in enumerate(clients):
            report = build_shift_report(vf, client, shift, notes, statement_of_facts=sof)
            cc_emails = [e for e in cc_setting if e not in report.to_emails]
            db.add(
                VesselReport(
                    vessel_file_id=vf.id,
                    batch_id=batch_id,
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
        batch_id = uuid.uuid4().hex
        for client in clients:
            report = build_vessel_status_report(
                vf, client, tipos, event_at, figure, notes, operation=operation, statement_of_facts=sof,
            )
            cc_emails = [e for e in cc_setting if e not in report.to_emails]
            db.add(
                VesselReport(
                    vessel_file_id=vf.id,
                    batch_id=batch_id,
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


@router.post("/barcos/{file_id}/reportes/{report_id}/borrar")
def delete_vessel_report(
    file_id: int, report_id: int,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Borra un reporte cargado por error. Como un mismo "Generar reporte"
    arma un mail por cliente, borra TODOS los del mismo batch_id (son el
    mismo evento) -- asi no queda un destinatario con el mail viejo y los
    demas sin el. Si era un Loading Shift, el "Total loaded" / breakdown
    por bodega de los siguientes se recalcula solo."""
    r = db.get(VesselReport, report_id)
    if r and r.vessel_file_id == file_id:
        if r.batch_id:
            db.query(VesselReport).filter(
                VesselReport.vessel_file_id == file_id,
                VesselReport.batch_id == r.batch_id,
            ).delete()
        else:
            db.delete(r)
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
