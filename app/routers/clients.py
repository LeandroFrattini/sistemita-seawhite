from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import Client, User, VesselCall, VesselExtraAgency
from ..service import all_clients
from ..templating import templates

router = APIRouter()


@router.get("/clients", response_class=HTMLResponse)
def clients_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return templates.TemplateResponse(
        request,
        "clients.html",
        {"user": user, "clients": all_clients(db), "formats": ["EXCEL", "WBL_TEXT"]},
    )


@router.post("/clients")
def create_client(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    name: str = Form(...),
    to_name: str = Form(""),
    emails: str = Form(""),
    report_format: str = Form("EXCEL"),
):
    name = name.strip()
    if name and not db.query(Client).filter(Client.name.ilike(name)).first():
        db.add(
            Client(
                name=name,
                to_name=to_name.strip(),
                emails=emails.strip(),
                report_format=report_format if report_format in {"EXCEL", "WBL_TEXT"} else "EXCEL",
                active=True,
            )
        )
        db.commit()
    return RedirectResponse("/clients", status_code=302)


@router.post("/clients/{client_id}")
def update_client(
    client_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    name: str = Form(...),
    to_name: str = Form(""),
    emails: str = Form(""),
    report_format: str = Form("EXCEL"),
    active: str = Form("on"),
):
    client = db.get(Client, client_id)
    if client:
        client.name = name.strip()
        client.to_name = to_name.strip()
        client.emails = emails.strip()
        client.report_format = report_format if report_format in {"EXCEL", "WBL_TEXT"} else "EXCEL"
        client.active = active == "on"
        db.commit()
    return RedirectResponse("/clients", status_code=302)


@router.post("/clients/{client_id}/delete")
def deactivate_client(client_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    client = db.get(Client, client_id)
    if client:
        client.active = False
        db.commit()
    return RedirectResponse("/clients", status_code=302)


@router.post("/clients/{client_id}/borrar")
def delete_client(client_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Borrado permanente. Suelta las referencias del line-up:
    - PRINCIPAL vinculado -> pasa a texto libre con el nombre del cliente
    - Otras agencias -> se quita el vínculo
    """
    client = db.get(Client, client_id)
    if client:
        for vc in db.scalars(select(VesselCall).where(VesselCall.principal_client_id == client_id)):
            vc.principal_client_id = None
            if not vc.principal_text:
                vc.principal_text = client.name
        db.query(VesselExtraAgency).filter(VesselExtraAgency.client_id == client_id).delete()
        db.delete(client)
        db.commit()
    return RedirectResponse("/clients", status_code=302)
