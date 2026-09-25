import io

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..charts import build_donut, describir_fuera, filtrar_por_tipo
from ..database import get_db
from datetime import date, datetime, timedelta

from ..dates import eta_sort_key, parse_date
from ..models import Client, OperatedVessel, Terminal, User, VesselCall, VesselExtraAgency, VesselFile
from ..recalc import recalc_lineup, recalc_terminal
from ..service import (
    active_clients,
    active_terminals,
    calls_for_lineup,
    close_vessel_file_if_open,
    ensure_vessel_file,
    get_draft_lineup,
    group_by_terminal,
    sync_is_ours,
)
from ..templating import templates

router = APIRouter()

EDITABLE = {
    "vessel_name", "vessel_type", "imo", "eta", "etb", "etc", "operation",
    "quantity", "grade", "shipper", "destination", "local_agent",
}
BOOL_FIELDS = {"is_ours", "second_call"}
SEA_WHITE = {"sea white", "seawhite", "sw"}


def _render_lineup(request: Request, db: Session, user: User, kind: str) -> HTMLResponse:
    lineup = get_draft_lineup(db, kind)
    terminals = active_terminals(db, kind)
    calls = calls_for_lineup(db, lineup.id)
    grouped = group_by_terminal(terminals, calls)
    return templates.TemplateResponse(
        request,
        "lineup.html",
        {
            "user": user,
            "kind": kind,
            "flammable": kind == "FLAMMABLE",
            "lineup": lineup,
            "terminals": terminals,
            "grouped": grouped,
            "clients": active_clients(db),
            "vessel_types": ["Bulk Carrier", "Tanker"],
            "ours_count": sum(1 for c in calls if c.is_ours),
        },
    )


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "home.html", {"user": user})


@router.get("/lineup", response_class=HTMLResponse)
def grain_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _render_lineup(request, db, user, "GRAIN")


@router.get("/flammable", response_class=HTMLResponse)
def flammable_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _render_lineup(request, db, user, "FLAMMABLE")


_MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _period_label(p: str) -> str:
    try:
        y, m = p.split("-")
        return f"{_MESES[int(m)].capitalize()} {y}"
    except (ValueError, IndexError):
        return p or "sin mes"


@router.get("/nuestros-barcos", response_class=HTMLResponse)
def our_vessels_page(request: Request, mes: str = "", tipo: str = "AGENCY", db: Session = Depends(get_db), user: User = Depends(current_user)):
    en_lineup = []
    for kind in ("GRAIN", "FLAMMABLE"):
        lineup = get_draft_lineup(db, kind)
        terminals = active_terminals(db, kind)
        grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
        term_by_id = {t.id: t for t in terminals}
        for t in terminals:
            for c in grouped.get(t.id, []):
                if c.is_ours:
                    en_lineup.append((kind, term_by_id.get(c.terminal_id), c))
    en_lineup.sort(key=lambda row: eta_sort_key(row[2].eta, row[2].etb))

    todos = list(db.scalars(select(OperatedVessel).order_by(OperatedVessel.period.desc(),
                                                            OperatedVessel.operated_at.desc())))
    # conteo por mes para las pestañas
    counts: dict[str, int] = {}
    for o in todos:
        counts[o.period or ""] = counts.get(o.period or "", 0) + 1
    meses = sorted(counts.keys(), reverse=True)
    operados = [o for o in todos if o.period == mes] if mes else todos

    # graficos de torta: operados (sigue el filtro de mes) y anunciados (line-up actual).
    # Solo cuentan los clientes cargados y activos en la planilla de Clientes.
    # Un barco cuenta una vez por CADA cliente asociado (agencia principal, otras agencias y
    # estibas), asi que si figura con agencia y estiba aparece en los dos selectores.
    tipo = "ESTIBA" if tipo.upper() == "ESTIBA" else "AGENCY"
    tipo_por_nombre = {c.name.strip().casefold(): c.client_type for c in active_clients(db)}
    nombres_anunciados: list[str] = []
    for _, _, call in en_lineup:
        clientes = call.recipient_clients()
        nombres_anunciados += [c.name for c in clientes] if clientes else [call.principal_name]
    todos_op = [o.principal for o in operados]
    ag_op, fuera_op = filtrar_por_tipo(todos_op, tipo_por_nombre, "AGENCY")
    es_op, _ = filtrar_por_tipo(todos_op, tipo_por_nombre, "ESTIBA")
    nombres_op = ag_op if tipo == "AGENCY" else es_op
    nombres_an, fuera_an = filtrar_por_tipo(nombres_anunciados, tipo_por_nombre, tipo)
    grafico_operados = build_donut(nombres_op)
    grafico_anunciados = build_donut(nombres_an)
    # el total de la tabla de operados = agencias + estibas + los que no se pueden clasificar
    cuenta_operados = {"total": len(todos_op), "agencias": len(ag_op), "estibas": len(es_op), "fuera": len(fuera_op)}

    # Tabla de Operados: separada en Agencia / Estiba (se cobra una vez por
    # cada cliente asociado, asi que cada fila es un cliente distinto).
    operados_agencia = [o for o in operados if tipo_por_nombre.get(o.principal.strip().casefold()) == "AGENCY"]
    operados_estiba = [o for o in operados if tipo_por_nombre.get(o.principal.strip().casefold()) == "ESTIBA"]

    return templates.TemplateResponse(
        request,
        "nuestros_barcos.html",
        {
            "user": user,
            "en_lineup": en_lineup,
            "operados": operados,
            "operados_agencia": operados_agencia,
            "operados_estiba": operados_estiba,
            "grafico_operados": grafico_operados,
            "grafico_anunciados": grafico_anunciados,
            "fuera_operados": describir_fuera(fuera_op),
            "n_fuera_operados": len(fuera_op),
            "fuera_anunciados": describir_fuera(fuera_an),
            "n_fuera_anunciados": len(fuera_an),
            "cuenta_operados": cuenta_operados,
            "tipo": tipo,
            "total_operados": len(todos),
            "mes": mes,
            "meses": [(m, _period_label(m), counts[m]) for m in meses],
            "period_label": _period_label,
            "clients": active_clients(db),
        },
    )


