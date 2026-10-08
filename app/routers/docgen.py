"""Generador de documentacion (Utilidades): completa los documentos para las
autoridades con los datos del buque y de la escala. Se guardan solo los datos
de buques por IMO y las agencias; los archivos generados no se guardan.
"""
import base64
import json
import re
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, verify_password
from ..database import get_db
from ..docgen.firma import normalize_firma
from ..docgen.generators import DOCS, DOC_KEYS, FIRMA_DOCS, NO_DATE, NOT_DEFAULT, OPTIONAL, STAGES, Ctx, build_many
from ..docgen.logos import normalize_logo
from ..models import DocAgency, DocCall, DocFavorite, DocVessel, User
from ..templating import templates

router = APIRouter(prefix="/operaciones/utilidades/documentacion")

VESSEL_FIELDS = ["name", "kind", "flag", "eslora", "manga", "puntal", "trn", "trb",
                 "call_sign", "matricula", "puerto_registro", "armador",
                 "clasificacion", "velocidad", "inmarsat", "company_id"]
CALL_FIELDS = ["capitan", "ultimo_puerto", "procedencia", "destino", "descripcion_viaje",
               "carga_detalle", "estadia", "tripulantes", "pasajeros", "lista_pasajeros",
               "terminal", "exportador", "ciudad_exportador", "carga",
               "calado_proa", "calado_popa", "calado_max", "practico", "remolque_proa",
               "remolque_popa", "estima"]
MAX_LOGO = 2 * 1024 * 1024

# Vencimientos de certificados del buque (orden de la pantalla). Se guardan siempre con el buque.
CERTIFICADOS = [
    ("iapp", "IAPP"), ("radio", "RADIO"), ("equipo", "EQUIPO"), ("francobordo", "FRANCOBORDO"),
    ("construccion", "CONSTRUCCION"), ("desratizacion", "DESRATIZACION"), ("polucion", "POLUCION"),
    ("cgs", "C.G.S."), ("doc", "D.O.C."), ("isps", "I.S.P.S."),
    ("mlc", "MLC"), ("fitness", "FITNESS"), ("sewage", "SEWAGE"), ("clc", "CLC"),
]
CERT_KEYS = [k for k, _ in CERTIFICADOS]


