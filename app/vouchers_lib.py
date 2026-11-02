"""Logica de vouchers que comparten el router, Pendientes y el bloqueo (sin dependencias de FastAPI)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .docgen import voucher as vch
from .models import AppSetting, Client, OperatedVessel, Voucher

BLOQUEO_KEY = "voucher_bloqueo"  # "1" = prendido. Viene APAGADO: se prende a mano desde Admin cuando se termine de probar.

# Turnos del Head Tally: siempre de 6 horas.
TURNOS = [("01-07", 1, 7), ("07-13", 7, 13), ("13-19", 13, 19), ("19-01", 19, 25)]


def bloqueo_activo(db: Session) -> bool:
    row = db.get(AppSetting, BLOQUEO_KEY)
    return bool(row and row.value == "1")


def set_bloqueo(db: Session, activo: bool) -> None:
    row = db.get(AppSetting, BLOQUEO_KEY)
    if row:
        row.value = "1" if activo else "0"
    else:
        db.add(AppSetting(key=BLOQUEO_KEY, value="1" if activo else "0"))
    db.commit()


def estado_voucher(v: Voucher) -> dict:
    try:
        return json.loads(v.items or "{}")
    except ValueError:
        return {}


# Cuando un barco se atiende para mas de un cliente, cada uno tiene su voucher, pero el Head Tally y los Serenos (watchman)
# van en UN solo voucher: el que los tenga tildado.
EXCLUSIVOS = {"head_tally": "HEAD TALLY", "watchman": "SERENOS"}


def _estibas(db: Session) -> set[str]:
    return {c.name.strip().lower() for c in db.scalars(select(Client).where(Client.client_type == "ESTIBA"))}


def hermanos(db: Session, o: OperatedVessel) -> list[OperatedVessel]:
    """Las otras filas de agencia del mismo barco y la misma estadia (mismo nombre, mismo amarre y zarpe): los demas clientes del barco."""
    if not (o.amarre or "").strip() or not (o.zarpe or "").strip():
        return []
    estibas = _estibas(db)
    return [h for h in db.scalars(select(OperatedVessel).where(
        OperatedVessel.id != o.id, func.lower(OperatedVessel.vessel_name) == (o.vessel_name or "").strip().lower(),
        OperatedVessel.amarre == o.amarre, OperatedVessel.zarpe == o.zarpe)) if es_fila_de_agencia(h, estibas)]


def exclusivos_activos(formato: str, estado: dict, servicio: str = "FULL") -> set[str]:
    """Cuales de los conceptos que van en un solo voucher (head_tally, watchman) estan tildados en ese estado."""
    est = vch.normalizar(formato, estado, servicio)
    return {k for k in EXCLUSIVOS if k in est["c"] and est["c"][k].get("on")}


def conflictos(db: Session, v: Voucher, estado: dict) -> list[tuple[Voucher, set[str]]]:
    """Los vouchers hermanos que ya llevan alguno de los conceptos exclusivos que este voucher tiene tildados: [(voucher, {claves})]."""
    propios = exclusivos_activos(v.formato, estado, v.servicio)
    if not propios:
        return []
    o = db.get(OperatedVessel, v.operated_id)
    out = []
    for h in hermanos(db, o) if o is not None else []:
        if h.voucher is None:
            continue
        comunes = propios & exclusivos_activos(h.voucher.formato, estado_voucher(h.voucher), h.voucher.servicio)
        if comunes:
            out.append((h.voucher, comunes))
    return out


def sacar_de(v: Voucher, claves: set[str]) -> None:
    """Destilda esos conceptos en un voucher (se pasan al otro)."""
    est = vch.normalizar(v.formato, estado_voucher(v), v.servicio)
    for k in claves:
        if k in est["c"]:
            est["c"][k]["on"] = False
    v.items = json.dumps(est, ensure_ascii=False)


def resumen_hermanos(db: Session, o: OperatedVessel) -> list[dict]:
    """Para mostrar en el voucher: los otros clientes del barco, como va su voucher y cual lleva Head Tally / Serenos."""
    out = []
    for h in hermanos(db, o):
        v = h.voucher
        out.append({"agencia": h.principal, "estado": ("Enviado" if v.estado == "ENVIADO" else "Borrador") if v else "Sin armar",
                    "url": f"/vouchers/{v.id}" if v else f"/vouchers/nuevo?operated_id={h.id}",
                    "lleva": [EXCLUSIVOS[k] for k in EXCLUSIVOS if v and k in exclusivos_activos(v.formato, estado_voucher(v), v.servicio)]})
    return out


def lleva_head_tally(v: Voucher) -> bool:
    return vch.tiene(v.formato, estado_voucher(v), "head_tally", v.servicio)


def turnos_confirmados(v: Voucher) -> bool:
    return bool((v.turnos or "").strip())


def incompleto(v: Voucher) -> bool:
    """Falta enviarlo, o lleva Head Tally y no se confirmaron los turnos."""
    if v.estado != "ENVIADO":
        return True
    return lleva_head_tally(v) and not turnos_confirmados(v)


def es_fila_de_agencia(o: OperatedVessel, estibas: set[str]) -> bool:
    return (o.principal or "").strip().lower() not in estibas


def pendientes(db: Session) -> list[OperatedVessel]:
    """Barcos operados con los datos completados cuyo voucher falta o esta sin terminar (tarea para todos)."""
    out = []
    for o in db.scalars(select(OperatedVessel).where(OperatedVessel.datos_completados_at.is_not(None))
                        .order_by(OperatedVessel.datos_completados_at.desc())):
        if o.voucher is None or incompleto(o.voucher):
            out.append(o)
    return out


def voucher_bloqueante(db: Session, username: str) -> Voucher | None:
    """El voucher que este usuario tiene que completar si o si (solo si el bloqueo esta prendido)."""
    if not bloqueo_activo(db):
        return None
    for v in db.scalars(select(Voucher).where(Voucher.bloqueo_user == username).order_by(Voucher.id)):
        if incompleto(v):
            return v
    return None


# ----------------------------------------------------------------- turnos --
def _parse_dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def _rango(inicio: str, fin: str, amarre: str = "") -> tuple[datetime | None, datetime | None]:
    """El Head Tally arranca desde el berthing (amarre); si no hay amarre cargado, desde el inicio de la operacion."""
    fechas = [d for d in (_parse_dt(amarre), _parse_dt(inicio)) if d]
    a, b = (min(fechas) if fechas else None), _parse_dt(fin)
    return (a, b) if a and b and b >= a else (None, None)


def _turno_en(dia: date, nombre: str, h1: int, h2: int) -> dict:
    base = datetime.combine(dia, datetime.min.time())
    return {"fecha": dia.isoformat(), "turno": nombre, "desde": (base + timedelta(hours=h1)).isoformat(timespec="minutes"),
            "hasta": (base + timedelta(hours=h2)).isoformat(timespec="minutes")}


def turnos_posibles(inicio: str, fin: str, amarre: str = "") -> list[dict]:
    """Turnos de 6 horas que se cruzan con el horario del Head Tally (del amarre al fin de la operacion).
    Cada uno: fecha del turno (la del dia en que empieza), nombre ('07-13') y desde/hasta."""
    a, b = _rango(inicio, fin, amarre)
    if not a:
        return []
    out = []
    dia = a.date() - timedelta(days=1)  # el turno 19-01 del dia anterior puede tocar el comienzo
    while dia <= b.date():
        for nombre, h1, h2 in TURNOS:
            t = _turno_en(dia, nombre, h1, h2)
            if datetime.fromisoformat(t["desde"]) < b and datetime.fromisoformat(t["hasta"]) > a:
                out.append(t)
        dia += timedelta(days=1)
    return out


def turnos_validos(inicio: str, fin: str, amarre: str = "") -> dict[tuple[str, str], dict]:
    """Todos los turnos que se pueden elegir: los de la lista y los extra (por ejemplo el del mooring), que son
    cualquiera de los cuatro turnos de los dias desde un dia antes del amarre hasta un dia despues del fin."""
    a, b = _rango(inicio, fin, amarre)
    if not a:
        return {}
    out = {}
    dia = a.date() - timedelta(days=1)
    while dia <= b.date() + timedelta(days=1):
        for nombre, h1, h2 in TURNOS:
            t = _turno_en(dia, nombre, h1, h2)
            out[(t["fecha"], nombre)] = t
        dia += timedelta(days=1)
    return out


def fecha_por_defecto(o: OperatedVessel) -> str:
    """La fecha del certificado: la de zarpada si ya esta cargada, si no hoy."""
    z = (o.zarpe or "")[:10]
    try:
        return date.fromisoformat(z).isoformat()
    except ValueError:
        return date.today().isoformat()
