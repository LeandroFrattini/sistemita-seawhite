from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..excel_import import ImportResult, parse_lineup_xlsx
from ..models import Client, Terminal, User, VesselCall, VesselExtraAgency
from ..service import ensure_vessel_file, get_draft_lineup, sync_is_ours
from ..templating import templates

router = APIRouter()


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "import.html", {"user": user, "result": None})


@router.post("/import", response_class=HTMLResponse)
async def import_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    file: UploadFile = File(...),
    mode: str = Form("replace"),
):
    data = await file.read()
    try:
        result = parse_lineup_xlsx(data)
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse(
            request,
            "import.html",
            {"user": user, "result": None, "error": f"No se pudo leer el archivo: {exc}"},
        )

    if not result.terminals:
        return templates.TemplateResponse(
            request, "import.html", {"user": user, "result": result, "error": None, "applied": False}
        )

    applied = _apply(db, user, result, replace=(mode == "replace"))
    return templates.TemplateResponse(
        request,
        "import.html",
        {"user": user, "result": result, "error": None, "applied": True, "summary": applied},
    )


def _apply(db: Session, user: User, result: ImportResult, *, replace: bool) -> dict:
    lineup = get_draft_lineup(db)
    if replace:
        for c in list(db.scalars(select(VesselCall).where(VesselCall.lineup_id == lineup.id))):
            db.delete(c)
        db.flush()

    if result.port_name:
        lineup.port_name = result.port_name

    clients = {c.name.lower(): c for c in db.scalars(select(Client))}
    created_terminals: list[str] = []
    unmatched_clients: set[str] = set()
    n_calls = 0

    for it in result.terminals:
        term = _get_or_make_terminal(db, it.code, created_terminals)
        base_order = db.scalar(
            select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
                VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == term.id
            )
        ) or 0
        for i, ic in enumerate(it.calls, start=1):
            call = VesselCall(
                lineup_id=lineup.id,
                terminal_id=term.id,
                sort_order=base_order + i * 10,
                vessel_name=ic.vessel_name,
                vessel_type=_vessel_type(ic.vessel_type),
                imo=ic.imo,
                eta=ic.eta,
                etb=ic.etb,
                etc=ic.etc,
                operation=ic.operation or "Load",
                quantity=ic.quantity,
                grade=ic.grade,
                shipper=ic.shipper,
                destination=ic.destination,
                local_agent=ic.local,
            )
            _set_principal(call, ic.principal, clients, unmatched_clients)
            sync_is_ours(call)
            db.add(call)
            db.flush()
            _set_extras(db, call, ic.otras, clients, unmatched_clients)
            if call.is_ours:
                ensure_vessel_file(db, call, user)
            n_calls += 1

    lineup.updated_by = user.username
    db.commit()
    return {
        "terminals": len(result.terminals),
        "calls": n_calls,
        "created_terminals": created_terminals,
        "unmatched_clients": sorted(unmatched_clients),
        "warnings": result.warnings,
    }


def _get_or_make_terminal(db: Session, code: str, created: list[str]) -> Terminal:
    code = code.strip()
    term = db.scalar(
        select(Terminal).where(
            (func.lower(Terminal.code) == code.lower())
            | (func.lower(Terminal.name) == code.lower())
        )
    )
    if term:
        return term
    max_order = db.scalar(select(func.coalesce(func.max(Terminal.sort_order), 0))) or 0
    term = Terminal(code=code, name=code, berth_label=f"{code} berth", sort_order=max_order + 10, active=True)
    db.add(term)
    db.flush()
    created.append(code)
    return term


def _vessel_type(raw: str) -> str:
    return "Tanker" if "tank" in (raw or "").lower() else "Bulk Carrier"


def _set_principal(call: VesselCall, raw: str, clients: dict, unmatched: set) -> None:
    raw = (raw or "").strip()
    if not raw:
        return
    hit = clients.get(raw.lower())
    if hit:
        call.principal_client_id = hit.id
    else:
        call.principal_text = raw


def _set_extras(db: Session, call: VesselCall, raw: str, clients: dict, unmatched: set) -> None:
    for token in (raw or "").replace(";", ",").split(","):
        name = token.strip()
        if not name:
            continue
        hit = clients.get(name.lower())
        if hit and hit.id != call.principal_client_id:
            db.add(VesselExtraAgency(vessel_call_id=call.id, client_id=hit.id))
        elif not hit:
            unmatched.add(name)
