import io
import time
import uuid
import zipfile

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from .. import liquidaciones as liq
from ..auth import administracion_required
from ..models import User
from ..templating import templates

router = APIRouter()


@router.get("/administracion", response_class=HTMLResponse)
def administracion_page(request: Request, user: User = Depends(administracion_required)):
    return templates.TemplateResponse(request, "administracion.html", {"user": user})


# --- Liquidaciones Aduana --------------------------------------------------
# Modulo one-shot/stateless: no persiste nada en base, solo guarda el .xlsx
# generado en memoria un rato corto (TTL) para que se pueda descargar
# despues de ver los resultados, sin tener que reprocesar.
_ARCHIVOS_TEMP: dict[str, dict] = {}
_TTL_SEGUNDOS = 30 * 60


def _limpiar_temporales():
    limite = time.time() - _TTL_SEGUNDOS
    vencidos = [t for t, v in _ARCHIVOS_TEMP.items() if v["creado"] < limite]
    for t in vencidos:
        _ARCHIVOS_TEMP.pop(t, None)


@router.get("/administracion/liquidaciones", response_class=HTMLResponse)
def liquidaciones_form(request: Request, user: User = Depends(administracion_required)):
    return templates.TemplateResponse(request, "administracion/liquidaciones.html", {"user": user, "resultado": None, "error": None})


@router.post("/administracion/liquidaciones/procesar", response_class=HTMLResponse)
async def liquidaciones_procesar(
    request: Request, excel: UploadFile, zip: UploadFile, user: User = Depends(administracion_required),
):
    _limpiar_temporales()
    error = None
    resultado = None
    token = None
    try:
        if not excel.filename.lower().endswith(".xlsx"):
            raise ValueError("El primer archivo tiene que ser el Excel de liquidaciones (.xlsx).")
        if not zip.filename.lower().endswith(".zip"):
            raise ValueError("El segundo archivo tiene que ser el .zip con los PDFs de habilitacion.")

        excel_bytes = await excel.read()
        zip_bytes = await zip.read()

        if len(zip_bytes) > 50 * 1024 * 1024:
            raise ValueError("El .zip pesa mas de 50 MB, revisa que sean solo los PDFs de habilitacion.")
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                if not any(n.lower().endswith(".pdf") for n in zf.namelist()):
                    raise ValueError("El .zip no tiene ningun PDF adentro.")
        except zipfile.BadZipFile:
            raise ValueError("El archivo .zip esta corrupto o no es un zip valido.")

        resultado = liq.procesar(excel_bytes, zip_bytes)
        token = uuid.uuid4().hex
        _ARCHIVOS_TEMP[token] = {
            "bytes": resultado.excel_bytes,
            "filename": f"Liquidaciones_clasificadas.xlsx",
            "creado": time.time(),
        }
    except ValueError as e:
        error = str(e)
    except Exception:
        error = "No se pudo procesar los archivos. Revisa que sean el Excel y el .zip correctos."

    return templates.TemplateResponse(request, "administracion/_liquidaciones_resultado.html", {
        "user": user, "resultado": resultado, "error": error, "token": token,
        "catalogo": liq.CATALOGO_TIPOS,
    })


@router.get("/administracion/liquidaciones/descargar/{token}")
def liquidaciones_descargar(token: str, user: User = Depends(administracion_required)):
    _limpiar_temporales()
    entry = _ARCHIVOS_TEMP.get(token)
    if not entry:
        return RedirectResponse(url="/administracion/liquidaciones", status_code=302)
    bio = io.BytesIO(entry["bytes"])
    bio.seek(0)
    return StreamingResponse(
        bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{entry["filename"]}"'},
    )
