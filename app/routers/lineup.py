from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from datetime import date, datetime

from ..dates import eta_sort_key, parse_date
from ..models import Client, OperatedVessel, Terminal, User, VesselCall, VesselExtraAgency, VesselFile
from ..recalc import recalc_lineup, recalc_terminal
from ..service import (
    active_clients,
    active_terminals,
    calls_for_lineup,
    ensure_vessel_file,
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
BOOL_FIELDS = {"is_ours", "second_call"}
SEA_WHITE = {"sea white", "seawhite", "sw"}


def _render_lineup(request: Request, db: Session, user: User, kind: str) -> HTMLResponse:
    lineup = get_draft_lineup(db, kind)
    terminals = active_terminals(db, kind)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    return templates.TemplateResponse(
        request,
        "lineup.html",
        {
            "user": user,
            "kind": kind,
            "flammable": kind == "FLAMMABLE",
            "lineup": lineup,
            "terminals": terminals,
            "grouped": grouped,
            "clients": active_clients(db),
            "vessel_types": ["Bulk Carrier", "Tanker"],
            "ours_count": sum(1 for c in calls if c.is_ours),
        },
    )


@router.get("/", response_class=HTMLResponse)
def grain_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _render_lineup(request, db, user, "GRAIN")


@router.get("/flammable", response_class=HTMLResponse)
def flammable_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _render_lineup(request, db, user, "FLAMMABLE")


_MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _period_label(p: str) -> str:
    try:
        y, m = p.split("-")
        return f"{_MESES[int(m)].capitalize()} {y}"
    except (ValueError, IndexError):
        return p or "sin mes"


@router.get("/nuestros-barcos", response_class=HTMLResponse)
def our_vessels_page(request: Request, mes: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    en_lineup = []
    for kind in ("GRAIN", "FLAMMABLE"):
        lineup = get_draft_lineup(db, kind)
        terminals = active_terminals(db, kind)
        grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
        term_by_id = {t.id: t for t in terminals}
        for t in terminals:
            for c in grouped.get(t.id, []):
                if c.is_ours:
                    en_lineup.append((kind, term_by_id.get(c.terminal_id), c))
    en_lineup.sort(key=lambda row: eta_sort_key(row[2].eta, row[2].etb))

    todos = list(db.scalars(select(OperatedVessel).order_by(OperatedVessel.period.desc(),
                                                            OperatedVessel.operated_at.desc())))
    # conteo por mes para las pestañas
    counts: dict[str, int] = {}
    for o in todos:
        counts[o.period or ""] = counts.get(o.period or "", 0) + 1
    meses = sorted(counts.keys(), reverse=True)
    operados = [o for o in todos if o.period == mes] if mes else todos

    return templates.TemplateResponse(
        request,
        "nuestros_barcos.html",
        {
            "user": user,
            "en_lineup": en_lineup,
            "operados": operados,
            "total_operados": len(todos),
            "mes": mes,
            "meses": [(m, _period_label(m), counts[m]) for m in meses],
            "period_label": _period_label,
            "clients": active_clients(db),
        },
    )


@router.post("/nuestros-barcos/agregar")
def add_our_vessel(
    db: Session = Depends(get_db), user: User = Depends(current_user),
    vessel_name: str = Form(...), ubicacion: str = Form(...),
    principal: str = Form(""), eta: str = Form(""),
):
    """Alta rapida para barcos que no pasan por el line-up "oficial" (ej.
    vienen solo a tomar bunker, en Boya 11) -- se escribe la ubicacion a
    mano y si no existe un muelle con ese nombre se crea uno nuevo (GRAIN,
    excluido del Excel), asi la proxima vez que se repita esa ubicacion se
    reusa el mismo. Queda marcado "Nuestro" y abre legajo en Barcos (ID)
    igual que cualquier otro barco nuestro."""
    ubicacion = ubicacion.strip()
    if not vessel_name.strip() or not ubicacion:
        return RedirectResponse("/nuestros-barcos", status_code=302)

    terminal = db.scalar(
        select(Terminal).where(Terminal.kind == "GRAIN", func.lower(Terminal.code) == ubicacion.lower())
    )
    if not terminal:
        max_order = db.scalar(select(func.coalesce(func.max(Terminal.sort_order), 0)).where(Terminal.kind == "GRAIN"))
        terminal = Terminal(
            kind="GRAIN", code=ubicacion, name=ubicacion, berth_label=ubicacion,
            sort_order=max(max_order or 0, 890) + 10, active=True, exclude_from_excel=True,
        )
        db.add(terminal)
        db.flush()

    lineup = get_draft_lineup(db, "GRAIN")
    max_order = db.scalar(
        select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
            VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal.id
        )
    )
    call = VesselCall(
        lineup_id=lineup.id, terminal_id=terminal.id, sort_order=(max_order or 0) + 10,
        vessel_name=vessel_name.strip(), vessel_type="Bulk Carrier", operation="Load",
        eta=eta.strip(), is_ours=True,
    )
    db.add(call)
    db.flush()
    _set_principal(db, call, principal.strip())
    lineup.updated_by = user.username
    ensure_vessel_file(db, call, user)
    db.commit()
    return RedirectResponse("/nuestros-barcos", status_code=302)


@router.post("/operados/{op_id}/mes")
def move_operated(op_id: int, period: str = Form(""), volver: str = Form(""),
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(OperatedVessel, op_id)
    if row:
        p = period.strip()[:7]
        if len(p) == 7 and p[4] == "-":
            row.period = p
            db.commit()
    dest = f"/nuestros-barcos?mes={volver}" if volver else "/nuestros-barcos"
    return RedirectResponse(dest + "#operados", status_code=302)


@router.post("/operados/{op_id}/delete")
def delete_operated(op_id: int, volver: str = Form(""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(OperatedVessel, op_id)
    if row:
        db.delete(row)
        db.commit()
    dest = f"/nuestros-barcos?mes={volver}" if volver else "/nuestros-barcos"
    return RedirectResponse(dest + "#operados", status_code=302)


@router.post("/api/lineup")
async def update_lineup(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    lineup = get_draft_lineup(db, str(data.get("kind", "GRAIN")))
    # la fecha ya no se toca a mano -- get_draft_lineup la pisa sola con hoy
    if "port_name" in data:
        lineup.port_name = str(data["port_name"]).strip()
    lineup.updated_by = user.username
    db.commit()
    return {"ok": True}


@router.post("/api/calls")
async def create_call(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    terminal = db.get(Terminal, int(data["terminal_id"]))
    if not terminal:
        return JSONResponse({"error": "terminal no existe"}, status_code=400)
    lineup = get_draft_lineup(db, terminal.kind)
    max_order = db.scalar(
        select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
            VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal.id
        )
    )
    call = VesselCall(
        lineup_id=lineup.id,
        terminal_id=terminal.id,
        sort_order=(max_order or 0) + 10,
        operation="Load",
        vessel_type="Tanker" if terminal.kind == "FLAMMABLE" else "Bulk Carrier",
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

    if field in BOOL_FIELDS:
        setattr(call, field, bool(value))
    elif field == "principal":
        _set_principal(db, call, str(value).strip())
    elif field in EDITABLE:
        setattr(call, field, str(value).strip())
        if field == "local_agent":
            call.is_ours = (str(value).strip().lower() in SEA_WHITE) or call.is_ours
    else:
        return JSONResponse({"error": f"campo invalido: {field}"}, status_code=400)

    call.lineup.updated_by = user.username
    vf = ensure_vessel_file(db, call, user) if call.is_ours else None
    db.commit()
    return {
        "ok": True,
        "is_ours": call.is_ours,
        "principal_name": call.principal_name,
        "linked": call.principal_client_id is not None,
        "file_id": vf.id if vf else None,
    }


@router.post("/api/terminals/{terminal_id}/note")
async def update_terminal_note(terminal_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    term = db.get(Terminal, terminal_id)
    if not term:
        return JSONResponse({"error": "no existe"}, status_code=404)
    term.status_note = str(data.get("value", "")).strip()
    db.commit()
    return {"ok": True}


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
    db.flush()
    if call.is_ours:
        ensure_vessel_file(db, call, user)
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
        if call.is_ours:
            _archive_operated(db, call, user)
            # se saco del line-up (X) -- si tenia legajo abierto en Barcos
            # (ID), se cierra tambien: si no, queda "abierto" para siempre
            # aunque el barco ya se fue (sumando de mas en Abiertos).
            vf = db.scalar(
                select(VesselFile).where(
                    VesselFile.status == "open",
                    func.lower(VesselFile.vessel_name) == call.vessel_name.strip().lower(),
                    VesselFile.terminal_id == call.terminal_id,
                )
            )
            if vf:
                vf.status = "closed"
                vf.closed_at = datetime.utcnow()
        db.delete(call)
        db.commit()
    return {"ok": True}


def _archive_operated(db: Session, call: VesselCall, user: User) -> None:
    """Una fila por CADA cliente (principal + otras agencias) -- si el barco
    tenia 3 clientes cuenta como 3 barcos operados para el recuento mensual,
    no como uno solo con los otros dos pegados en un campo de texto aparte."""
    term = call.terminal
    d = parse_date(call.etc) or parse_date(call.etb) or date.today()
    clients = call.recipient_clients()
    names = [c.name for c in clients] if clients else [call.principal_name]
    for name in names:
        db.add(
            OperatedVessel(
                removed_by=user.username,
                period=d.strftime("%Y-%m"),
                lineup_date=call.lineup.lineup_date if call.lineup else "",
                terminal_code=term.code if term else "",
                berth_label=(term.berth_label or term.code) if term else "",
                vessel_name=call.vessel_name,
                vessel_type=call.vessel_type,
                imo=call.imo,
                eta=call.eta,
                etb=call.etb,
                etc=call.etc,
                operation=call.operation,
                quantity=call.quantity,
                grade=call.grade,
                shipper=call.shipper,
                destination=call.destination,
                local_agent=call.local_agent,
                principal=name,
                extras="",
            )
        )


def _changes_payload(changes) -> dict:
    return {
        "ok": True,
        "count": len(changes),
        "changes": [
            {"vessel": c.vessel_name, "field": c.field, "old": c.old, "new": c.new}
            for c in changes
        ],
    }


@router.post("/api/recalc")
def recalc(kind: str = "GRAIN", db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db, kind)
    terminals = active_terminals(db, kind)
    grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
    changes = recalc_lineup(grouped)
    db.commit()
    return _changes_payload(changes)


@router.post("/api/terminals/{terminal_id}/recalc")
def recalc_one_terminal(terminal_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    term = db.get(Terminal, terminal_id)
    if not term:
        return JSONResponse({"error": "no existe"}, status_code=404)
    lineup = get_draft_lineup(db, term.kind)
    calls = list(
        db.scalars(
            select(VesselCall)
            .where(VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal_id)
            .order_by(VesselCall.sort_order, VesselCall.id)
        )
    )
    changes = recalc_terminal(calls)
    db.commit()
    return _changes_payload(changes)


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
