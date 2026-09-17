import io
import mimetypes
from email.message import EmailMessage

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import BASE_DIR
from ..database import get_db
from ..models import User
from ..service import active_clients
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
    return templates.TemplateResponse(request, "utilidades/pending_docs.html", {
        "user": user, "clients": active_clients(db),
    })


@router.post("/operaciones/utilidades/pending-docs/eml")
async def pending_docs_eml(request: Request, user: User = Depends(current_user)):
    """Arma un .eml (mensaje MIME real) con los adjuntos fijos que
    correspondan y lo devuelve para descargar -- un mailto: normal no puede
    llevar adjuntos por navegador, pero un .eml descargado si los trae
    embebidos: al abrirlo, Outlook lo carga con todo listo para revisar."""
    data = await request.json()
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = data.get("body") or ""
    filename = (data.get("filename") or "Pending Docs.eml").strip().replace("/", "-")
    claves = data.get("attachments") or []

    msg = EmailMessage()
    msg["From"] = "Sea White <operations@seawhite.com.ar>"
    if to:
        msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    for clave in claves:
        entry = ATTACHMENT_FILES.get(clave)
        if not entry:
            continue
        disk_name, display_name = entry
        path = ATTACHMENTS_DIR / disk_name
        if not path.exists():
            continue
        ctype, _ = mimetypes.guess_type(display_name)
        maintype, subtype = ctype.split("/", 1) if ctype else ("application", "octet-stream")
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=display_name)

    bio = io.BytesIO(bytes(msg))
    bio.seek(0)
    return StreamingResponse(
        bio, media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
