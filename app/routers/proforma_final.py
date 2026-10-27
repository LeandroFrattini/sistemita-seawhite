"""Administracion: proforma final (asistente), agencias a facturar (fee y cargas sociales) y calendario de feriados."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import proforma_final as pf
from ..calendario import TIPOS as TIPOS_CALENDARIO
from ..auth import GATE_COOKIE, GATE_MAX_AGE, administracion_required, datos_reservados_required, make_gate_cookie, verify_password
from ..database import get_db
from ..docgen.fechas import parse_number
from ..docgen import voucher as vch
from ..models import AgenciaFee, AppSetting, Client, DocCall, DocVessel, Feriado, OperatedVessel, ProformaPilotageTramo, Sereno, TarifaPersonal, User, Encargado, EncargadoTope
from .. import practicaje as pract
from .. import lds as lds_calc
from .. import chequeo, encargados as enc, migraciones, personal, serenos_padron, serenos_pagos
from ..docgen import resumen_sereno_xlsx
from .. import muelle as muelle_calc
from ..vouchers_lib import estado_voucher
from ..proforma_fees_2026 import buscar_en_lista, sugerir_monto
from ..proformador_calc import get_param
from ..security import is_https
from ..templating import templates

router = APIRouter(prefix="/administracion")
log = logging.getLogger("proforma_final")

CARGAS_SERENOS_KEY = "proforma_final_cargas_serenos_general"
CARGAS_TALLY_KEY = "proforma_final_cargas_tally_general"
_CARGAS_VIEJA_KEY = "proforma_final_cargas_sociales_general"  # primera version: un solo porcentaje


def _setting_float(db: Session, key: str) -> float | None:
    row = db.get(AppSetting, key)
    if not row:
        return None
    try:
        return float(row.value)
    except ValueError:
        return None


def cargas_generales(db: Session) -> tuple[float, float]:
    """(serenos, head tally) generales: los que usa toda agencia sin porcentaje propio."""
    serenos = _setting_float(db, CARGAS_SERENOS_KEY)
    if serenos is None:
        serenos = _setting_float(db, _CARGAS_VIEJA_KEY) or 0.0
    tally = _setting_float(db, CARGAS_TALLY_KEY)
    return serenos, (tally if tally is not None else serenos)


def _set_setting(db: Session, key: str, value: float) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = str(value)
    else:
        db.add(AppSetting(key=key, value=str(value)))


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
    return n if 0 <= n <= 1000 else None


def _usd(raw: str) -> float:
    try:
        n = float((raw or "").strip().replace(",", "."))
    except ValueError:
        return 0.0
    return n if 0 <= n <= 10_000_000 else 0.0


# ------------------------------------------------------------ asistente ----
def _n(txt) -> float:
    v = parse_number(str(txt or ""))
    return float(v) if v is not None else 0


def _calado_historial(call: DocCall | None) -> float:
    """Calado de entrada en PIES a partir del ultimo 'Calados Entrada' del Generador de documentos (viene en metros)."""
    if call is None:
        return 0
    try:
        d = json.loads(call.data or "{}")
    except ValueError:
        return 0
    m = _n(d.get("calado_max")) or max(_n(d.get("calado_proa")), _n(d.get("calado_popa")))
    return round(m * pract.PIES_POR_METRO, 1) if m else 0


def _particulares(dv: DocVessel | None, call: DocCall | None = None) -> dict:
    """Datos del buque del historial (por IMO): TRN, TRB, medidas, bandera y calado de entrada; vacios para completar a mano."""
    ce = _calado_historial(call)
    return {
        "trn": _n(dv.trn) if dv else 0, "trb": _n(dv.trb) if dv else 0, "eslora": _n(dv.eslora) if dv else 0,
        "manga": _n(dv.manga) if dv else 0, "puntal": _n(dv.puntal) if dv else 0, "bandera": (dv.flag or "") if dv else "",
        "calado_entrada": ce, "calado_salida": 0,
        "trn_historial": bool(dv and _n(dv.trn)), "calado_historial": bool(ce),
    }


def _del_voucher(o: OperatedVessel) -> dict:
    """Lo que se uso segun el voucher del barco (conceptos tildados y turnos de Head Tally), si ya se armo."""
    v = o.voucher
    if v is None:
        return {"servicios": [], "turnos": [], "hay_voucher": False, "mig_voucher": {}}
    try:
        turnos = [t for t in json.loads(v.turnos or "[]") if isinstance(t, dict)]
    except ValueError:
        turnos = []
    servicios = vch.lineas(v.formato, estado_voucher(v))
    return {"servicios": servicios, "turnos": turnos, "hay_voucher": True, "voucher_enviado": v.estado == "ENVIADO",
            "mig_voucher": migraciones.desde_voucher(servicios)}


def _barcos_a_proformar(db: Session, limite: int = 300) -> list[dict]:
    """Barcos operados (uno por agencia a facturar) para elegir en la proforma: los mas recientes primero.
    Las estibas no se proforman. Trae los datos que Operaciones completo al irse el barco."""
    clientes = {c.name.strip().lower(): c for c in db.scalars(select(Client))}
    historial = {d.imo: d for d in db.scalars(select(DocVessel))}  # datos del buque ya cargados en el Generador de documentos
    escalas: dict[str, DocCall] = {}  # la ultima escala de cada barco (para el calado de entrada)
    for c in db.scalars(select(DocCall).order_by(DocCall.updated_at.desc())):
        escalas.setdefault(c.imo, c)
    out = []
    for o in db.scalars(select(OperatedVessel).order_by(OperatedVessel.operated_at.desc(), OperatedVessel.id.desc()).limit(limite * 2)):
        cli = clientes.get((o.principal or "").strip().lower())
        if cli is not None and cli.client_type == "ESTIBA":
            continue
        out.append({
            "id": o.id, "nombre": (o.vessel_name or "").strip(), "imo": o.imo or "",
            "sitio": o.berth_label or o.terminal_code or "", "agencia": o.principal or "",
            "agencia_id": cli.id if cli is not None else None,
            "amarre": o.amarre or "", "inicio": o.inicio_operacion or "", "fin": o.fin_operacion or "", "zarpe": o.zarpe or "",
            "cantidad": (o.cantidad_operada or o.quantity or "").strip(),
            "carga": (o.grade or "").strip().upper(), "shipper": (o.shipper or "").strip().upper(),
            **_particulares(historial.get((o.imo or "").strip()), escalas.get((o.imo or "").strip())),
            **_del_voucher(o),
            "completo": bool(o.amarre and o.inicio_operacion and o.fin_operacion and o.zarpe and o.cantidad_operada),
        })
        if len(out) >= limite:
            break
    return out


@router.get("/proforma-final", response_class=HTMLResponse)
def proforma_final_page(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    g_ser, g_tal = cargas_generales(db)
    agencias = [{
        "id": c.id, "nombre": c.name,
        "serenos_pct": c.cargas_sociales_pct if c.cargas_sociales_pct is not None else g_ser,
        "tally_pct": c.cargas_tally_pct if c.cargas_tally_pct is not None else g_tal,
        "fees": [{"texto": f.texto, "monto_usd": f.monto_usd, "revisar": f.revisar} for f in c.fees],
    } for c in _agencias(db)]
    return templates.TemplateResponse(request, "administracion/proforma_final.html", {
        "user": user, "agencias": agencias, "barcos": _barcos_a_proformar(db), "pasos": pf.PASOS,
        "hoy": date.today().isoformat(),
        "aduana_usd": get_param(db, "aduana_habilitacion_usd", pf.ADUANA_USD),
        "law_pct": ("%g" % get_param(db, "law_25413_pct", chequeo.LAW_PCT)).replace(".", ","),
        "version": (os.environ.get("RENDER_GIT_COMMIT") or "local")[:7],
        # tramos de calado del practicaje (en pies) para mostrarlos tambien en metros
        "serenos_padron": [s.nombre for s in db.scalars(select(Sereno).order_by(Sereno.nombre))],
        "encargados_padron": [e.nombre for e in db.scalars(select(Encargado).order_by(Encargado.nombre))],
        "at_orders_ars": get_param(db, "encargados_at_orders_ars", enc.AT_ORDERS_DEFECTO),
        "tramos_calado": [{"hasta": t.hasta_pies, "coef": t.valor_usd}
                          for t in db.scalars(select(ProformaPilotageTramo).order_by(ProformaPilotageTramo.orden))],
    })


@router.post("/proforma-final/practicaje")
async def proforma_final_practicaje(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Practicaje IN y OUT con el desglose (misma formula y tablas que el proformador inicial)."""
    b = pf.clean_buque(await request.json())
    return pract.calcular(db, b["eslora"], b["manga"], b["puntal"], b["calado_entrada"], b["calado_salida"])


