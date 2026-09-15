"""Helpers de dominio compartidos por los routers."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    AppSetting,
    Client,
    Lineup,
    Terminal,
    User,
    VesselCall,
    VesselExtraAgency,
    VesselFile,
    VesselFileAgency,
)

SIGNATURE_KEY = "report_signature_html"
CC_KEY = "report_cc"
DEFAULT_CC = "operations@seawhite.com.ar"


def split_emails(raw: str) -> list[str]:
    raw = (raw or "").replace(";", ",").replace("\n", ",")
    return [e.strip() for e in raw.split(",") if e.strip()]


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def get_draft_lineup(db: Session, kind: str = "GRAIN") -> Lineup:
    """El line-up en borrador (Grain o Flammable). La fecha se pisa sola con
    la de hoy en cada acceso -- asi no depende de que alguien se acuerde de
    moverla a mano (y de paso, evita mandar un reporte con fecha vieja)."""
    today = date.today().strftime("%d/%m/%y")
    lineup = db.scalar(
        select(Lineup)
        .where(Lineup.status == "draft", Lineup.kind == kind)
        .order_by(Lineup.id.desc())
    )
    if not lineup:
        lineup = Lineup(kind=kind, status="draft", lineup_date=today, port_name="")
        db.add(lineup)
        db.commit()
    elif lineup.lineup_date != today:
        lineup.lineup_date = today
        db.commit()
    return lineup


def active_terminals(db: Session, kind: str = "GRAIN") -> list[Terminal]:
    return list(
        db.scalars(
            select(Terminal)
            .where(Terminal.active, Terminal.kind == kind)
            .order_by(Terminal.sort_order, Terminal.id)
        )
    )


def all_terminals(db: Session, kind: str | None = None) -> list[Terminal]:
    stmt = select(Terminal).order_by(Terminal.kind, Terminal.sort_order, Terminal.id)
    if kind:
        stmt = stmt.where(Terminal.kind == kind)
    return list(db.scalars(stmt))


def active_clients(db: Session) -> list[Client]:
    return list(db.scalars(select(Client).where(Client.active).order_by(Client.name)))


def all_clients(db: Session) -> list[Client]:
    return list(db.scalars(select(Client).order_by(Client.name)))


def calls_for_lineup(db: Session, lineup_id: int) -> list[VesselCall]:
    return list(
        db.scalars(
            select(VesselCall)
            .where(VesselCall.lineup_id == lineup_id)
            .options(
                selectinload(VesselCall.principal_client),
                selectinload(VesselCall.extra_agencies).selectinload(VesselExtraAgency.client),
            )
            .order_by(VesselCall.terminal_id, VesselCall.sort_order, VesselCall.id)
        )
    )


def group_by_terminal(
    terminals: list[Terminal], calls: list[VesselCall]
) -> dict[int, list[VesselCall]]:
    grouped: dict[int, list[VesselCall]] = {t.id: [] for t in terminals}
    for call in calls:
        grouped.setdefault(call.terminal_id, []).append(call)
    for lst in grouped.values():
        lst.sort(key=lambda c: (c.sort_order, c.id))
    return grouped


def sync_is_ours(call: VesselCall) -> None:
    """Marca el barco como propio si el agente local es Sea White."""
    if (call.local_agent or "").strip().lower() in {"sea white", "seawhite", "sw"}:
        call.is_ours = True


def ensure_vessel_file(db: Session, call: VesselCall, user: User | None) -> VesselFile | None:
    """Crea (o reutiliza si ya hay uno abierto para ese barco+muelle) el
    legajo con ID de un barco marcado "Nuestro", y sincroniza cliente y
    otras agencias. No hace nada si el barco no es nuestro."""
    if not call.is_ours or not (call.vessel_name or "").strip():
        return None

    vf = db.scalar(
        select(VesselFile).where(
            VesselFile.status == "open",
            func.lower(VesselFile.vessel_name) == call.vessel_name.strip().lower(),
            VesselFile.terminal_id == call.terminal_id,
        )
    )
    if not vf:
        term = call.terminal
        vf = VesselFile(
            kind=term.kind if term else "GRAIN",
            vessel_name=call.vessel_name.strip(),
            vessel_type=call.vessel_type,
            terminal_id=call.terminal_id,
            terminal_code=term.code if term else "",
            opened_by=user.username if user else "",
        )
        db.add(vf)
        db.flush()

    vf.vessel_type = call.vessel_type or vf.vessel_type
    vf.principal_client_id = call.principal_client_id
    vf.principal_text = call.principal_text
    _sync_vessel_file_fields(db, call, vf)
    return vf


def close_vessel_file_if_open(db: Session, call: VesselCall) -> VesselFile | None:
    """Contraparte de ensure_vessel_file: si un barco deja de ser "nuestro"
    y todavia tiene un legajo abierto en Barcos (ID) para ese muelle, lo
    cierra (igual que el boton "Cerrar" manual) para que no quede colgado."""
    if not (call.vessel_name or "").strip():
        return None
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
    return vf


def _sync_vessel_file_fields(db: Session, call: VesselCall, vf: VesselFile) -> None:
    current_ids = set(
        db.scalars(
            select(VesselExtraAgency.client_id).where(VesselExtraAgency.vessel_call_id == call.id)
        )
    )
    existing_ids = {link.client_id for link in vf.agencies}
    for cid in current_ids - existing_ids:
        db.add(VesselFileAgency(vessel_file_id=vf.id, client_id=cid))
    for link in list(vf.agencies):
        if link.client_id not in current_ids:
            db.delete(link)
