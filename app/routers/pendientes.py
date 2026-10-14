"""Pendientes por barco: lista de cosas a pedir / tachar de cada legajo abierto, que ve todo
operaciones. Un barco entra cuando faltan DIAS_AVISO dias o menos para su ETA del line-up (o ya
esta en puerto). La home muestra "TIENES TAREAS PENDIENTES" (rojo) o "HOY ESTÁS AL DÍA" (verde)."""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..dates import fmt_display, parse_date
from ..models import User, VesselCall, VesselFile, VesselTask
from ..templating import templates

router = APIRouter()

DIAS_AVISO = 5  # el barco aparece cuando faltan este numero de dias (o menos) para su ETA

# (clave, texto, aclaracion). Con contrato Charter se abre la lista de documentos.
CHARTER_ITEMS = [
    ("pending_docs", "Pending docs", "mail que enviamos nosotros"),
    ("documentos", "Documentos", ""),
    ("sig_bodegas", "SIG Bodegas", ""),
    ("sigres", "SIGRES", ""),
    ("deb", "DEB", ""),
    ("mani", "MANI", ""),
]
# Si el barco viene del exterior se piden ademas estos dos.
EXTERIOR_ITEMS = [
    ("pbip", "PBIP", ""),
    ("libre_platica", "Libre plática", ""),
]
CONTRATOS = {"CHARTER": "Charter", "OPA": "OPA"}
ITEM_KEYS = {k for k, _, _ in CHARTER_ITEMS + EXTERIOR_ITEMS}


def _checklist(vf: VesselFile) -> dict:
    try:
        data = json.loads(vf.checklist or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _arrival(call: VesselCall | None, today: date) -> dict:
    """Cuando llega el barco segun el line-up. visible = ya corresponde mostrarlo."""
    if call is None:
        return {"visible": False, "label": "sin barco en el line-up", "days": None}
    eta, etb = (call.eta or "").strip(), (call.etb or "").strip()
    low = f"{eta} {etb}".lower()
    if "alongside" in low or "roads" in low or "at port" in low:
        return {"visible": True, "label": f"ya en puerto · {eta or etb}", "days": -999}
    d = parse_date(eta) or parse_date(etb)
    if not d:
        return {"visible": False, "label": "sin ETA", "days": None}
    days = (d - today).days
    if days > 0:
        when = f"faltan {days} día{'s' if days != 1 else ''}"
    elif days == 0:
        when = "llega hoy"
    else:
        when = f"ETA vencida hace {-days} día{'s' if days != -1 else ''}"
    return {"visible": days <= DIAS_AVISO, "label": f"ETA {fmt_display(d)} · {when}", "days": days}


def _items_for(vf: VesselFile) -> list[dict]:
    """Casillas que corresponden a este barco segun su contrato y si viene del exterior."""
    done = _checklist(vf)
    wanted = []
    if vf.contrato == "CHARTER":
        wanted += [("Documentos", CHARTER_ITEMS)]
    if vf.exterior:
        wanted += [("Del exterior", EXTERIOR_ITEMS)]
    out = []
    for group, items in wanted:
        for key, text, note in items:
            d = done.get(key) or {}
            out.append({"key": key, "text": text, "note": note, "group": group,
                        "done": bool(d), "by": d.get("by", ""), "at": d.get("at", "")})
    return out


def pending_cards(db: Session) -> tuple[list[dict], list[dict]]:
    """(barcos que ya aparecen, barcos que todavia no) -- los legajos abiertos con su ETA."""
    today = date.today()
    shown, later = [], []
    for vf in db.scalars(select(VesselFile).where(VesselFile.status == "open").order_by(VesselFile.id)):
        call = db.scalar(
            select(VesselCall)
            .where(VesselCall.vessel_name == vf.vessel_name, VesselCall.terminal_id == vf.terminal_id)
            .order_by(VesselCall.id.desc())
        )
        arrival = _arrival(call, today)
        items = _items_for(vf)
        tasks = list(vf.tasks)
        card = {
            "vf": vf, "arrival": arrival, "items": items, "tasks": tasks,
            # sin tipo de contrato elegido tambien es un pendiente (si no, el cartel diria "al dia")
            "sin_contrato": not vf.contrato,
            "open": (0 if vf.contrato else 1) + sum(1 for i in items if not i["done"]) + sum(1 for t in tasks if not t.done),
        }
        (shown if arrival["visible"] else later).append(card)
    shown.sort(key=lambda c: (c["arrival"]["days"], c["vf"].id))
    later.sort(key=lambda c: (c["arrival"]["days"] is None, c["arrival"]["days"] or 0, c["vf"].id))
    return shown, later


def pending_summary(db: Session) -> dict:
    """Cuantas casillas sin tildar hay en los barcos que ya aparecen, y en cuantos barcos."""
    shown, _ = pending_cards(db)
    return {"count": sum(c["open"] for c in shown), "vessels": sum(1 for c in shown if c["open"]), "overdue": 0}


@router.get("/pendientes", response_class=HTMLResponse)
def pendientes_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    shown, later = pending_cards(db)
    return templates.TemplateResponse(request, "pendientes.html", {
        "user": user,
        "cards": shown,
        "later": later,
        "summary": {"count": sum(c["open"] for c in shown), "vessels": sum(1 for c in shown if c["open"])},
        "contratos": CONTRATOS,
        "dias_aviso": DIAS_AVISO,
    })


def _back(file_id: int) -> RedirectResponse:
    return RedirectResponse(f"/pendientes#barco-{file_id}", status_code=303)


@router.post("/pendientes/{file_id}/config")
def set_config(file_id: int, contrato: str = Form(""), exterior: str = Form(""),
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Tipo de contrato (Charter / OPA) y si viene del exterior."""
    vf = db.get(VesselFile, file_id)
    if vf:
        vf.contrato = contrato if contrato in CONTRATOS else ""
        vf.exterior = exterior == "on"
        db.commit()
    return _back(file_id)


@router.post("/pendientes/{file_id}/item/{key}/toggle")
def toggle_item(file_id: int, key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    vf = db.get(VesselFile, file_id)
    if vf and key in ITEM_KEYS:
        data = _checklist(vf)
        if key in data:
            del data[key]
        else:
            data[key] = {"by": user.username, "at": datetime.now().strftime("%d/%m %H:%M")}
        vf.checklist = json.dumps(data)
        db.commit()
    return _back(file_id)


@router.post("/pendientes/{file_id}/tareas")
def add_task(file_id: int, text: str = Form(""), due_date: str = Form(""),
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    vf = db.get(VesselFile, file_id)
    text = " ".join(text.split())[:300]
    if vf and text:
        db.add(VesselTask(vessel_file_id=vf.id, text=text, created_by=user.username))
        db.commit()
    return _back(file_id)


@router.post("/pendientes/tareas/{task_id}/toggle")
def toggle_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(VesselTask, task_id)
    if not t:
        return RedirectResponse("/pendientes", status_code=303)
    t.done = not t.done
    t.done_by = user.username if t.done else ""
    t.done_at = datetime.utcnow() if t.done else None
    db.commit()
    return _back(t.vessel_file_id)


@router.post("/pendientes/tareas/{task_id}/borrar")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(VesselTask, task_id)
    file_id = t.vessel_file_id if t else 0
    if t:
        db.delete(t)
        db.commit()
    return _back(file_id) if file_id else RedirectResponse("/pendientes", status_code=303)
