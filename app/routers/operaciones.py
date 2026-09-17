from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..auth import current_user
from ..models import User
from ..templating import templates

router = APIRouter()


@router.get("/operaciones", response_class=HTMLResponse)
def operaciones_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "operaciones.html", {"user": user})


@router.get("/operaciones/utilidades", response_class=HTMLResponse)
def utilidades_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades.html", {"user": user})
