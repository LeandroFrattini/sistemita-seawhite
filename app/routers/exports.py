import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..excel_export import build_lineup_xlsx
from ..models import ArchivedLineup, User
from ..service import (
    active_terminals,
    calls_for_lineup,
    get_draft_lineup,
    group_by_terminal,
)
from ..templating import templates

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(db: Session, *, internal: bool) -> StreamingResponse:
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    bio, filename = build_lineup_xlsx(lineup, terminals, grouped, internal=internal)
    return StreamingResponse(
        bio,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/internal.xlsx")
def export_internal(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _xlsx_response(db, internal=True)


@router.get("/export/clients.xlsx")
def export_clients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _xlsx_response(db, internal=False)


@router.get("/finalize")
def finalize_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    archives = (
        db.query(ArchivedLineup).order_by(ArchivedLineup.archived_at.desc()).limit(30).all()
    )
    reportable = [
        c for c in calls if c.is_ours and c.recipient_clients()
    ]
    return templates.TemplateResponse(
        request,
        "finalize.html",
        {
            "user": user,
            "lineup": lineup,
            "terminals": terminals,
            "grouped": grouped,
            "archives": archives,
            "reportable": reportable,
            "ours_no_recipient": [c for c in calls if c.is_ours and not c.recipient_clients()],
        },
    )


@router.post("/finalize")
def finalize_submit(db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db)
    terminals = active_terminals(db)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)

    payload = {
        "lineup_date": lineup.lineup_date,
        "port_name": lineup.port_name,
        "terminals": [
            {
                "code": t.code,
                "name": t.name,
                "berth_label": t.berth_label,
                "calls": [
                    {
                        "vessel_name": c.vessel_name,
                        "vessel_type": c.vessel_type,
                        "imo": c.imo,
                        "eta": c.eta,
                        "etb": c.etb,
                        "etc": c.etc,
                        "operation": c.operation,
                        "quantity": c.quantity,
                        "grade": c.grade,
                        "shipper": c.shipper,
                        "destination": c.destination,
                        "local_agent": c.local_agent,
                        "principal": c.principal_name,
                        "extras": [link.client.name for link in c.extra_agencies if link.client],
                        "is_ours": c.is_ours,
                    }
                    for c in grouped.get(t.id, [])
                ],
            }
            for t in terminals
        ],
    }
    db.add(
        ArchivedLineup(
            lineup_date=lineup.lineup_date,
            archived_by=user.username,
            payload_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )
    )
    db.commit()
    return RedirectResponse("/finalize?archived=1", status_code=302)
