"""Vouchers (Service Certificate): se completan al irse el barco, uno por agencia a facturar."""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import quote

from .. import vouchers_lib as lib
from ..auth import current_user
from ..calendario import conjuntos
from ..database import get_db
from ..docgen import voucher as vch
from ..models import Client, OperatedVessel, User, Voucher, VoucherConcepto
from ..proforma_final import DIAS, tipo_dia
from ..templating import templates

router = APIRouter(prefix="/vouchers")

TIPO_DIA_TXT = {"SEMANA": "Día hábil", "SABADO": "Sábado", "DOMINGO": "Domingo", "FERIADO": "Feriado", "NO_LABORABLE": "Día no laborable"}


def _estibas(db: Session) -> set[str]:
    return {c.name.strip().lower() for c in db.scalars(select(Client).where(Client.client_type == "ESTIBA"))}


def _crear(db: Session, o: OperatedVessel, user: User) -> Voucher:
    """Borrador con todos los conceptos tildados; lo tiene que completar quien cargo los datos del barco."""
    if o.voucher is not None:
        return o.voucher
    formato = vch.formato_para(o.principal)
    v = Voucher(
        operated_id=o.id, formato=formato, buque=(o.vessel_name or "").strip(), agencia=(o.principal or "").strip(),
        fecha=lib.fecha_por_defecto(o), items=json.dumps(vch.estado_inicial(formato, o.servicio)),
        creado_por=user.username, bloqueo_user=o.completado_por or user.username,
    )
    db.add(v)
    db.commit()
    return v


def _siguiente(db: Session, user: User, excluir: int) -> str:
    """A donde ir despues de terminar un voucher: el proximo que quede por completar (primero los del mismo usuario)."""
    pend = [o for o in lib.pendientes(db) if not (o.voucher and o.voucher.id == excluir)]
    pend.sort(key=lambda o: (o.completado_por != user.username, o.id))
    if pend:
        return f"/vouchers/nuevo?operated_id={pend[0].id}"
    return "/vouchers?listo=1"


def _con_permiso(db: Session, vid: int) -> Voucher | None:
    return db.get(Voucher, vid)


