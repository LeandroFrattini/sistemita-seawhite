"""Generador de documentacion (Utilidades): completa los documentos para las
autoridades con los datos del buque y de la escala. Se guardan solo los datos
de buques por IMO y las agencias; los archivos generados no se guardan.
"""
import re
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..docgen.generators import DOCS, Ctx, build_many
from ..models import DocAgency, DocVessel, User
from ..templating import templates

router = APIRouter(prefix="/operaciones/utilidades/documentacion")

VESSEL_FIELDS = ["name", "kind", "flag", "eslora", "manga", "puntal", "trn", "trb",
                 "call_sign", "matricula", "puerto_registro", "armador"]
CALL_FIELDS = ["capitan", "ultimo_puerto", "procedencia", "destino", "descripcion_viaje",
               "carga_detalle", "estadia", "tripulantes", "pasajeros", "lista_pasajeros",
               "terminal", "exportador", "ciudad_exportador", "carga"]
MAX_LOGO = 2 * 1024 * 1024


def _imo(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _vessel_dict(v: DocVessel) -> dict:
    return {"imo": v.imo, **{f: getattr(v, f) for f in VESSEL_FIELDS}}


def _agency_dict(a: DocAgency) -> dict:
    return {"id": a.id, "name": a.name, "address": a.address, "doc_format": a.doc_format,
            "has_logo": bool(a.logo)}


def _date(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError(f"Fecha inválida: {raw}")


def _clean_vessel(data: dict) -> dict:
    out = {f: (data.get(f) or "").strip() for f in VESSEL_FIELDS}
    out["kind"] = out["kind"] if out["kind"] in ("BULK_CARRIER", "TANKER") else "BULK_CARRIER"
    return out


def _upsert_vessel(db: Session, imo: str, data: dict) -> DocVessel:
    v = db.scalar(select(DocVessel).where(DocVessel.imo == imo))
    if not v:
        v = DocVessel(imo=imo)
        db.add(v)
    for f, val in _clean_vessel(data).items():
        setattr(v, f, val)
    db.commit()
    return v


@router.get("", response_class=HTMLResponse)
def page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    agencies = db.scalars(select(DocAgency).order_by(DocAgency.name)).all()
    return templates.TemplateResponse(request, "utilidades/documentacion.html", {
        "user": user,
        "docs": [{"key": k, "label": label, "reg": reg} for k, label, reg in DOCS],
        "agencies": [_agency_dict(a) for a in agencies],
        "today": date.today().isoformat(),
    })


# ------------------------------------------------------------ buques -------
@router.get("/barco")
def get_vessel(imo: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = _imo(imo)
    if not n:
        return JSONResponse({"found": False, "error": "Ingresá un IMO"}, status_code=400)
    v = db.scalar(select(DocVessel).where(DocVessel.imo == n))
    return {"found": bool(v), "imo": n, "vessel": _vessel_dict(v) if v else None}


@router.post("/barco")
async def save_vessel(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    imo = _imo(data.get("imo"))
    if not imo or not (data.get("name") or "").strip():
        return JSONResponse({"ok": False, "error": "Faltan el IMO y el nombre del buque"}, status_code=400)
    return {"ok": True, "vessel": _vessel_dict(_upsert_vessel(db, imo, data))}


# ---------------------------------------------------------- agencias -------
@router.get("/agencias.json")
def list_agencies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_agency_dict(a) for a in db.scalars(select(DocAgency).order_by(DocAgency.name)).all()]


def _logo_from_upload(upload: UploadFile | None) -> tuple[bytes, str] | None:
    if upload is None or not upload.filename:
        return None
    data = upload.file.read(MAX_LOGO + 1)
    if len(data) > MAX_LOGO:
        raise ValueError("El logo pesa más de 2 MB")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "image/png"
    if data[:2] == b"\xff\xd8":
        return data, "image/jpeg"
    raise ValueError("El logo tiene que ser PNG o JPG")


@router.post("/agencias")
def create_agency(
    name: str = Form(...), address: str = Form(""), doc_format: str = Form("GENERAL"),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    name = name.strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Falta el nombre de la agencia"}, status_code=400)
    if db.scalar(select(DocAgency).where(DocAgency.name == name)):
        return JSONResponse({"ok": False, "error": "Ya existe una agencia con ese nombre"}, status_code=400)
    a = DocAgency(name=name, address=address.strip(),
                  doc_format="HEINLEIN" if doc_format == "HEINLEIN" else "GENERAL")
    try:
        got = _logo_from_upload(logo)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    if got:
        a.logo, a.logo_mime = got
    db.add(a)
    db.commit()
    return {"ok": True, "agency": _agency_dict(a)}


@router.post("/agencias/{agency_id}")
def update_agency(
    agency_id: int,
    name: str = Form(...), address: str = Form(""), doc_format: str = Form("GENERAL"),
    remove_logo: str = Form(""), logo: UploadFile | None = File(None),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    a = db.get(DocAgency, agency_id)
    if not a:
        return JSONResponse({"ok": False, "error": "Agencia no encontrada"}, status_code=404)
    name = name.strip()
    if not name:
        return JSONResponse({"ok": False, "error": "Falta el nombre de la agencia"}, status_code=400)
    clash = db.scalar(select(DocAgency).where(DocAgency.name == name, DocAgency.id != agency_id))
    if clash:
        return JSONResponse({"ok": False, "error": "Ya existe una agencia con ese nombre"}, status_code=400)
    try:
        got = _logo_from_upload(logo)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    a.name, a.address = name, address.strip()
    a.doc_format = "HEINLEIN" if doc_format == "HEINLEIN" else "GENERAL"
    if got:
        a.logo, a.logo_mime = got
    elif remove_logo == "on":
        a.logo, a.logo_mime = None, ""
    db.commit()
    return {"ok": True, "agency": _agency_dict(a)}


@router.post("/agencias/{agency_id}/borrar")
def delete_agency(agency_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(DocAgency, agency_id)
    if a:
        db.delete(a)
        db.commit()
    return {"ok": True}


@router.get("/agencias/{agency_id}/logo")
def agency_logo(agency_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = db.get(DocAgency, agency_id)
    if not a or not a.logo:
        return Response(status_code=404)
    return Response(content=a.logo, media_type=a.logo_mime or "image/png",
                    headers={"Cache-Control": "private, max-age=60"})


# ---------------------------------------------------------- generacion -----
@router.post("/generar")
async def generate(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()

    def fail(msg: str):
        return JSONResponse({"ok": False, "error": msg}, status_code=400)

    vessel = _clean_vessel(data.get("vessel") or {})
    if not vessel["name"]:
        return fail("Falta el nombre del buque")
    imo = _imo((data.get("vessel") or {}).get("imo"))
    vessel["imo"] = imo

    call = {f: ((data.get("call") or {}).get(f) or "").strip() for f in CALL_FIELDS}
    if not call["ciudad_exportador"]:
        call["ciudad_exportador"] = "Bahia Blanca"

    wanted = {d.get("key"): d.get("date") for d in (data.get("docs") or []) if d.get("key")}
    order = [k for k, _, _ in DOCS if k in wanted]
    if not order:
        return fail("Tildá al menos un documento")

    agency = db.get(DocAgency, int(data["agency_id"])) if data.get("agency_id") else None
    if {"ped_carga", "bill"} & set(order) and agency is None:
        return fail("Elegí la agencia para el Pedido de Carga y el BILL")

    dates: dict[str, date] = {}
    try:
        for k in order:
            if k == "serenos":
                continue
            d = _date(wanted[k])
            if d is None:
                return fail("Falta la fecha de uno de los documentos")
            dates[k] = d
        serenos = {k: _date((data.get("serenos") or {}).get(k))
                   for k in ("solicitud", "t0006", "t0612", "t1218", "t1824")}
    except ValueError as e:
        return fail(str(e))
    if "serenos" in order and not all(serenos.values()):
        return fail("Completá la fecha de solicitud y las 4 fechas de turno de Serenos")

    if imo:
        _upsert_vessel(db, imo, vessel)  # queda el historial del buque para la proxima escala

    ctx = Ctx(vessel=vessel, call=call, agency=agency, dates=dates, serenos=serenos,
              migra_modo="SALIDA" if data.get("migra_modo") == "SALIDA" else "ENTRADA")
    name, content, mime = build_many(order, ctx)
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip() or "documentacion"
    return Response(
        content=content, media_type=mime,
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"},
    )
