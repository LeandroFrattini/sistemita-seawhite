import io
import json
import zipfile
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from ..auth import current_user
from ..config import BASE_DIR
from ..costos_templates import PLANTILLAS as COSTOS_PLANTILLAS
from ..database import get_db
from ..fondeaderos_templates import FONDEADEROS
from ..migraciones_docs import Tripulante, build_acta_reconduccion, build_nota_migraciones, build_shore_pass
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


@router.get("/operaciones/utilidades/costos", response_class=HTMLResponse)
def costos_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades/costos.html", {
        "user": user, "plantillas": COSTOS_PLANTILLAS,
    })


@router.get("/operaciones/utilidades/fondeaderos", response_class=HTMLResponse)
def fondeaderos_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades/fondeaderos.html", {
        "user": user, "fondeaderos": FONDEADEROS,
    })


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


def _tripulantes_desde_json(raw: str) -> list[Tripulante]:
    data = json.loads(raw or "[]")
    return [Tripulante(**{k: (v or "").strip() if isinstance(v, str) else v for k, v in t.items()}) for t in data]


DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/operaciones/utilidades/migraciones", response_class=HTMLResponse)
def migraciones_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "utilidades/migraciones.html", {
        "user": user, "hoy": date.today().isoformat(),
    })


@router.post("/operaciones/utilidades/migraciones/nota.docx")
def migraciones_nota(
    tipo: str = Form(...), fecha: str = Form(...), bandera: str = Form(...),
    buque: str = Form(...), muelle: str = Form(""), tripulantes: str = Form("[]"),
    user: User = Depends(current_user),
):
    bio = build_nota_migraciones(
        tipo=tipo, fecha=date.fromisoformat(fecha), bandera=bandera.strip().upper(),
        buque=buque.strip().upper(), muelle=muelle.strip().upper(),
        tripulantes=_tripulantes_desde_json(tripulantes),
    )
    nombre = f"{'Desembarco' if tipo.upper() == 'DESEMBARCO' else 'Embarco'} - {buque.strip()}.docx"
    return StreamingResponse(bio, media_type=DOCX_MEDIA, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/operaciones/utilidades/migraciones/reconduccion.docx")
def migraciones_reconduccion(
    fecha: str = Form(...), nacionalidad: str = Form(...), nombre: str = Form(...),
    pasaporte: str = Form(...), bandera: str = Form(...), buque: str = Form(...),
    vuelo: str = Form(...), fecha_salida: str = Form(...), hora_salida: str = Form(...),
    user: User = Depends(current_user),
):
    bio = build_acta_reconduccion(
        fecha=date.fromisoformat(fecha), nacionalidad=nacionalidad.strip(), nombre=nombre.strip(),
        pasaporte=pasaporte.strip(), bandera=bandera.strip(), buque=buque.strip(),
        vuelo=vuelo.strip(), fecha_salida=fecha_salida.strip(), hora_salida=hora_salida.strip(),
    )
    nombre_archivo = f"Acta Reconduccion - {nombre.strip()}.docx"
    return StreamingResponse(bio, media_type=DOCX_MEDIA, headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'})


@router.post("/operaciones/utilidades/migraciones/shore-pass.zip")
async def migraciones_shore_pass(
    request: Request, buque: str = Form(...), empresa_signataria: str = Form("SEA WHITE"),
    lugar_fecha: str = Form(...), tripulantes: str = Form("[]"),
    user: User = Depends(current_user),
):
    form = await request.form()
    trips = _tripulantes_desde_json(tripulantes)

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, trip in enumerate(trips):
            foto = form.get(f"foto_{idx}")
            foto_bytes = await foto.read() if isinstance(foto, UploadFile) and foto.filename else None
            ficha = build_shore_pass(
                buque=buque.strip().upper(), empresa_signataria=empresa_signataria.strip() or "SEA WHITE",
                lugar_fecha=lugar_fecha.strip(), trip=trip, foto_bytes=foto_bytes,
            )
            nombre = f"Shore Pass - {trip.nombre.strip() or f'tripulante {idx + 1}'}.xlsx"
            zf.writestr(nombre, ficha.read())
    bio.seek(0)
    return StreamingResponse(
        bio, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="Shore Pass - {buque.strip()}.zip"'},
    )
