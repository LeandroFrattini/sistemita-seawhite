"""Administracion: proforma final (asistente), agencias a facturar (fee y cargas sociales) y calendario de feriados."""
from __future__ import annotations

import json
import re
from datetime import date

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import proforma_final as pf
from ..calendario import TIPOS as TIPOS_CALENDARIO
from ..auth import administracion_required
from ..database import get_db
from ..docgen.fechas import parse_number
from ..docgen import voucher as vch
from ..models import AgenciaFee, AppSetting, Client, DocCall, DocVessel, Feriado, OperatedVessel, User
from .. import practicaje as pract
from .. import muelle as muelle_calc
from ..vouchers_lib import estado_voucher
from ..proforma_fees_2026 import buscar_en_lista, sugerir_monto
from ..templating import templates

router = APIRouter(prefix="/administracion")

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
        return {"servicios": [], "turnos": [], "hay_voucher": False}
    try:
        turnos = [t for t in json.loads(v.turnos or "[]") if isinstance(t, dict)]
    except ValueError:
        turnos = []
    return {"servicios": vch.lineas(v.formato, estado_voucher(v)), "turnos": turnos, "hay_voucher": True,
            "voucher_enviado": v.estado == "ENVIADO"}


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