@router.post("/proforma-final/muelle")
async def proforma_final_muelle(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Uso de muelle, fondeadero y vias navegables con el desglose de dias por bloques de 8 horas."""
    d = await request.json()
    d = d if isinstance(d, dict) else {}
    fechas = {k: pf._datetime(d.get(k)) for k in ("entrada", "salida", "fondeo_entrada", "fondeo_salida", "inicio")}
    return muelle_calc.calcular(
        db, trn=pf._num(d.get("trn"), 1_000_000), cantidad=pf._num(d.get("cantidad"), 100_000_000), fondeo=bool(d.get("fondeo")),
        solo_bunker=bool(d.get("solo_bunker")), factor_via=pf._num(d.get("factor"), 10) or 1.0,
        entrada=fechas["entrada"], salida=fechas["salida"], fondeo_entrada=fechas["fondeo_entrada"], fondeo_salida=fechas["fondeo_salida"],
        inicio=fechas["inicio"], aplicar_beneficio=d.get("aplicar_beneficio") is not False,
    )


@router.post("/proforma-final/lds")
async def proforma_final_lds(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Amarre y desamarre de Lanchas del Sur (con recargo por dia y hora) y escala si lleva SHORE GANGWAY."""
    d = await request.json()
    d = d if isinstance(d, dict) else {}
    return lds_calc.calcular(
        db, eslora=pf._num(d.get("eslora"), 1000), amarre=pf._datetime(d.get("amarre")), desamarre=pf._datetime(d.get("desamarre")),
        lanchas_amarre=int(pf._num(d.get("lanchas_amarre"), 4)), lanchas_desamarre=int(pf._num(d.get("lanchas_desamarre"), 4)),
        escala=bool(d.get("escala")), escala_dias=int(pf._num(d.get("escala_dias"), 365)),
        draft=bool(d.get("draft")), draft_momento=pf._datetime(d.get("draft_momento")),
    )


def _ref_fecha(d: dict) -> date | None:
    try:
        return date.fromisoformat(str(d.get("ref") or "")[:10])
    except ValueError:
        return None


@router.post("/proforma-final/chequeo")
async def proforma_final_chequeo(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Chequeo general: la proforma consolidada (renglones en dolares y pesos, LAW NR 25413, lo que va por cuenta del armador)."""
    state = pf.clean_state(await request.json())
    return chequeo.armar(db, state)


@router.post("/proforma-final/migraciones")
async def proforma_final_migraciones(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Migraciones IN/OUT, taxis y free pratique (segun el TRN): importe de cada concepto tildado y totales."""
    d = await request.json()
    d = d if isinstance(d, dict) else {}
    m = migraciones.clean({"items": d.get("items")})
    return migraciones.calcular(db, trn=pf._num(d.get("trn"), 1_000_000), items=m["items"], dolar=pf._num(d.get("dolar"), 1_000_000))


@router.post("/proforma-final/tally")
async def proforma_final_tally(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Tally (Head Tally): escalon de cada turno, precio por categoria de carga, cargas sociales y total en pesos y dolares."""
    d = await request.json()
    d = d if isinstance(d, dict) else {}
    t = personal.clean_tally({"turnos": d.get("turnos"), "precios": d.get("precios"), "categoria": d.get("categoria")})
    return personal.calcular_tally(db, categoria=t["categoria"], turnos=t["turnos"], precios=t["precios"], pct=pf._num(d.get("pct"), 1000),
                                   dolar=pf._num(d.get("dolar"), 1_000_000), ref=_ref_fecha(d))


@router.post("/proforma-final/serenos")
async def proforma_final_serenos(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Serenos: turnos desde el amarre al zarpe (o los que se cargaron), tarifa por dia/hora/categoria, cargas y viaticos."""
    d = await request.json()
    d = d if isinstance(d, dict) else {}
    armado = d.get("turnos") is not None
    s = personal.clean_serenos({"turnos": d.get("turnos"), "categoria": d.get("categoria"), "viatico": d.get("viatico"), "viatico_precio": d.get("viatico_precio")})
    return personal.calcular_serenos(db, categoria=s["categoria"], viatico=s["viatico"], viatico_precio=s["viatico_precio"], turnos=s["turnos"] if armado else None,
                                     amarre=pf._datetime(d.get("amarre")), zarpe=pf._datetime(d.get("zarpe")), pct=pf._num(d.get("pct"), 1000),
                                     dolar=pf._num(d.get("dolar"), 1_000_000), ref=_ref_fecha(d))


@router.post("/proforma-final/excel")
async def proforma_final_excel(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    state = pf.clean_state(await request.json())
    nombre = f"Proforma final - {state['agencia']['nombre'] or 'sin agencia'} - {date.today().strftime('%d.%m.%Y')}.xlsx"
    headers = {"X-Filename": nombre.encode("ascii", "ignore").decode() or "Proforma final.xlsx"}
    try:
        contenido = pf.build_excel(state, chequeo.armar(db, state), db)
    except Exception:
        # que nadie se quede sin poder sacar la proforma: se baja el resumen simple y queda el error en el registro
        log.exception("proforma final: no se pudo armar el Excel con el formato de las proformas (usuario=%s, buque=%s)", user.username, state["buque"]["nombre"])
        contenido = pf.build_excel(state)
        headers["X-Aviso"] = "version-simplificada"
    return Response(content=contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@router.post("/proforma-final/excel-serenos")
async def proforma_final_excel_serenos(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Excel aparte con los recibos de los serenos (se arma con lo cargado en el paso 9). Si falta algo, dice que es."""
    state = await request.json()
    try:
        contenido, nombre = pf.build_excel_serenos(state, db, user.username)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)
    except Exception:
        log.exception("proforma final: no se pudo armar el Excel de serenos (usuario=%s)", user.username)
        return JSONResponse({"ok": False, "error": "No se pudo armar el Excel de serenos. Avisale al administrador del sistema."}, status_code=500)
    return Response(content=contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"X-Filename": nombre.encode("ascii", "ignore").decode() or "SERENOS.xlsx"})


@router.post("/proforma-final/excel-encargados")
async def proforma_final_excel_encargados(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Excel aparte de encargados (declaracion jurada del Head Tally), con el tope mensual de aportes. Si falta algo, dice que es."""
    state = await request.json()
    try:
        contenido, nombre = pf.build_excel_encargados(state, db, user.username)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=422)
    except Exception:
        log.exception("proforma final: no se pudo armar el Excel de encargados (usuario=%s)", user.username)
        return JSONResponse({"ok": False, "error": "No se pudo armar el Excel de encargados. Avisale al administrador del sistema."}, status_code=500)
    return Response(content=contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"X-Filename": nombre.encode("ascii", "ignore").decode() or "ENCARGADOS.xlsx"})


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
    g_ser, g_tal = cargas_generales(db)
    agencias = _agencias(db)
    sin_fee = [c.name for c in agencias if not c.fees]
    return templates.TemplateResponse(request, "administracion/agencias.html", {
        "user": user, "agencias": agencias, "g_ser": g_ser, "g_tal": g_tal, "sin_fee": sin_fee,
        "guardado": request.query_params.get("ok") == "1", "cargadas": request.query_params.get("cargadas", ""),
    })


@router.post("/agencias/guardar")
async def agencias_guardar(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    form = await request.form()
    _set_setting(db, CARGAS_SERENOS_KEY, _pct(str(form.get("g_serenos", ""))) or 0.0)
    _set_setting(db, CARGAS_TALLY_KEY, _pct(str(form.get("g_tally", ""))) or 0.0)
    for c in _agencias(db):
        c.cargas_sociales_pct = _pct(str(form.get(f"serenos_{c.id}", "")))  # vacio = usa el general
        c.cargas_tally_pct = _pct(str(form.get(f"tally_{c.id}", "")))
        # los renglones de fee se rearman en el orden en que llegan; un renglon sin texto se descarta
        c.fees.clear()
        patron = re.compile(rf"fee_{c.id}_(\d+)_t")
        for k in sorted(int(m.group(1)) for m in (patron.fullmatch(key) for key in form.keys()) if m):
            texto = " ".join(str(form.get(f"fee_{c.id}_{k}_t", "")).split())[:200]
            if texto:
                c.fees.append(AgenciaFee(
                    texto=texto, monto_usd=_usd(str(form.get(f"fee_{c.id}_{k}_m", ""))),
                    revisar=form.get(f"fee_{c.id}_{k}_r") == "on", orden=len(c.fees),
                ))
    db.commit()
    return RedirectResponse("/administracion/agencias?ok=1", status_code=303)


@router.post("/agencias/cargar-lista-2026")
def agencias_cargar_lista(db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Carga los fee y cargas sociales de la lista "Clientes 2026" en las agencias que todavia no tienen fee
    (las que ya tienen renglones no se tocan). Los montos poco claros quedan marcados para revisar."""
    cargadas = []
    for c in _agencias(db):
        entrada = buscar_en_lista(c.name)
        if not entrada or c.fees:
            continue
        _, serenos, tally, renglones = entrada
        for i, texto in enumerate(renglones):
            monto, revisar = sugerir_monto(texto)
            c.fees.append(AgenciaFee(texto=texto, monto_usd=monto, revisar=revisar, orden=i))
        if c.cargas_sociales_pct is None:
            c.cargas_sociales_pct = serenos
        if c.cargas_tally_pct is None:
            c.cargas_tally_pct = tally
        cargadas.append(c.name)
    db.commit()
    return RedirectResponse(f"/administracion/agencias?ok=1&cargadas={len(cargadas)}", status_code=303)


# ------------------------------------------------------- tarifas de personal --
def _numero_ar(txt: str) -> float | None:
    """'193.493,56' o '193493,56' o '193493.56' -> 193493.56 (None si no es un numero)."""
    t = (txt or "").strip().replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        n = float(t)
    except ValueError:
        return None
    return round(n, 2) if 0 <= n <= 1e10 else None


# ------------------------------------------- acceso a las pantallas con importes ----
def _destino_seguro(txt: str) -> str:
    """Adonde se vuelve despues de poner la contraseña: solo pantallas de Administracion de este mismo sitio."""
    t = str(txt or "")
    return t if t.startswith("/administracion/") and not t.startswith("//") and "\\" not in t and "\n" not in t and "\r" not in t else "/administracion"


@router.get("/acceso-datos", response_class=HTMLResponse)
def acceso_datos_form(request: Request, next: str = "", user: User = Depends(administracion_required)):
    return templates.TemplateResponse(request, "administracion/acceso_datos.html", {"user": user, "next": _destino_seguro(next), "error": ""})


@router.post("/acceso-datos")
def acceso_datos_enviar(request: Request, password: str = Form(""), next: str = Form(""), user: User = Depends(administracion_required)):
    from ..security import client_ip, ip_limiter, lock_minutes, user_limiter

    destino = _destino_seguro(next)
    ukey, ikey = f"gate:{user.username.lower()}", f"gate-ip:{client_ip(request)}"
    espera = max(user_limiter.remaining_lock(ukey), ip_limiter.remaining_lock(ikey))
    if espera:
        msg = f"Demasiados intentos fallidos. Probá de nuevo en {lock_minutes(espera)} min."
        return templates.TemplateResponse(request, "administracion/acceso_datos.html", {"user": user, "next": destino, "error": msg}, status_code=429)
    if not password or not verify_password(password, user.password_hash):
        user_limiter.fail(ukey)
        ip_limiter.fail(ikey)
        log.warning("acceso a datos reservados: contraseña incorrecta usuario=%s ip=%s", user.username, client_ip(request))
        return templates.TemplateResponse(request, "administracion/acceso_datos.html", {"user": user, "next": destino, "error": "La contraseña no es correcta."}, status_code=401)
    user_limiter.reset(ukey)
    log.info("acceso a datos reservados ok usuario=%s", user.username)
    resp = RedirectResponse(destino, status_code=303)
    resp.set_cookie(GATE_COOKIE, make_gate_cookie(user), httponly=True, samesite="lax", secure=is_https(request), max_age=GATE_MAX_AGE)
    return resp


# -------------------------------------------------------------- serenos ----
@router.get("/serenos", response_class=HTMLResponse)
def serenos_page(request: Request, db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    return templates.TemplateResponse(request, "administracion/serenos.html", {
        "user": user, "serenos": db.scalars(select(Sereno).order_by(Sereno.nombre)).all(),
        "ok": request.query_params.get("ok", ""), "error": request.query_params.get("error", ""),
        "nombre_en_error": request.query_params.get("n", ""), "cuil_en_error": request.query_params.get("c", ""),
    })


def _datos_sereno(db: Session, nombre: str, cuil: str, propio_id: int | None, cuil_actual: str = ""):
    """Valida nombre y CUIL; devuelve (nombre, cuil, error)."""
    nombre = serenos_padron.limpiar_nombre(nombre)
    if not nombre:
        return None, None, "nombre"
    c = serenos_padron.normalizar_cuil(cuil)
    if not c:
        return None, None, "cuil"
    if c != cuil_actual and not serenos_padron.cuil_valido(c.replace("-", "")):  # un CUIL ya cargado que no se toca no se vuelve a exigir
        return None, None, "cuil_digito"  # el digito verificador no cierra: casi seguro un error de tipeo
    otro = db.scalar(select(Sereno).where(Sereno.cuil == c))
    if otro is not None and otro.id != propio_id:
        return None, None, "repetido"
    return nombre, c, None


@router.get("/serenos/{sereno_id}", response_class=HTMLResponse)
def sereno_resumen_page(sereno_id: int, request: Request, mes: str = "", db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    s = db.get(Sereno, sereno_id)
    if s is None:
        return RedirectResponse("/administracion/serenos?error=no_existe", status_code=303)
    meses = serenos_pagos.meses_con_pagos(db, s)
    todos = mes == "todos"
    elegido = "" if todos else (mes if mes in meses else (meses[0] if meses else ""))
    return templates.TemplateResponse(request, "administracion/sereno_resumen.html", {
        "user": user, "s": s, "meses": meses, "mes": elegido, "todos": todos or not meses, "r": serenos_pagos.resumen(db, s, elegido),
    })


@router.get("/serenos/{sereno_id}/excel")
def sereno_resumen_excel(sereno_id: int, mes: str = "", db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    s = db.get(Sereno, sereno_id)
    if s is None:
        return RedirectResponse("/administracion/serenos?error=no_existe", status_code=303)
    m = enc.mes_valido(mes)
    r = serenos_pagos.resumen(db, s, m)
    datos = resumen_sereno_xlsx.generar(nombre=s.nombre, cuil=s.cuil, mes=m, filas=r["filas"], hoy=date.today())
    nombre = re.sub(r"[^A-Za-z0-9 ._-]", "", f"RESUMEN {s.nombre} {m or 'todos los meses'}").strip() + ".xlsx"
    return Response(content=datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/serenos/{sereno_id}/quitar-barco")
def sereno_quitar_barco(sereno_id: int, clave: str = Form(""), mes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    s = db.get(Sereno, sereno_id)
    if s is not None and clave:
        serenos_pagos.quitar(db, s, clave)
    return RedirectResponse(f"/administracion/serenos/{sereno_id}?mes={mes or 'todos'}", status_code=303)


@router.post("/serenos/nuevo")
def sereno_nuevo(nombre: str = Form(""), cuil: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    n, c, err = _datos_sereno(db, nombre, cuil, None)
    if err:
        from urllib.parse import quote
        return RedirectResponse(f"/administracion/serenos?error={err}&n={quote(nombre[:60])}&c={quote(cuil[:20])}", status_code=303)
    db.add(Sereno(nombre=n, cuil=c))
    db.commit()
    return RedirectResponse("/administracion/serenos?ok=agregado", status_code=303)


@router.post("/serenos/{sereno_id}/guardar")
def sereno_guardar(sereno_id: int, nombre: str = Form(""), cuil: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    s = db.get(Sereno, sereno_id)
    if s is None:
        return RedirectResponse("/administracion/serenos?error=no_existe", status_code=303)
    n, c, err = _datos_sereno(db, nombre, cuil, s.id, s.cuil)
    if err:
        return RedirectResponse(f"/administracion/serenos?error={err}_{s.id}", status_code=303)
    s.nombre, s.cuil = n, c
    db.commit()
    return RedirectResponse("/administracion/serenos?ok=guardado", status_code=303)


@router.post("/serenos/{sereno_id}/eliminar")
def sereno_eliminar(sereno_id: int, db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    s = db.get(Sereno, sereno_id)
    if s is not None:
        db.delete(s)
        db.commit()
    return RedirectResponse("/administracion/serenos?ok=eliminado", status_code=303)


# ----------------------------------------------------------- encargados ----
def _monto(txt) -> float | None:
    """'1.234.567,89', '1234567,89' o '1234567.89' -> 1234567.89; None si no es un monto positivo."""
    t = re.sub(r"[\s$]", "", str(txt or ""))
    if not t:
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in t:
        t = t.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return round(v, 2) if 0 < v < 1e12 else None


@router.get("/encargados", response_class=HTMLResponse)
def encargados_page(request: Request, mes: str = "", db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    mes = enc.mes_valido(mes) or date.today().strftime("%Y-%m")
    y, m = int(mes[:4]), int(mes[5:7])
    ant, sig = (f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"), (f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}")
    return templates.TemplateResponse(request, "administracion/encargados.html", {
        "user": user, "mes": mes, "mes_ant": ant, "mes_sig": sig, "estado": enc.estado_mes(db, mes), "historial": enc.historial_topes(db),
        "ok": request.query_params.get("ok", ""), "error": request.query_params.get("error", ""),
    })


def _datos_encargado(db: Session, nombre: str, cuil: str, propio_id: int | None, cuil_actual: str = ""):
    nombre = enc.limpiar_nombre(nombre)
    if not nombre:
        return None, None, "nombre"
    c = serenos_padron.normalizar_cuil(cuil)
    if not c:
        return None, None, "cuil"
    if c != cuil_actual and not serenos_padron.cuil_valido(c.replace("-", "")):  # un CUIL ya cargado que no se toca no se vuelve a exigir
        return None, None, "cuil_digito"
    otro = db.scalar(select(Encargado).where(Encargado.cuil == c))
    if otro is not None and otro.id != propio_id:
        return None, None, "repetido"
    return nombre, c, None


@router.post("/encargados/{encargado_id}/guardar")
def encargado_guardar(encargado_id: int, nombre: str = Form(""), cuil: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    e = db.get(Encargado, encargado_id)
    if e is None:
        return RedirectResponse("/administracion/encargados?error=no_existe", status_code=303)
    n, c, err = _datos_encargado(db, nombre, cuil, e.id, e.cuil)
    if err:
        return RedirectResponse(f"/administracion/encargados?error={err}_{e.id}", status_code=303)
    e.nombre, e.cuil = n, c
    db.commit()
    return RedirectResponse("/administracion/encargados?ok=guardado", status_code=303)


@router.post("/encargados/{encargado_id}/supero")
def encargado_supero(encargado_id: int, mes: str = Form(""), activo: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    m = enc.mes_valido(mes)
    if db.get(Encargado, encargado_id) is None or not m:
        return RedirectResponse("/administracion/encargados?error=no_existe", status_code=303)
    enc.marcar_supero(db, encargado_id, m, bool(activo), user.username)
    return RedirectResponse(f"/administracion/encargados?mes={m}", status_code=303)


@router.post("/encargados/tope")
def encargado_tope(mes: str = Form(""), monto: str = Form(""), db: Session = Depends(get_db), user: User = Depends(datos_reservados_required)):
    m = enc.mes_valido(mes)
    if not m:
        return RedirectResponse("/administracion/encargados?error=tope_mes", status_code=303)
    v = _monto(monto)
    if v is None:
        return RedirectResponse(f"/administracion/encargados?mes={m}&error=tope_monto", status_code=303)
    actual = enc.tope_de(db, m)
    if actual is not None and abs(actual.monto - v) < 0.005:
        return RedirectResponse(f"/administracion/encargados?mes={m}&ok=tope_igual", status_code=303)
    db.add(EncargadoTope(mes=m, monto=v, usuario=user.username))
    db.commit()
    return RedirectResponse(f"/administracion/encargados?mes={m}&ok=tope", status_code=303)


@router.get("/tarifas-personal", response_class=HTMLResponse)
def tarifas_personal_page(request: Request, vigencia: str = "", db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    filas = db.scalars(select(TarifaPersonal).order_by(TarifaPersonal.vigencia, TarifaPersonal.id)).all()
    vigencias = sorted({f.vigencia for f in filas}, reverse=True)
    elegida = vigencia if vigencia in vigencias else (vigencias[0] if vigencias else "")
    por = {(f.servicio, f.categoria, f.nivel): f for f in filas if f.vigencia == elegida}

    def grilla(servicio, categorias, niveles):
        return [{"categoria": k, "etiqueta": et, "celdas": [por.get((servicio, k, n)) for n in niveles]} for k, et in categorias.items()]

    return templates.TemplateResponse(request, "administracion/tarifas_personal.html", {
        "user": user, "vigencias": vigencias, "elegida": elegida, "hoy": date.today().isoformat(),
        "tally": grilla("TALLY", personal.CATEGORIAS_TALLY, ("H", "100", "150")),
        "serenos": grilla("SERENO", personal.CATEGORIAS_SERENOS, ("HABIL", "INHABIL", "DOMINGO")),
        "viaticos": grilla("VIATICO", personal.VIATICOS, ("TURNO",)),
        "aviso": request.query_params.get("ok", ""), "error": request.query_params.get("error", ""),
    })


@router.post("/tarifas-personal/guardar")
async def tarifas_personal_guardar(request: Request, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    form = await request.form()
    vig = str(form.get("vigencia") or "")
    clave = str(form.get("confirm_password") or "")
    if not clave or not verify_password(clave, user.password_hash):
        return RedirectResponse(f"/administracion/tarifas-personal?vigencia={vig}&error=password", status_code=303)
    cambios = 0
    for f in db.scalars(select(TarifaPersonal).where(TarifaPersonal.vigencia == vig)):
        raw = form.get(f"v_{f.id}")
        if raw is None:
            continue
        n = _numero_ar(str(raw))
        if n is None:
            return RedirectResponse(f"/administracion/tarifas-personal?vigencia={vig}&error=numero", status_code=303)
        if abs(n - f.valor) > 0.004:
            f.valor = n
            cambios += 1
    db.commit()
    return RedirectResponse(f"/administracion/tarifas-personal?vigencia={vig}&ok={'guardado' if cambios else 'sin_cambios'}", status_code=303)


@router.post("/tarifas-personal/nueva")
def tarifas_personal_nueva(desde: str = Form(""), copiar: str = Form(""), db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    """Nueva vigencia: copia todos los valores de la vigencia elegida con la fecha nueva, para despues corregirlos."""
    try:
        nueva = date.fromisoformat(desde).isoformat()
    except ValueError:
        return RedirectResponse(f"/administracion/tarifas-personal?vigencia={copiar}&error=fecha", status_code=303)
    if db.scalar(select(TarifaPersonal).where(TarifaPersonal.vigencia == nueva).limit(1)):
        return RedirectResponse(f"/administracion/tarifas-personal?vigencia={copiar}&error=repetida", status_code=303)
    base = db.scalars(select(TarifaPersonal).where(TarifaPersonal.vigencia == copiar)).all()
    if not base:
        return RedirectResponse("/administracion/tarifas-personal?error=sin_base", status_code=303)
    for f in base:
        db.add(TarifaPersonal(servicio=f.servicio, categoria=f.categoria, nivel=f.nivel, valor=f.valor, vigencia=nueva))
    db.commit()
    return RedirectResponse(f"/administracion/tarifas-personal?vigencia={nueva}&ok=nueva", status_code=303)


# ------------------------------------------------------------- calendario --
@router.get("/calendario", response_class=HTMLResponse)
def calendario_page(request: Request, anio: int = 0, db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    anio = anio or date.today().year
    feriados = [
        {"id": f.id, "fecha": f.fecha, "d": date.fromisoformat(f.fecha), "nombre": f.nombre, "tipo": f.tipo}
        for f in db.scalars(select(Feriado).where(Feriado.fecha.like(f"{anio}-%")).order_by(Feriado.fecha))
    ]
    for f in feriados:
        f["dia"] = pf.DIAS[f["d"].weekday()]
    return templates.TemplateResponse(request, "administracion/calendario.html", {
        "user": user, "feriados": feriados, "anio": anio, "error": request.query_params.get("error", ""),
        "tipos": TIPOS_CALENDARIO,
        "n_feriados": sum(1 for f in feriados if f["tipo"] != "NO_LABORABLE"),
        "n_no_lab": sum(1 for f in feriados if f["tipo"] == "NO_LABORABLE"),
    })


@router.post("/calendario/agregar")
def calendario_agregar(fecha: str = Form(""), nombre: str = Form(""), tipo: str = Form("FERIADO"),
                       db: Session = Depends(get_db), user: User = Depends(administracion_required)):
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        return RedirectResponse("/administracion/calendario?error=fecha", status_code=303)
    if db.scalar(select(Feriado).where(Feriado.fecha == d.isoformat())):
        return RedirectResponse(f"/administracion/calendario?anio={d.year}&error=repetido", status_code=303)
    tipo = tipo if tipo in TIPOS_CALENDARIO else "FERIADO"
    db.add(Feriado(fecha=d.isoformat(), nombre=" ".join(nombre.split())[:120] or TIPOS_CALENDARIO[tipo], tipo=tipo,
                   creado_por=user.username))
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
