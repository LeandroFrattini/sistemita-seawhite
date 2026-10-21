"""Encargados (Head Tally): padron, descomposicion del precio del turno y aportes con tope mensual.

Cada turno del Tally se paga al encargado como un jornal: el precio del paso 8 es el BRUTO. De ese bruto se descuenta O.S. 3 %, jubilacion 11 %, ley 3 %
y aporte sindical 3 %. Los tres primeros (O.S., jubilacion y ley) se descuentan turno por turno mientras al encargado le falten MAS de un margen (100.000 por defecto) para el
TOPE de sueldo bruto del mes (lo carga Administracion, mes a mes); cuando le faltan 100.000 o menos, los turnos siguientes van sin esos descuentos y se puede
pasar del tope. El aporte sindical se descuenta siempre. Cada mes se empieza de cero. El encargado que figura en cada turno NO sale en la proforma
final: solo en el Excel de encargados.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Encargado, EncargadoSuperoTope, EncargadoTope, EncargadoTurno
from .serenos_padron import cuil_valido

PADRON_INICIAL = [("Bruno Aceituno", "20-38320705-7"), ("Fernando Navarrete", "20-24546704-5")]
MARCADOR = "encargados_padron_inicial"

PCT_OS, PCT_JUBIL, PCT_SIND, PCT_LEY = 0.03, 0.11, 0.03, 0.03
PCT_APORTES = PCT_OS + PCT_JUBIL + PCT_LEY            # lo que tiene tope
TURNOS = ("01-07", "07-13", "13-19", "19-01")
MARGEN_DEFECTO = 100000.0                              # con menos de esto de diferencia al tope, ya no se descuentan aportes
PCT_PRODUCCION = 0.25                                  # «1era produccion»: 25 % del basico (la tarifa de aceite no tiene insalubridad)


def es_berthing(act) -> bool:
    """Los turnos de Head Tally que son BERTHING van en la proforma pero no se le liquidan al encargado."""
    return str(act or "").strip().upper().startswith("BERTHING")


def limpiar_nombre(txt) -> str:
    return " ".join(str(txt or "").split())[:40]


def sembrar_padron(db: Session) -> None:
    """Carga los dos encargados una sola vez (despues se editan desde Administracion)."""
    if db.get(AppSetting, MARCADOR):
        return
    existentes = {c for (c,) in db.execute(select(Encargado.cuil))}
    for nombre, cuil in PADRON_INICIAL:
        if cuil not in existentes:
            db.add(Encargado(nombre=nombre, cuil=cuil))
    db.add(AppSetting(key=MARCADOR, value="1"))


def _r2(n: float) -> float:
    return round(n + 0.0, 2)


def descomponer(base: dict, categoria: str, precio: float) -> dict:
    """El bruto del turno (su precio) repartido como en la declaracion jurada: basico, insalubridad, 1era produccion.
    Insalubridad y produccion son fijas (salen de la tarifa hábil de la categoria); el basico es el resto, asi el bruto siempre es el precio del turno."""
    aceite_h = base.get(("TALLY", "ACEITE", "H"), 0.0)
    cat_h = base.get(("TALLY", categoria, "H"), 0.0) if categoria else 0.0
    basico_h = aceite_h / (1 + PCT_PRODUCCION) if aceite_h else 0.0
    prod = _r2(aceite_h - basico_h)
    insal = _r2(max(cat_h - aceite_h, 0.0)) if categoria else 0.0
    if precio <= 0 or prod + insal > precio:  # precio escrito a mano que no alcanza para los adicionales: todo va como basico
        return {"basico": _r2(precio), "insal": 0.0, "prod": 0.0, "bruto": _r2(precio), "basico_h": _r2(basico_h), "insal_pct": 0.0}
    return {"basico": _r2(precio - insal - prod), "insal": insal, "prod": prod, "bruto": _r2(precio), "basico_h": _r2(basico_h),
            "insal_pct": (insal / basico_h) if basico_h else 0.0}


def tope_de(db: Session, mes: str) -> EncargadoTope | None:
    return db.scalar(select(EncargadoTope).where(EncargadoTope.mes == mes).order_by(EncargadoTope.id.desc()).limit(1))


def historial_topes(db: Session, mes: str | None = None, limite: int = 60) -> list[EncargadoTope]:
    q = select(EncargadoTope).order_by(EncargadoTope.id.desc()).limit(limite)
    if mes:
        q = select(EncargadoTope).where(EncargadoTope.mes == mes).order_by(EncargadoTope.id.desc()).limit(limite)
    return list(db.scalars(q))


def mes_valido(txt) -> str:
    t = str(txt or "").strip()
    try:
        date.fromisoformat(t + "-01")
    except ValueError:
        return ""
    return t if len(t) == 7 else ""


def marcados(db: Session, mes: str) -> set[int]:
    """Los encargados que se marcaron a mano como «supero el tope» en ese mes."""
    return {i for (i,) in db.execute(select(EncargadoSuperoTope.encargado_id).where(EncargadoSuperoTope.mes == mes))}


def marcar_supero(db: Session, encargado_id: int, mes: str, activo: bool, usuario: str) -> None:
    fila = db.scalar(select(EncargadoSuperoTope).where(EncargadoSuperoTope.encargado_id == encargado_id, EncargadoSuperoTope.mes == mes))
    if activo and fila is None:
        db.add(EncargadoSuperoTope(encargado_id=encargado_id, mes=mes, usuario=usuario[:60]))
    elif not activo and fila is not None:
        db.delete(fila)
    db.commit()


def _orden(fecha: str, turno: str) -> tuple[str, int]:
    return fecha, TURNOS.index(turno) if turno in TURNOS else 9


def margen(db: Session) -> float:
    from .proformador_calc import get_param

    return get_param(db, "encargados_margen_ars", MARGEN_DEFECTO)


def _aplicar_tope(turnos: list[dict], tope: float, margen: float = MARGEN_DEFECTO) -> None:
    """Recorre los turnos de UN encargado en UN mes, en orden. El tope es sobre el SUELDO BRUTO acumulado del mes. Cada turno se toma ENTERO: mientras falten
    mas de `margen` para el tope, paga aportes (O.S., jubilacion y ley) sobre todo su bruto (aunque con ese turno se pase del tope); cuando faltan `margen` o
    menos, ya no paga ninguno. Agrega a cada turno: base (el bruto sobre el que se calculan los aportes), os, jubil, ley, aportes y estado ('completo' o 'tope')."""
    acumulado = 0.0
    for t in sorted(turnos, key=lambda x: (_orden(x["fecha"], x["turno"]), x.get("orden", 0))):
        if tope - acumulado > margen + 1e-9:
            base, estado = t["bruto"], "completo"
        else:
            base, estado = 0.0, "tope"
        t["base"] = base
        t["os"], t["jubil"], t["ley"] = base * PCT_OS, base * PCT_JUBIL, base * PCT_LEY
        t["aportes"], t["estado"] = t["os"] + t["jubil"] + t["ley"], estado
        acumulado += t["bruto"]


def calcular(db: Session, *, barco_clave: str, filas: list[dict], categoria: str, base: dict, padron: list[tuple[int, str]]) -> dict:
    """Los turnos de Tally del barco con su encargado: bruto, descomposicion, aportes (con tope mensual) y neto.

    `filas`: turnos del paso 8 ya calculados (fecha, turno, precio, nombre). `padron`: [(id, nombre)]. ValueError si falta un encargado o el tope del mes."""
    if not filas:
        raise ValueError("No hay turnos de Tally cargados en el paso 8.")
    ids = {n.lower(): i for i, n in padron}
    faltan = []
    for f in filas:
        if not f.get("nombre"):
            a, b = f["turno"].split("-")
            faltan.append(f"Falta elegir el encargado del turno del {f['fecha'][8:10]}/{f['fecha'][5:7]} de {a} a {b}.")
    if faltan:
        raise ValueError(" ".join(faltan))
    if not categoria:
        raise ValueError("Falta elegir la categoría de la carga del Tally (paso 8).")
    actuales = []
    for i, f in enumerate(filas):
        d = descomponer(base, categoria, f["precio"])
        actuales.append({**f, **d, "orden": i, "actual": True, "encargado_id": ids.get(f["nombre"].lower())})
    marg = margen(db)
    # lo que ya cobraron esos encargados en esos meses en otros barcos
    por_clave: dict[tuple, list[dict]] = {}
    for t in actuales:
        por_clave.setdefault((t["encargado_id"] if t["encargado_id"] is not None else t["nombre"].lower(), t["fecha"][:7]), []).append(t)
    topes, manuales = {}, []
    for (clave, mes), lista in por_clave.items():
        if isinstance(clave, int) and clave in marcados(db, mes):  # marcado a mano como «supero el tope»: sin aportes en todo el mes
            tope_mes = 0.0
            manuales.append((lista[0]["nombre"], mes))
        else:
            if mes not in topes:
                t = tope_de(db, mes)
                if t is None:
                    raise ValueError(f"Falta cargar el tope de sueldo bruto de {mes[5:7]}/{mes[:4]} (Administración → Encargados), o marcar «Superó el tope» al encargado.")
                topes[mes] = t.monto
            tope_mes = topes[mes]
        q = select(EncargadoTurno).where(EncargadoTurno.fecha.like(mes + "%"), EncargadoTurno.barco_clave != barco_clave)
        q = q.where(EncargadoTurno.encargado_id == clave) if isinstance(clave, int) else q.where(EncargadoTurno.nombre == lista[0]["nombre"])
        for r in db.scalars(q):
            lista.append({"fecha": r.fecha, "turno": r.turno, "bruto": r.bruto, "orden": -1, "actual": False})
        _aplicar_tope(lista, tope_mes, marg)
    for t in actuales:
        t["sind"] = t["bruto"] * PCT_SIND
        t["neto"] = t["bruto"] - t["os"] - t["jubil"] - t["ley"] - t["sind"]
    actuales.sort(key=lambda t: (_orden(t["fecha"], t["turno"]), t["nombre"]))
    return {"filas": actuales, "topes": topes, "manuales": manuales, "margen": marg, "categoria": categoria}


def registrar(db: Session, *, barco_clave: str, buque: str, filas: list[dict], usuario: str) -> None:
    """Deja anotados los turnos de este barco (reemplaza los que habia de ese mismo barco)."""
    for r in db.scalars(select(EncargadoTurno).where(EncargadoTurno.barco_clave == barco_clave)):
        db.delete(r)
    for f in filas:
        db.add(EncargadoTurno(barco_clave=barco_clave, buque=buque[:120], encargado_id=f.get("encargado_id"), nombre=f["nombre"], fecha=f["fecha"],
                              turno=f["turno"], bruto=f["bruto"], usuario=usuario[:60]))
    db.commit()


def estado_mes(db: Session, mes: str) -> dict:
    """Para la pantalla de Administracion: por encargado de la lista, el bruto del mes contra el tope, lo que se le descontó de aportes y cuánto falta."""
    tope, marg = tope_de(db, mes), margen(db)
    marcas = marcados(db, mes)
    por: dict[str, list[dict]] = {e.nombre: [] for e in db.scalars(select(Encargado).order_by(Encargado.nombre))}
    cuils = {e.nombre: e.cuil for e in db.scalars(select(Encargado))}
    ids = {e.nombre: e.id for e in db.scalars(select(Encargado))}
    for r in db.scalars(select(EncargadoTurno).where(EncargadoTurno.fecha.like(mes + "%"))):
        por.setdefault(r.nombre, []).append({"fecha": r.fecha, "turno": r.turno, "bruto": r.bruto, "orden": 0, "buque": r.buque})
    out = []
    for nombre, lista in sorted(por.items()):
        manual = ids.get(nombre) in marcas
        if manual:
            _aplicar_tope(lista, 0.0, marg)
        elif tope is not None:
            _aplicar_tope(lista, tope.monto, marg)
        bruto = sum(t["bruto"] for t in lista)
        falta = (tope.monto - bruto) if tope is not None else None
        out.append({"id": ids.get(nombre), "nombre": nombre, "cuil": cuils.get(nombre, ""), "turnos": len(lista), "barcos": len({t["buque"] for t in lista}), "bruto": bruto,
                    "aportes": sum(t.get("aportes", 0.0) for t in lista) if (tope is not None or manual) else None,
                    "manual": manual, "falta": falta, "alcanzado": manual or (tope is not None and bool(lista) and falta <= marg),
                    "pct": (min(bruto / tope.monto, 1.0) if tope is not None and tope.monto else 0.0)})
    return {"mes": mes, "tope": tope, "margen": marg, "encargados": out}
