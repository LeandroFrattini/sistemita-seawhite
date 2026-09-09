"""Helpers de dominio compartidos por los routers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import AppSetting, Client, Lineup, Terminal, VesselCall, VesselExtraAgency

SIGNATURE_KEY = "report_signature_html"


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


def get_draft_lineup(db: Session) -> Lineup:
    lineup = db.scalar(
        select(Lineup).where(Lineup.status == "draft").order_by(Lineup.id.desc())
    )
    if not lineup:
        lineup = Lineup(status="draft", lineup_date="", port_name="")
        db.add(lineup)
        db.commit()
    return lineup


def active_terminals(db: Session) -> list[Terminal]:
    return list(
        db.scalars(
            select(Terminal).where(Terminal.active).order_by(Terminal.sort_order, Terminal.id)
        )
    )


def all_terminals(db: Session) -> list[Terminal]:
    return list(db.scalars(select(Terminal).order_by(Terminal.sort_order, Terminal.id)))


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
