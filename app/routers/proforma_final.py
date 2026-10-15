"""Administracion: proforma final (asistente), agencias a facturar (fee y cargas sociales) y calendario de feriados."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import proforma_final as pf
from ..auth import administracion_required
from ..database import get_db
from ..models import AppSetting, Client, Feriado, User
from ..templating import templates

router = APIRouter(prefix="/administracion")

CARGAS_GENERAL_KEY = "proforma_final_cargas_sociales_general"


def cargas_general(db: Session) -> float:
    row = db.get(AppSetting, CARGAS_GENERAL_KEY)
    try:
        return float(row.value) if row else 0.0
    except ValueError:
        return 0.0


def _agencias(db: Session) -> list[Client]:
    """Las agencias de Clientes (no las estibas)."""
    return list(db.scalars(select(Client).where(Client.active.is_(True), Client.client_type != "ESTIBA").order_by(Client.name)))


def _pct(raw: str) -> float | None:
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        n = float(raw)
    except ValueError:
        return None
    return n if 0 <= n <= 100 else None


def _usd(raw: str) -> float:
    try:
        n = float((raw or "").strip().replace(",", "."))
    except ValueError:
        return 0.0
    return n if 0 <= n <= 10_000_000 else 0.0


# ------------------------------------------------------------ asistente ----
@router.get("/proforma-final", response_class=HTMLResponse)
def proforma_final_page(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    general = cargas_general(db)
    agencias = [{
        "id": c.id, "nombre": c.name, "fee_usd": c.fee_usd or 0,
        "cargas_pct": c.cargas_sociales_pct if c.cargas_sociales_pct is not None else general,
    } for c in _agencias(db)]
    return templates.TemplateResponse(request, "administracion/proforma_final.html", {
        "user": user, "agencias": agencias, "pasos": pf.PASOS, "hoy": date.today().isoformat(),
    })


@router.post("/proforma-final/excel")
async def proforma_final_excel(request: Request, user: User = Depends(administracion_required)):
    state = pf.clean_state(await request.json())
    nombre = f"Proforma final - {state['agencia']['nombre'] or 'sin agencia'} - {date.today().strftime('%d.%m.%Y')}.xlsx"
    return Response(
        content=pf.build_excel(state),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"X-Filename": nombre.encode("ascii", "ignore").decode() or "Proforma final.xlsx"},
    )


@router.post("/proforma-final/leer")
async def proforma_final_leer(archivo: UploadFile, user: User = Depends(administracion_required)):
    try:
        data = await archivo.read(pf.MAX_BYTES + 1)
        return {"ok": True, "state": pf.read_excel(data)}
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


# ------------------------------------------------------------- agencias ----
@router.get("/agencias", response_class=HTMLResponse)
def agencias_page(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    return templates.TemplateResponse(request, "administracion/agencias.html", {
        "user": user, "agencias": _agencias(db), "general": cargas_general(db), "guardado": request.query_params.get("ok") == "1",
    })


@router.post("/agencias/guardar")
async def agencias_guardar(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    form = await request.form()
    general = _pct(str(form.get("general", ""))) or 0.0
    row = db.get(AppSetting, CARGAS_GENERAL_KEY)
    if row:
        row.value = str(general)
    else:
        db.add(AppSetting(key=CARGAS_GENERAL_KEY, value=str(general)))
    for c in _agencias(db):
        c.fee_usd = _usd(str(form.get(f"fee_{c.id}", "")))
        c.cargas_sociales_pct = _pct(str(form.get(f"pct_{c.id}", "")))  # vacio = usa el general
    db.commit()
    return RedirectResponse("/administracion/agencias?ok=1", status_code=303)


# ------------------------------------------------------------- calendario --
@router.get("/calendario", response_class=HTMLResponse)
def calendario_page(request: Request, anio: int = 0, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    anio = anio or date.today().year
    feriados = [
        {"id": f.id, "fecha": f.fecha, "d": date.fromisoformat(f.fecha), "nombre": f.nombre}
        for f in db.scalars(select(Feriado).where(Feriado.fecha.like(f"{anio}-%")).order_by(Feriado.fecha))
    ]
    for f in feriados:
        f["dia"] = pf.DIAS[f["d"].weekday()]
    return templates.TemplateResponse(request, "administracion/calendario.html", {
        "user": user, "feriados": feriados, "anio": anio, "error": request.query_params.get("error", ""),
    })


@router.post("/calendario/agregar")
def calendario_agregar(fecha: str = Form(""), nombre: str = Form(""),
                       db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        return RedirectResponse("/administracion/calendario?error=fecha", status_code=303)
    if db.scalar(select(Feriado).where(Feriado.fecha == d.isoformat())):
        return RedirectResponse(f"/administracion/calendario?anio={d.year}&error=repetido", status_code=303)
    db.add(Feriado(fecha=d.isoformat(), nombre=" ".join(nombre.split())[:120] or "Feriado", creado_por=user.username))
    db.commit()
    return RedirectResponse(f"/administracion/calendario?anio={d.year}", status_code=303)


@router.post("/calendario/{feriado_id}/borrar")
def calendario_borrar(feriado_id: int, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    f = db.get(Feriado, feriado_id)
    anio = f.fecha[:4] if f else date.today().year
    if f:
        db.delete(f)
        db.commit()
    return RedirectResponse(f"/administracion/calendario?anio={anio}", status_code=303)
