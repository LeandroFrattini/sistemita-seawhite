import io
import zipfile

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import BASE_DIR
from ..database import get_db
from ..models import Client, User
from ..templating import templates

router = APIRouter()

# Plantillas fijas para Pending Docs (Utilidades) -- clave usada por el
# frontend -> (nombre de archivo en disco, nombre "lindo" para el adjunto).
# Si el archivo todavia no fue subido a ATTACHMENTS_DIR, se lo salta sin
# romper (asi el mail sale igual, solo sin ese adjunto puntual).
ATTACHMENTS_DIR = BASE_DIR / "app" / "static" / "utilidades" / "pending_docs_attachments"
ATTACHMENT_FILES = {
    "maritime_health": ("maritime_health_declaration.doc", "Maritime Declaration of Health.doc"),
    "ballast_water": ("ballast_water_reporting_form.doc", "Ballast Water Reporting Form.doc"),
    "senasa_form_a": ("senasa_form_a.pdf", "Senasa - Form A.pdf"),
    "senasa_form_b": ("senasa_form_b.pdf", "Senasa - Form B.pdf"),
    "om_1645": ("om_1645.pdf", "OM 1645.pdf"),
    "om_1646": ("om_1646.pdf", "OM 1646.pdf"),
    "om_1647": ("om_1647.pdf", "OM 1647.pdf"),
    "om_1648": ("om_1648.pdf", "OM 1648.pdf"),
    "shore_pass": ("shore_pass.xls", "Shore Pass.xls"),
}


@router.get("/operaciones", response_class=HTMLResponse)
def operaciones_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "operaciones.html", {"user": user})


@router.get("/operaciones/utilidades", response_class=HTMLResponse)
def utilidades_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades.html", {"user": user})


@router.get("/operaciones/utilidades/pending-docs", response_class=HTMLResponse)
def pending_docs_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    # Solo agencias -- los grupos de estiba no operan documentacion de buque,
    # no hace falta mandarles Pending Docs
    clients = db.scalars(
        select(Client).where(Client.active == True, Client.client_type == "AGENCY").order_by(Client.name)
    ).all()
    return templates.TemplateResponse(request, "utilidades/pending_docs.html", {
        "user": user, "clients": clients,
    })


@router.post("/operaciones/utilidades/pending-docs/adjuntos.zip")
async def pending_docs_adjuntos(request: Request, user: User = Depends(current_user)):
    """Descarga en un .zip las plantillas fijas que correspondan, para
    arrastrarlas al mail que "Abrir en Outlook" (mailto:) ya dejo abierto
    -- un mailto: no puede llevar adjuntos por navegador, es una limitacion
    del navegador, asi que el adjunto se suma a mano en un paso aparte."""
    data = await request.json()
    claves = data.get("attachments") or []

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for clave in claves:
            entry = ATTACHMENT_FILES.get(clave)
            if not entry:
                continue
            disk_name, display_name = entry
            path = ATTACHMENTS_DIR / disk_name
            if not path.exists():
                continue
            zf.writestr(display_name, path.read_bytes())
    bio.seek(0)
    return StreamingResponse(
        bio, media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="Adjuntos Pending Docs.zip"'},
    )
