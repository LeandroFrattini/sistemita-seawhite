from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import User
from ..service import active_clients
from ..templating import templates

router = APIRouter()


@router.get("/operaciones", response_class=HTMLResponse)
def operaciones_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "operaciones.html", {"user": user})


@router.get("/operaciones/utilidades", response_class=HTMLResponse)
def utilidades_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades.html", {"user": user})


@router.get("/operaciones/utilidades/pending-docs", response_class=HTMLResponse)
def pending_docs_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades/pending_docs.html", {
        "user": user, "clients": active_clients(db),
    })