# ------------------------------------------------------------------ lista --
@router.get("", response_class=HTMLResponse)
def lista(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    vouchers = list(db.scalars(select(Voucher).order_by(Voucher.id.desc()).limit(200)))
    pendientes = lib.pendientes(db)
    filas = [{
        "v": v, "head_tally": lib.lleva_head_tally(v), "turnos_ok": lib.turnos_confirmados(v),
        "incompleto": lib.incompleto(v),
    } for v in vouchers]
    return templates.TemplateResponse(request, "vouchers/lista.html", {
        "user": user, "filas": filas, "pendientes": pendientes, "listo": request.query_params.get("listo") == "1",
        "bloqueo": lib.bloqueo_activo(db),
    })


@router.get("/nuevo")
def nuevo(operated_id: int = 0, db: Session = Depends(get_db), user: User = Depends(current_user)):
    o = db.get(OperatedVessel, operated_id)
    if not o or not lib.es_fila_de_agencia(o, _estibas(db)):
        return RedirectResponse("/vouchers", status_code=303)
    v = _crear(db, o, user)
    return RedirectResponse(f"/vouchers/{v.id}", status_code=303)


# ----------------------------------------------------------------- editar --
@router.get("/{vid}", response_class=HTMLResponse)
def editar(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return RedirectResponse("/vouchers", status_code=303)
    memoria = [{"id": m.id, "texto": m.texto} for m in db.scalars(
        select(VoucherConcepto).order_by(VoucherConcepto.usos.desc(), VoucherConcepto.texto).limit(40))]
    return templates.TemplateResponse(request, "vouchers/editar.html", {
        "user": user, "v": v, "catalogo": vch.catalogo(v.formato, v.servicio), "estado": vch.normalizar(v.formato, lib.estado_voucher(v), v.servicio),
        "memoria": memoria, "lineas": vch.lineas(v.formato, lib.estado_voucher(v), v.servicio), "servicio": v.servicio,
        "head_tally": lib.lleva_head_tally(v), "bloqueado": lib.voucher_bloqueante(db, user.username) is not None,
        "bloqueo_activo": lib.bloqueo_activo(db),
    })


def _leer(v: Voucher, data: dict) -> tuple[dict, str]:
    estado = vch.normalizar(v.formato, data.get("items"), v.servicio)
    try:
        fecha = date.fromisoformat(str(data.get("fecha") or "")).isoformat()
    except ValueError:
        fecha = v.fecha
    return estado, fecha


def _recordar(db: Session, estado: dict, user: User, *, contar: bool) -> None:
    """Los conceptos agregados a mano quedan en la memoria para ofrecerlos la proxima vez."""
    for e in estado["extra"]:
        m = db.scalar(select(VoucherConcepto).where(VoucherConcepto.texto == e["t"]))
        if m is None:
            m = VoucherConcepto(texto=e["t"], usos=0, creado_por=user.username)
            db.add(m)
        if contar and e["on"]:
            m.usos = (m.usos or 0) + 1


@router.post("/{vid}/vista")
async def vista(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return JSONResponse({"error": "no existe"}, status_code=404)
    data = await request.json()
    estado, _ = _leer(v, data)
    return {"lineas": vch.lineas(v.formato, estado, v.servicio), "head_tally": vch.tiene(v.formato, estado, "head_tally", v.servicio),
            "shore_gangway": vch.tiene(v.formato, estado, "shore_gangway", v.servicio)}


@router.post("/{vid}/guardar")
async def guardar(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return JSONResponse({"error": "no existe"}, status_code=404)
    estado, fecha = _leer(v, await request.json())
    v.items, v.fecha = json.dumps(estado, ensure_ascii=False), fecha
    v.actualizado_por, v.actualizado_en = user.username, datetime.utcnow()
    _recordar(db, estado, user, contar=False)
    db.commit()
    return {"ok": True}


@router.post("/{vid}/enviar")
async def enviar(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return JSONResponse({"error": "no existe"}, status_code=404)
    estado, fecha = _leer(v, await request.json())
    if not vch.lineas(v.formato, estado, v.servicio):
        return JSONResponse({"ok": False, "error": "Tildá al menos un concepto antes de enviar."}, status_code=400)
    primera_vez = v.estado != "ENVIADO"
    v.items, v.fecha = json.dumps(estado, ensure_ascii=False), fecha
    v.estado, v.enviado_por, v.enviado_en = "ENVIADO", user.username, datetime.utcnow()
    v.actualizado_por, v.actualizado_en = user.username, datetime.utcnow()
    _recordar(db, estado, user, contar=primera_vez)
    db.commit()
    if lib.lleva_head_tally(v) and not lib.turnos_confirmados(v):
        return {"ok": True, "next": f"/vouchers/{v.id}/turnos"}
    return {"ok": True, "next": _siguiente(db, user, v.id)}


@router.get("/{vid}/descargar")
def descargar(vid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return RedirectResponse("/vouchers", status_code=303)
    try:
        fecha = date.fromisoformat(v.fecha)
    except ValueError:
        fecha = date.today()
    contenido, nombre, mime = vch.generar(v.formato, v.buque, v.agencia, lib.estado_voucher(v), fecha, v.servicio)
    return Response(content=contenido, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}"})


@router.get("/{vid}/turno-info")
def turno_info(vid: int, fecha: str = "", turno: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Datos de un turno extra que se agrega a mano (dia de la semana y tipo de dia), para mostrarlo en la tabla."""
    v = _con_permiso(db, vid)
    o = db.get(OperatedVessel, v.operated_id) if v else None
    validos = lib.turnos_validos(o.inicio_operacion, o.fin_operacion, o.amarre) if o else {}
    t = validos.get((fecha, turno))
    if not t:
        return JSONResponse({"ok": False, "error": "Ese turno queda fuera del período del barco."}, status_code=400)
    feriados, no_lab = conjuntos(db)
    d = date.fromisoformat(fecha)
    tipo = tipo_dia(d, feriados, no_lab)
    return {"ok": True, "dia": DIAS[d.weekday()], "tipo": tipo, "tipo_txt": TIPO_DIA_TXT[tipo]}


@router.get("/{vid}/tally")
def descargar_tally(vid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Voucher del Head Tally (Excel): los turnos elegidos con su horario y actividad."""
    v = _con_permiso(db, vid)
    if not v:
        return RedirectResponse("/vouchers", status_code=303)
    if not lib.turnos_confirmados(v):
        return RedirectResponse(f"/vouchers/{v.id}/turnos", status_code=303)
    try:
        turnos_elegidos = [t for t in json.loads(v.turnos) if isinstance(t, dict)]
    except ValueError:
        turnos_elegidos = []
    nombre = f"VOUCHER TALLY {v.buque}".strip()
    return Response(
        content=vch.tally(v.buque, turnos_elegidos),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}.xlsx"},
    )


@router.post("/conceptos/{cid}/borrar")
def olvidar_concepto(cid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(VoucherConcepto, cid)
    if m:
        db.delete(m)
        db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- turnos --
@router.get("/{vid}/turnos", response_class=HTMLResponse)
def turnos(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return RedirectResponse("/vouchers", status_code=303)
    o = db.get(OperatedVessel, v.operated_id)
    posibles = lib.turnos_posibles(o.inicio_operacion, o.fin_operacion, o.amarre) if o else []
    elegidos: dict[tuple[str, str], str] = {}
    if lib.turnos_confirmados(v):
        try:
            elegidos = {(t["fecha"], t["turno"]): t.get("act") or "LDG" for t in json.loads(v.turnos)}
        except (ValueError, KeyError, TypeError):
            elegidos = {}
    feriados, no_lab = conjuntos(db)
    # Se muestran los 4 turnos de cada dia del periodo (desde el dia anterior al amarre hasta el dia del fin), con su rango
    # horario, para tildar cualquiera. Vienen tildados los que se cruzan con el horario; los otros quedan para elegir
    # (por ejemplo el del mooring). Los extra ya guardados que caen fuera del periodo tambien se muestran.
    en_horario = {(t["fecha"], t["turno"]) for t in posibles}
    validos = lib.turnos_validos(o.inicio_operacion, o.fin_operacion, o.amarre) if o else {}
    a, b = lib._rango(o.inicio_operacion, o.fin_operacion, o.amarre) if o else (None, None)
    ultimo_dia = b.date().isoformat() if b else ""
    visibles = {k: t for k, t in validos.items() if t["fecha"] <= ultimo_dia}
    for k in elegidos:
        if k in validos and k not in visibles:
            visibles[k] = validos[k]
    todos = sorted(visibles.values(), key=lambda t: (t["fecha"], [n for n, _, _ in lib.TURNOS].index(t["turno"])))
    confirmado = lib.turnos_confirmados(v)
    filas = []
    for t in todos:
        k = (t["fecha"], t["turno"])
        d = date.fromisoformat(t["fecha"])
        tipo = tipo_dia(d, feriados, no_lab)
        dentro = k in en_horario
        on = (k in elegidos) if confirmado else dentro
        act = elegidos.get(k) or "LDG"
        if not confirmado and o:
            # por defecto: MOORING antes del amarre; BERTHING hasta que arranca la carga; LDG despues
            if o.amarre and t["hasta"] <= o.amarre:
                act = "MOORING"
            elif (o.amarre and t["desde"] <= o.amarre < t["hasta"]) or (o.inicio_operacion and t["hasta"] <= o.inicio_operacion):
                act = "BERTHING"
        filas.append({**t, "dia": DIAS[d.weekday()], "tipo": tipo, "tipo_txt": TIPO_DIA_TXT[tipo], "on": on, "act": act,
                      "en_horario": dentro, "extra": on and not dentro})
    return templates.TemplateResponse(request, "vouchers/turnos.html", {
        "user": user, "v": v, "o": o, "filas": filas, "confirmado": lib.turnos_confirmados(v),
        "actividades": vch.ACTIVIDADES_TALLY,
    })


@router.post("/{vid}/turnos")
async def guardar_turnos(vid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = _con_permiso(db, vid)
    if not v:
        return JSONResponse({"error": "no existe"}, status_code=404)
    o = db.get(OperatedVessel, v.operated_id)
    validos = set(lib.turnos_validos(o.inicio_operacion, o.fin_operacion, o.amarre)) if o else set()
    data = await request.json()
    elegidos = []
    for t in (data.get("turnos") if isinstance(data.get("turnos"), list) else []):
        if isinstance(t, dict) and (t.get("fecha"), t.get("turno")) in validos and (t["fecha"], t["turno"]) not in {(e["fecha"], e["turno"]) for e in elegidos}:
            act = " ".join(str(t.get("act") or "").split())[:30].upper() or "LDG"
            elegidos.append({"fecha": t["fecha"], "turno": t["turno"], "act": act})
    v.turnos = json.dumps(elegidos)
    v.actualizado_por, v.actualizado_en = user.username, datetime.utcnow()
    db.commit()
    return {"ok": True, "next": _siguiente(db, user, v.id)}