def _imo(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _certs_load(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        data = {}
    return {k: str(data.get(k) or "") for k in CERT_KEYS}


def _vessel_dict(v: DocVessel, favorito: bool = False) -> dict:
    updated = v.updated_at.isoformat() + "Z" if v.updated_at else ""
    return {"imo": v.imo, "updated_at": updated, "certificados": _certs_load(v.certificados), "favorito": favorito,
            **{f: getattr(v, f) for f in VESSEL_FIELDS}}


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
    if isinstance(data.get("certificados"), dict):  # sin la clave, no se pisan los guardados
        out["certificados"] = {k: _iso_or_text(data["certificados"].get(k)) for k in CERT_KEYS}
    return out


def _iso_or_text(raw) -> str:
    return str(raw or "").strip()[:40]


def _upsert_vessel(db: Session, imo: str, data: dict) -> DocVessel:
    v = db.scalar(select(DocVessel).where(DocVessel.imo == imo))
    if not v:
        v = DocVessel(imo=imo)
        db.add(v)
    for f, val in _clean_vessel(data).items():
        if f == "certificados":
            v.certificados = json.dumps(val, ensure_ascii=False)
        else:
            setattr(v, f, val)
    v.updated_at = datetime.utcnow()  # "ultima modificacion" tambien cuando se vuelve a generar
    db.commit()
    return v


@router.get("", response_class=HTMLResponse)
def page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    agencies = db.scalars(select(DocAgency).order_by(DocAgency.name)).all()
    return templates.TemplateResponse(request, "utilidades/documentacion.html", {
        "user": user,
        "docs": [{"key": k, "label": label, "reg": reg, "stage": STAGES.get(k, "ENTRADA"),
                  "checked": k not in NOT_DEFAULT, "has_date": k not in NO_DATE,
                  "has_firma": k in FIRMA_DOCS, "optional": k in OPTIONAL} for k, label, reg in DOCS],
        "certificados": [{"key": k, "label": label} for k, label in CERTIFICADOS],
        "agencies": [_agency_dict(a) for a in agencies],
        "today": date.today().isoformat(),
    })


# ------------------------------------------------------------ buques -------
@router.get("/barcos.json")
def list_vessels(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Historial: todos los buques, con todos sus datos, ordenados por nombre."""
    rows = db.scalars(select(DocVessel).order_by(DocVessel.name)).all()
    favs = set(db.scalars(select(DocFavorite.imo).where(DocFavorite.user_id == user.id)).all())
    return [_vessel_dict(v, v.imo in favs) for v in rows]


@router.post("/barco/{imo}/favorito")
def toggle_favorite(imo: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Marca o desmarca el buque como favorito del usuario (es por usuario, no de todos)."""
    imo = _imo(imo)
    if not imo or not db.scalar(select(DocVessel).where(DocVessel.imo == imo)):
        return JSONResponse({"ok": False, "error": "Primero guardá el buque"}, status_code=404)
    fav = db.scalar(select(DocFavorite).where(DocFavorite.user_id == user.id, DocFavorite.imo == imo))
    if fav:
        db.delete(fav)
        favorito = False
    else:
        db.add(DocFavorite(user_id=user.id, imo=imo))
        favorito = True
    db.commit()
    return {"ok": True, "favorito": favorito}


@router.post("/barco")
async def save_vessel(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    imo = _imo(data.get("imo"))
    if not imo or not (data.get("name") or "").strip():
        return JSONResponse({"ok": False, "error": "Faltan el IMO y el nombre del buque"}, status_code=400)
    return {"ok": True, "vessel": _vessel_dict(_upsert_vessel(db, imo, data))}


# ----------------------------------------------------------- escalas -------
SERENO_KEYS = ("solicitud", "t0006", "t0612", "t1218", "t1824")


def _iso(raw) -> str:
    try:
        return date.fromisoformat(str(raw)).isoformat() if raw else ""
    except ValueError:
        return ""


def _clean_state(data: dict) -> dict:
    """Lo que guarda una escala: tarjeta Escala + fechas de documentos y de Serenos."""
    call = data.get("call") or {}
    dates, blank = data.get("dates") or {}, data.get("blank") or {}
    ser, ser_blank = data.get("serenos") or {}, data.get("serenos_blank") or {}
    return {
        "call": {f: str(call.get(f) or "")[:500] for f in CALL_FIELDS},
        "dates": {k: _iso(dates.get(k)) for k in DOC_KEYS},
        "blank": {k: bool(blank.get(k)) for k in DOC_KEYS},
        "serenos": {k: _iso(ser.get(k)) for k in SERENO_KEYS},
        "serenos_blank": {k: bool(ser_blank.get(k)) for k in SERENO_KEYS},
    }


def _call_dict(c: DocCall) -> dict:
    try:
        state = json.loads(c.data or "{}")
    except ValueError:
        state = {}
    return {"id": c.id, "imo": c.imo, "state": state, "has_firma": bool(c.firma),
            "created_at": c.created_at.isoformat() + "Z" if c.created_at else "",
            "updated_at": c.updated_at.isoformat() + "Z" if c.updated_at else ""}


def _save_call(db: Session, imo: str, call_id, state: dict) -> DocCall:
    c = db.get(DocCall, int(call_id)) if call_id else None
    if c is None or c.imo != imo:
        c = DocCall(imo=imo)
        db.add(c)
    c.data = json.dumps(_clean_state(state), ensure_ascii=False)
    c.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return c


@router.get("/barco/{imo}/escalas.json")
def list_calls(imo: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(DocCall).where(DocCall.imo == _imo(imo)).order_by(DocCall.created_at.desc(), DocCall.id.desc())).all()
    return [_call_dict(c) for c in rows]


@router.post("/escalas")
async def save_call(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    imo = _imo(data.get("imo"))
    if not imo or not db.scalar(select(DocVessel).where(DocVessel.imo == imo)):
        return JSONResponse({"ok": False, "error": "Guardá primero los datos del buque (hace falta el IMO)"}, status_code=400)
    return {"ok": True, "call": _call_dict(_save_call(db, imo, data.get("id"), data.get("state") or {}))}


MAX_FIRMA = 20 * 1024 * 1024


@router.post("/escalas/{call_id}/firma")
def upload_firma(call_id: int, firma: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    c = db.get(DocCall, call_id)
    if not c:
        return JSONResponse({"ok": False, "error": "Primero guardá la escala"}, status_code=404)
    data = firma.file.read(MAX_FIRMA + 1)
    if len(data) > MAX_FIRMA:
        return JSONResponse({"ok": False, "error": "La imagen pesa más de 20 MB"}, status_code=400)
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8"):
        return JSONResponse({"ok": False, "error": "La firma tiene que ser un JPG o PNG"}, status_code=400)
    try:
        png = normalize_firma(data)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    c.firma = base64.b64encode(png).decode("ascii")
    db.commit()
    return {"ok": True, "call": _call_dict(c)}


@router.post("/escalas/{call_id}/firma/quitar")
def remove_firma(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(DocCall, call_id)
    if c:
        c.firma = ""
        db.commit()
    return {"ok": True}


@router.get("/escalas/{call_id}/firma")
def get_firma(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(DocCall, call_id)
    if not c or not c.firma:
        return Response(status_code=404)
    return Response(content=base64.b64decode(c.firma), media_type="image/png",
                    headers={"Cache-Control": "private, no-store"})


@router.post("/escalas/{call_id}/borrar")
async def delete_call(call_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    data = await request.json()
    if not verify_password(str(data.get("password") or ""), user.password_hash):
        return JSONResponse({"ok": False, "error": "Contraseña incorrecta"}, status_code=403)
    c = db.get(DocCall, call_id)
    if c:
        db.delete(c)
        db.commit()
    return {"ok": True}


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

    wanted = {d.get("key"): d for d in (data.get("docs") or []) if d.get("key")}
    order = [k for k, _, _ in DOCS if k in wanted]
    if not order:
        return fail("Tildá al menos un documento")

    agency = db.get(DocAgency, int(data["agency_id"])) if data.get("agency_id") else None
    if {"ped_carga", "bill"} & set(order) and agency is None:
        return fail("Elegí la agencia para el Pedido de Carga y el BILL")

    dates: dict[str, date] = {}
    try:
        for k in order:
            if k in NO_DATE:
                continue  # serenos tiene sus propias fechas; los PBIP no llevan fecha
            if wanted[k].get("blank"):
                continue  # fecha en blanco: sale vacia para completarla a mano
            d = _date(wanted[k].get("date"))
            if d is None:
                return fail("Falta la fecha de uno de los documentos (o tildá «en blanco»)")
            dates[k] = d
        s_dates, s_blank = data.get("serenos") or {}, data.get("serenos_blank") or {}
        serenos = {k: (None if s_blank.get(k) else _date(s_dates.get(k)))
                   for k in ("solicitud", "t0006", "t0612", "t1218", "t1824")}
        if "serenos" in order and any(v is None and not s_blank.get(k) for k, v in serenos.items()):
            return fail("Completá las 5 fechas de Serenos (o tildá «en blanco»)")
    except ValueError as e:
        return fail(str(e))

    call_id = None
    if imo:
        _upsert_vessel(db, imo, vessel)  # queda el historial del buque para la proxima escala
        state = dict(data.get("state") or {}, call=call)
        call_id = _save_call(db, imo, data.get("call_id"), state).id  # y la escala, con sus fechas

    firma_keys = {k for k in (data.get("firma_docs") or []) if k in FIRMA_DOCS and k in order}
    firma = None
    if firma_keys:
        saved = db.get(DocCall, call_id) if call_id else None
        if not saved or not saved.firma:
            return fail("Subí la firma del capitán en la sección Escala (y guardá la escala) para poder usarla")
        firma = base64.b64decode(saved.firma)

    ctx = Ctx(vessel=vessel, call=call, agency=agency, dates=dates, serenos=serenos,
              migra_modo="SALIDA" if data.get("migra_modo") == "SALIDA" else "ENTRADA",
              pna_modo="SALIDA" if data.get("pna_modo") == "SALIDA" else "ENTRADA",
              certificados=vessel.get("certificados") or {}, firma=firma, firma_keys=firma_keys)
    name, content, mime = build_many(order, ctx, single_workbook=data.get("download_mode") == "libro")
    ascii_name = name.encode("ascii", "ignore").decode("ascii").strip() or "documentacion"
    headers = {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"}
    if call_id:
        headers["X-Escala-Id"] = str(call_id)
    return Response(content=content, media_type=mime, headers=headers)
