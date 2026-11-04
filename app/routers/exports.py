import json
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..eml import build_eml, safe_filename
from ..excel_export import build_lineup_xlsx
from ..models import ArchivedLineup, Client, User
from ..service import (
    CC_KEY,
    DEFAULT_CC,
    active_terminals,
    calls_for_lineup,
    get_draft_lineup,
    get_setting,
    group_by_terminal,
    split_emails,
)
from ..templating import templates

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(db: Session, *, internal: bool) -> StreamingResponse:
    lineup = get_draft_lineup(db)
    terminals = [t for t in active_terminals(db) if not t.exclude_from_excel]
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


@router.get("/export/heinlein.eml")
def export_heinlein_eml(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """El mail que se le manda a Heinlein, armado: asunto, texto, destinatarios (los de Heinlein en Clientes), copia a Operations y el Excel interno adjunto.
    Se baja como .eml (borrador de Outlook): se abre, se revisa y se envia."""
    lineup = get_draft_lineup(db)
    terminals = [t for t in active_terminals(db) if not t.exclude_from_excel]
    grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
    bio, nombre_xlsx = build_lineup_xlsx(lineup, terminals, grouped, internal=True)
    cliente = db.scalar(select(Client).where(func.lower(Client.name).like("%heinlein%"), Client.active.is_(True)).order_by(Client.id))
    para = cliente.email_list if cliente else []
    cc = [e for e in (split_emails(get_setting(db, CC_KEY, DEFAULT_CC)) or ["operations@seawhite.com.ar"]) if e not in para]
    fecha = (lineup.lineup_date or "").replace("/", ".")
    puerto = (settings.port_name or "BAHIA BLANCA").upper().replace(" PORT", "").strip()
    asunto = f"{puerto} - GRAIN TERMINALS LINE UP - {fecha} / HEINLEIN"
    lineas = [fecha, "", "BUEN DIA,", "", "NOTAR ADJUNTO GRAIN TERMINALS LINE UP CON AGENCIAS LOCALES/DE BS AS."]
    texto = "\n".join(lineas) + "\n"
    html = ('<div style="font-family:\'Courier New\',Courier,monospace;font-size:13px;line-height:1.4;">'
            + "<br>".join(escape(l) if l else "&nbsp;" for l in lineas) + "</div>")
    data = build_eml(subject=asunto, to_emails=para, cc_emails=cc, html_body=html, text_body=texto,
                     attachments=[(nombre_xlsx, bio.getvalue(), XLSX_MIME)])
    return Response(content=data, media_type="message/rfc822",
                    headers={"Content-Disposition": f'attachment; filename="{safe_filename(asunto.replace(" / ", " - "))}.eml"'})


@router.get("/export/clients.xlsx")
def export_clients(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _xlsx_response(db, internal=False)


@router.get("/finalize")
def finalize_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db)
    terminals = [t for t in active_terminals(db) if not t.exclude_from_excel]
    terminal_ids = {t.id for t in terminals}
    calls = [c for c in calls_for_lineup(db, lineup.id) if c.terminal_id in terminal_ids]
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
    terminals = [t for t in active_terminals(db) if not t.exclude_from_excel]
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