def _sitio(o: OperatedVessel) -> str:
    return o.berth_label or o.terminal_code or ""


def _parse_zarpe(value: str) -> datetime | None:
    """'2026-09-20T20:15' (datetime-local) -> datetime, para que Excel lo
    trate como fecha real (ordenable/filtrable), no como texto suelto."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


@router.get("/nuestros-barcos/operados/exportar.xlsx")
def exportar_operados(mes: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    """BARCO / SITIO o MUELLE / ZARPADA / DESTINO / CLIENTE, separado en 2
    hojas (Agencias / Estibas) -- respeta el filtro de mes que este viendo."""
    query = select(OperatedVessel).order_by(OperatedVessel.period.desc(), OperatedVessel.operated_at.desc())
    todos = list(db.scalars(query))
    operados = [o for o in todos if o.period == mes] if mes else todos
    tipo_por_nombre = {c.name.strip().casefold(): c.client_type for c in active_clients(db)}
    operados_agencia = [o for o in operados if tipo_por_nombre.get(o.principal.strip().casefold()) == "AGENCY"]
    operados_estiba = [o for o in operados if tipo_por_nombre.get(o.principal.strip().casefold()) == "ESTIBA"]

    BLUE = "FF1B5FA8"
    WHITE_BOLD = Font(bold=True, color="FFFFFFFF")

    def _fill(color):
        return PatternFill("solid", fgColor=color)

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in (("Agencias", operados_agencia), ("Estibas", operados_estiba)):
        ws = wb.create_sheet(title)
        headers = ["BARCO", "SITIO / MUELLE", "ZARPADA", "DESTINO", "CLIENTE"]
        for i, h in enumerate(headers, start=1):
            c = ws.cell(row=1, column=i, value=h)
            c.font = WHITE_BOLD
            c.fill = _fill(BLUE)
            c.alignment = Alignment(horizontal="left")
        for r, o in enumerate(rows, start=2):
            ws.cell(row=r, column=1, value=o.vessel_name.upper())
            ws.cell(row=r, column=2, value=_sitio(o))
            zarpe_dt = _parse_zarpe(o.zarpe)
            zc = ws.cell(row=r, column=3, value=zarpe_dt if zarpe_dt else "")
            if zarpe_dt:
                zc.number_format = "dd/mm/yyyy hh:mm"
            ws.cell(row=r, column=4, value=o.destination or "")
            ws.cell(row=r, column=5, value=o.principal)
        for i, w in enumerate([28, 22, 20, 22, 26], start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    filename = f"Operados {_period_label(mes) if mes else 'todos'}.xlsx".replace("/", "-")
    return StreamingResponse(
        bio, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/nuestros-barcos/agregar")
def add_our_vessel(
    db: Session = Depends(get_db), user: User = Depends(current_user),
    vessel_name: str = Form(...), ubicacion: str = Form(...),
    principal: str = Form(""), eta: str = Form(""), lleva_reporte: str = Form(""),
):
    """Alta rapida para barcos que no pasan por el line-up "oficial" (ej.
    vienen solo a tomar bunker, en Boya 11) -- se escribe la ubicacion a
    mano y si no existe un muelle con ese nombre se crea uno nuevo (GRAIN,
    excluido del Excel), asi la proxima vez que se repita esa ubicacion se
    reusa el mismo. Queda marcado "Nuestro" siempre (para el recuento);
    el legajo en Barcos (ID) solo se abre si se tildo "Lleva reporte"."""
    ubicacion = ubicacion.strip()
    if not vessel_name.strip() or not ubicacion:
        return RedirectResponse("/nuestros-barcos", status_code=302)

    terminal = db.scalar(
        select(Terminal).where(Terminal.kind == "GRAIN", func.lower(Terminal.code) == ubicacion.lower())
    )
    if not terminal:
        max_order = db.scalar(select(func.coalesce(func.max(Terminal.sort_order), 0)).where(Terminal.kind == "GRAIN"))
        terminal = Terminal(
            kind="GRAIN", code=ubicacion, name=ubicacion, berth_label=ubicacion,
            sort_order=max(max_order or 0, 890) + 10, active=True, exclude_from_excel=True,
        )
        db.add(terminal)
        db.flush()

    lineup = get_draft_lineup(db, "GRAIN")
    max_order = db.scalar(
        select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
            VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal.id
        )
    )
    call = VesselCall(
        lineup_id=lineup.id, terminal_id=terminal.id, sort_order=(max_order or 0) + 10,
        vessel_name=vessel_name.strip(), vessel_type="Bulk Carrier", operation="Load",
        eta=eta.strip(), is_ours=True, needs_report=lleva_reporte == "on",
    )
    db.add(call)
    db.flush()
    _set_principal(db, call, principal.strip())
    lineup.updated_by = user.username
    if call.needs_report:
        ensure_vessel_file(db, call, user)
    db.commit()
    return RedirectResponse("/nuestros-barcos", status_code=302)


@router.post("/operados/{op_id}/mes")
def move_operated(op_id: int, period: str = Form(""), volver: str = Form(""),
                  db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(OperatedVessel, op_id)
    if row:
        p = period.strip()[:7]
        if len(p) == 7 and p[4] == "-":
            row.period = p
            db.commit()
    dest = f"/nuestros-barcos?mes={volver}" if volver else "/nuestros-barcos"
    return RedirectResponse(dest + "#operados", status_code=302)


@router.post("/operados/{op_id}/cliente")
def set_operated_client(op_id: int, cliente: str = Form(""), volver: str = Form(""), tipo: str = Form("AGENCY"),
                        db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Corrige el cliente de un barco ya operado (ej. quedo con un texto suelto como
    "AT PORT" en vez de su cliente). Solo se acepta un cliente activo de la planilla."""
    row = db.get(OperatedVessel, op_id)
    client = db.scalar(
        select(Client).where(func.lower(Client.name) == cliente.strip().lower(), Client.active.is_(True))
    )
    if row and client:
        row.principal = client.name
        db.commit()
    partes = ([f"mes={volver}"] if volver else []) + [f"tipo={'ESTIBA' if tipo.upper() == 'ESTIBA' else 'AGENCY'}"]
    return RedirectResponse("/nuestros-barcos?" + "&".join(partes) + "#operados", status_code=302)


