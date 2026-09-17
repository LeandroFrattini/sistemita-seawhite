from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ..auth import admin_required
from ..models import User
from ..templating import templates

router = APIRouter()


@router.get("/administracion", response_class=HTMLResponse)
def administracion_page(request: Request, user: User = Depends(admin_required)):
    return templates.TemplateResponse(request, "administracion.html", {"user": user})
