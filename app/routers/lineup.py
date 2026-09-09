from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import Client, User, VesselCall, VesselExtraAgency
from ..recalc import recalc_lineup
from ..service import (
    active_clients,
    active_terminals,
    calls_for_lineup,
    get_draft_lineup,
    group_by_terminal,
    sync_is_ours,
)
from ..templating import templates

router = APIRouter()

EDITABLE = {
    "vessel_name", "vessel_type", "imo", "eta", "etb", "etc", "operation",
    "quantity", "grade", "shipper", "destination", "local_agent",
}
SEA_WHITE = {"sea white", "seawhite", "sw"}


@router.get("/", response_class=HTMLResponse)
def lineup_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    clients = active_clients(db)
    return templates.TemplateResponse(
        request,
        "lineup.html",
        {
            "user": user,
            "lineup": lineup,
            "terminals": terminals,
            "grouped": grouped,
            "clients": clients,
            "vessel_types": ["Bulk Carrier", "Tanker"],
            "ours_count": sum(1 for c in calls if c.is_ours),
        },
    )


@router.post("/api/lineup")
async def update_lineup(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    lineup = get_draft_lineup(db)
    if "lineup_date" in data:
        lineup.lineup_date = str(data["lineup_date"]).strip()
    if "port_name" in data:
        lineup.port_name = str(data["port_name"]).strip()
    lineup.updated_by = user.username
    db.commit()
    return {"ok": True}


@router.post("/api/calls")
async def create_call(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    lineup = get_draft_lineup(db)
    terminal_id = int(data["terminal_id"])
    max_order = db.scalar(
        select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
            VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal_id
        )
    )
    call = VesselCall(
        lineup_id=lineup.id,
        terminal_id=terminal_id,
        sort_order=(max_order or 0) + 10,
        operation="Load",
        vessel_type="Bulk Carrier",
    )
    db.add(call)
    lineup.updated_by = user.username
    db.commit()
    return {"ok": True, "id": call.id}


@router.patch("/api/calls/{call_id}")
async def update_call(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    field = data.get("field")
    value = data.get("value", "")

    if field == "is_ours":
        call.is_ours = bool(value)
    elif field == "principal":
        _set_principal(db, call, str(value).strip())
    elif field in EDITABLE:
        setattr(call, field, str(value).strip())
        if field == "local_agent":
            call.is_ours = (str(value).strip().lower() in SEA_WHITE) or call.is_ours
    else:
        return JSONResponse({"error": f"campo invalido: {field}"}, status_code=400)

    call.lineup.updated_by = user.username
    db.commit()
    return {
        "ok": True,
        "is_ours": call.is_ours,
        "principal_name": call.principal_name,
        "linked": call.principal_client_id is not None,
    }


@router.post("/api/calls/{call_id}/extras")
async def set_extras(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    ids = {int(x) for x in data.get("client_ids", []) if str(x).strip()}
    call.extra_agencies.clear()
    db.flush()
    for cid in ids:
        if db.get(Client, cid):
            db.add(VesselExtraAgency(vessel_call_id=call.id, client_id=cid))
    db.commit()
    return {"ok": True}


@router.post("/api/calls/{call_id}/move")
async def move_call(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    direction = data.get("direction")
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    siblings = list(
        db.scalars(
            select(VesselCall)
            .where(
                VesselCall.lineup_id == call.lineup_id,
                VesselCall.terminal_id == call.terminal_id,
            )
            .order_by(VesselCall.sort_order, VesselCall.id)
        )
    )
    idx = next(i for i, c in enumerate(siblings) if c.id == call.id)
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(siblings):
        other = siblings[swap]
        call.sort_order, other.sort_order = other.sort_order, call.sort_order
        db.commit()
    return {"ok": True}


@router.delete("/api/calls/{call_id}")
def delete_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    call = db.get(VesselCall, call_id)
    if call:
        db.delete(call)
        db.commit()
    return {"ok": True}


@router.post("/api/recalc")
def recalc(db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    changes = recalc_lineup(grouped)
    db.commit()
    return {
        "ok": True,
        "count": len(changes),
        "changes": [
            {"vessel": c.vessel_name, "field": c.field, "old": c.old, "new": c.new}
            for c in changes
        ],
    }


def _set_principal(db: Session, call: VesselCall, value: str) -> None:
    if not value:
        call.principal_client_id = None
        call.principal_text = ""
        return
    client = db.scalar(select(Client).where(func.lower(Client.name) == value.lower()))
    if client:
        call.principal_client_id = client.id
        call.principal_text = ""
    else:
        call.principal_client_id = None
        call.principal_text = value