@router.post("/operados/{op_id}/completar")
def completar_operado(
    op_id: int, volver: str = Form(""), tipo: str = Form("AGENCY"),
    amarre: str = Form(""), inicio_operacion: str = Form(""), fin_operacion: str = Form(""),
    zarpe: str = Form(""), cantidad_operada: str = Form(""),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Carga los datos operativos de un barco ya operado (Amarre/Inicio/Final/
    Zarpe/Cantidad para Agencia, o solo Final para Estiba) -- se van a usar
    para calculos futuros, por eso quedan en campos propios y no sueltos.
    Un mismo movimiento de barco genera una fila de OperatedVessel POR
    CADA cliente (ver _archive_operated), asi que al completar una hay
    que repetir los mismos datos en sus filas hermanas (mismo barco,
    mismo muelle, creadas juntas en el mismo momento al sacarlo del
    line-up) para no tener que cargarlo mas de una vez."""
    row = db.get(OperatedVessel, op_id)
    if row:
        row.amarre = amarre.strip()
        row.inicio_operacion = inicio_operacion.strip()
        row.fin_operacion = fin_operacion.strip()
        row.zarpe = zarpe.strip()
        row.cantidad_operada = cantidad_operada.strip()

        hermanas = db.scalars(
            select(OperatedVessel).where(
                OperatedVessel.id != row.id,
                func.lower(OperatedVessel.vessel_name) == row.vessel_name.strip().lower(),
                OperatedVessel.terminal_code == row.terminal_code,
                OperatedVessel.berth_label == row.berth_label,
                OperatedVessel.operated_at >= row.operated_at - timedelta(seconds=10),
                OperatedVessel.operated_at <= row.operated_at + timedelta(seconds=10),
            )
        ).all()
        for h in hermanas:
            h.amarre = row.amarre
            h.inicio_operacion = row.inicio_operacion
            h.fin_operacion = row.fin_operacion
            h.zarpe = row.zarpe
            h.cantidad_operada = row.cantidad_operada
        db.commit()
    partes = ([f"mes={volver}"] if volver else []) + [f"tipo={'ESTIBA' if tipo.upper() == 'ESTIBA' else 'AGENCY'}"]
    return RedirectResponse("/nuestros-barcos?" + "&".join(partes) + "#operados", status_code=302)


@router.post("/operados/{op_id}/delete")
def delete_operated(op_id: int, volver: str = Form(""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(OperatedVessel, op_id)
    if row:
        db.delete(row)
        db.commit()
    dest = f"/nuestros-barcos?mes={volver}" if volver else "/nuestros-barcos"
    return RedirectResponse(dest + "#operados", status_code=302)


@router.post("/api/lineup")
async def update_lineup(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    lineup = get_draft_lineup(db, str(data.get("kind", "GRAIN")))
    # la fecha ya no se toca a mano -- get_draft_lineup la pisa sola con hoy
    if "port_name" in data:
        lineup.port_name = str(data["port_name"]).strip()
    if "notice" in data:
        lineup.notice = str(data["notice"]).strip()
    lineup.updated_by = user.username
    db.commit()
    return {"ok": True}


@router.post("/api/calls")
async def create_call(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    terminal = db.get(Terminal, int(data["terminal_id"]))
    if not terminal:
        return JSONResponse({"error": "terminal no existe"}, status_code=400)
    lineup = get_draft_lineup(db, terminal.kind)
    max_order = db.scalar(
        select(func.coalesce(func.max(VesselCall.sort_order), 0)).where(
            VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal.id
        )
    )
    call = VesselCall(
        lineup_id=lineup.id,
        terminal_id=terminal.id,
        sort_order=(max_order or 0) + 10,
        operation="Load",
        vessel_type="Tanker" if terminal.kind == "FLAMMABLE" else "Bulk Carrier",
    )
    db.add(call)
    lineup.updated_by = user.username
    db.commit()
    return {"ok": True, "id": call.id}


@router.patch("/api/calls/{call_id}")
async def update_call(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    field = data.get("field")
    value = data.get("value", "")

    if field in BOOL_FIELDS:
        setattr(call, field, bool(value))
    elif field == "principal":
        _set_principal(db, call, str(value).strip())
    elif field in EDITABLE:
        setattr(call, field, str(value).strip())
        if field == "local_agent":
            call.is_ours = (str(value).strip().lower() in SEA_WHITE) or call.is_ours
    else:
        return JSONResponse({"error": f"campo invalido: {field}"}, status_code=400)

    call.lineup.updated_by = user.username
    vf = ensure_vessel_file(db, call, user) if call.is_ours and call.needs_report else None
    if not call.is_ours:
        close_vessel_file_if_open(db, call)
    db.commit()
    return {
        "ok": True,
        "is_ours": call.is_ours,
        "principal_name": call.principal_name,
        "linked": call.principal_client_id is not None,
        "file_id": vf.id if vf else None,
    }


@router.post("/api/terminals/{terminal_id}/note")
async def update_terminal_note(terminal_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    term = db.get(Terminal, terminal_id)
    if not term:
        return JSONResponse({"error": "no existe"}, status_code=404)
    term.status_note = str(data.get("value", "")).strip()
    db.commit()
    return {"ok": True}


@router.post("/api/calls/{call_id}/extras")
async def set_extras(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    ids = {int(x) for x in data.get("client_ids", []) if str(x).strip()}
    call.extra_agencies.clear()
    db.flush()
    for cid in ids:
        if db.get(Client, cid):
            db.add(VesselExtraAgency(vessel_call_id=call.id, client_id=cid))
    db.flush()
    if call.is_ours and call.needs_report:
        ensure_vessel_file(db, call, user)
    db.commit()
    return {"ok": True}


@router.post("/api/calls/{call_id}/move")
async def move_call(call_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = await request.json()
    direction = data.get("direction")
    call = db.get(VesselCall, call_id)
    if not call:
        return JSONResponse({"error": "no existe"}, status_code=404)
    siblings = list(
        db.scalars(
            select(VesselCall)
            .where(
                VesselCall.lineup_id == call.lineup_id,
                VesselCall.terminal_id == call.terminal_id,
            )
            .order_by(VesselCall.sort_order, VesselCall.id)
        )
    )
    idx = next(i for i, c in enumerate(siblings) if c.id == call.id)
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(siblings):
        other = siblings[swap]
        call.sort_order, other.sort_order = other.sort_order, call.sort_order
        db.commit()
    return {"ok": True}


@router.delete("/api/calls/{call_id}")
def delete_call(call_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    call = db.get(VesselCall, call_id)
    if call:
        if call.is_ours:
            _archive_operated(db, call, user)
            # se saco del line-up (X) -- si tenia legajo abierto en Barcos
            # (ID), se cierra tambien: si no, queda "abierto" para siempre
            # aunque el barco ya se fue (sumando de mas en Abiertos).
            vf = db.scalar(
                select(VesselFile).where(
                    VesselFile.status == "open",
                    func.lower(VesselFile.vessel_name) == call.vessel_name.strip().lower(),
                    VesselFile.terminal_id == call.terminal_id,
                )
            )
            if vf:
                vf.status = "closed"
                vf.closed_at = datetime.utcnow()
        db.delete(call)
        db.commit()
    return {"ok": True}


_MISMO_BARCO_DIAS = 45  # ventana para considerar "mismo paso por puerto"


def _buscar_operado_mismo_imo(
    db: Session, imo: str, vessel_name: str, principal: str, ahora: datetime,
) -> OperatedVessel | None:
    """Un barco que se saca de un muelle y se vuelve a cargar en otro (mismo
    cliente facturado) es el MISMO paso por puerto, no dos -- si ya hay un
    Operado reciente para ese barco+cliente, se fusiona ahi en vez de sumar
    una fila nueva al recuento mensual.

    Matchea por IMO si esta cargado en los dos lados (mas confiable); si
    alguno de los dos quedo sin IMO (se olvidaron de tipearlo de nuevo al
    volver a cargar el barco en el otro muelle), cae a nombre de barco
    -- sigue siendo el mismo cliente y la misma ventana de dias, asi que
    el riesgo de matchear dos barcos distintos por casualidad es bajo."""
    imo = (imo or "").strip()
    vessel_name = (vessel_name or "").strip()
    if not imo and not vessel_name:
        return None
    desde = ahora - timedelta(days=_MISMO_BARCO_DIAS)
    filtros = [
        func.lower(OperatedVessel.principal) == principal.strip().lower(),
        OperatedVessel.operated_at >= desde,
    ]
    if imo:
        filtros.append((OperatedVessel.imo == imo) | (func.lower(OperatedVessel.vessel_name) == vessel_name.lower()))
    else:
        filtros.append(func.lower(OperatedVessel.vessel_name) == vessel_name.lower())
    return db.scalar(select(OperatedVessel).where(*filtros).order_by(OperatedVessel.operated_at.desc()))


def _archive_operated(db: Session, call: VesselCall, user: User) -> None:
    """Una fila por CADA cliente (principal + otras agencias) -- si el barco
    tenia 3 clientes cuenta como 3 barcos operados para el recuento mensual,
    no como uno solo con los otros dos pegados en un campo de texto aparte.

    Si el mismo IMO+cliente ya tiene un Operado reciente (se movio de
    muelle y se volvio a cargar en otra terminal), se fusiona en esa fila
    en vez de crear una nueva -- ver _buscar_operado_mismo_imo."""
    term = call.terminal
    ahora = datetime.utcnow()
    d = parse_date(call.etc) or parse_date(call.etb) or date.today()
    nuevo_terminal_code = term.code if term else ""
    nuevo_berth = (term.berth_label or term.code) if term else ""
    clients = call.recipient_clients()
    names = [c.name for c in clients] if clients else [call.principal_name]
    for name in names:
        existente = _buscar_operado_mismo_imo(db, call.imo, call.vessel_name, name, ahora)
        if existente:
            if nuevo_berth and nuevo_berth not in existente.berth_label:
                existente.berth_label = f"{existente.berth_label} → {nuevo_berth}".strip(" →")
            if nuevo_terminal_code and nuevo_terminal_code not in existente.terminal_code:
                existente.terminal_code = f"{existente.terminal_code} → {nuevo_terminal_code}".strip(" →")
            if call.quantity.strip() and call.quantity.strip() not in existente.quantity:
                existente.quantity = f"{existente.quantity} + {call.quantity}".strip(" +")
            existente.etb = call.etb or existente.etb
            existente.etc = call.etc or existente.etc
            existente.destination = call.destination or existente.destination
            existente.grade = call.grade or existente.grade
            existente.shipper = call.shipper or existente.shipper
            existente.vessel_type = call.vessel_type or existente.vessel_type
            existente.period = d.strftime("%Y-%m")
            existente.removed_by = user.username
            continue
        db.add(
            OperatedVessel(
                removed_by=user.username,
                period=d.strftime("%Y-%m"),
                lineup_date=call.lineup.lineup_date if call.lineup else "",
                terminal_code=nuevo_terminal_code,
                berth_label=nuevo_berth,
                vessel_name=call.vessel_name,
                vessel_type=call.vessel_type,
                imo=call.imo,
                eta=call.eta,
                etb=call.etb,
                etc=call.etc,
                operation=call.operation,
                quantity=call.quantity,
                grade=call.grade,
                shipper=call.shipper,
                destination=call.destination,
                local_agent=call.local_agent,
                principal=name,
                extras="",
            )
        )


def _changes_payload(changes) -> dict:
    return {
        "ok": True,
        "count": len(changes),
        "changes": [
            {"vessel": c.vessel_name, "field": c.field, "old": c.old, "new": c.new}
            for c in changes
        ],
    }


@router.post("/api/recalc")
def recalc(kind: str = "GRAIN", db: Session = Depends(get_db), user: User = Depends(current_user)):
    lineup = get_draft_lineup(db, kind)
    terminals = active_terminals(db, kind)
    grouped = group_by_terminal(terminals, calls_for_lineup(db, lineup.id))
    changes = recalc_lineup(grouped)
    db.commit()
    return _changes_payload(changes)


@router.post("/api/terminals/{terminal_id}/recalc")
def recalc_one_terminal(terminal_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    term = db.get(Terminal, terminal_id)
    if not term:
        return JSONResponse({"error": "no existe"}, status_code=404)
    lineup = get_draft_lineup(db, term.kind)
    calls = list(
        db.scalars(
            select(VesselCall)
            .where(VesselCall.lineup_id == lineup.id, VesselCall.terminal_id == terminal_id)
            .order_by(VesselCall.sort_order, VesselCall.id)
        )
    )
    changes = recalc_terminal(calls)
    db.commit()
    return _changes_payload(changes)


def _set_principal(db: Session, call: VesselCall, value: str) -> None:
    if not value:
        call.principal_client_id = None
        call.principal_text = ""
        return
    client = db.scalar(select(Client).where(func.lower(Client.name) == value.lower()))
    if client:
        call.principal_client_id = client.id
        call.principal_text = ""
    else:
        call.principal_client_id = None
        call.principal_text = value
