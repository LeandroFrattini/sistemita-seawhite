"""Tally (Head Tally = encargado) y Serenos de la proforma final.

Las tarifas son las de la Camara Portuaria y Maritima de Bahia Blanca (archivo «serenos y encargado.xlsx», agosto 2026), en pesos
por turno de 6 horas, y se guardan en la base con su vigencia (TarifaPersonal) para actualizarlas cada mes.

TALLY (encargado). Cada turno del voucher (01-07, 07-13, 13-19, 19-01) cae en un escalon segun el dia y la hora:
    dia de semana  07-13 y 13-19 .......... BASICO (H)          | sabado 07-13 ........................ BASICO (H)
    dia de semana  19-01 y 01-07 .......... EXTRA 100 %         | sabado 01-07 y 13-19 ................ EXTRA 100 %
    domingo 07-13 y 13-19 ................. EXTRA 100 %         | sabado 19-01, domingo 01-07 y 19-01 . EXTRA 150 %
    feriado y dia no laborable (todo el dia) .... 3 x el turno BASICO de la categoria
  El precio sale de la categoria de la carga (aceite, cereal, bolsones/materiales o fertilizantes). Se suman las cargas sociales de la agencia.
SERENOS. Turnos de 6 horas (00-06, 06-12, 12-18, 18-24) desde el amarre hasta el zarpe:
    HABIL: 06-12 y 12-18 de dia de semana, y sabado 06-12 | INHABIL: 00-06 y 18-24 de dia de semana, y sabado 00-06, 12-18 y 18-24
    DOMINGO: domingos y feriados (todo el dia; manda la tabla)
  Categoria NORMAL, INSALUBRE o PELIGROSO. Se suman las cargas sociales de la agencia sobre los sueldos (no sobre los viaticos) y los viaticos
  por turno segun el sitio (White o Galvan).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendario import conjuntos
from .models import TarifaPersonal
from .proforma_final import tipo_dia

TURNOS_TALLY = ("01-07", "07-13", "13-19", "19-01")
VENTANAS_SERENOS = ("00-06", "06-12", "12-18", "18-24")
CATEGORIAS_TALLY = {"ACEITE": "Aceite", "CEREAL": "Cereal", "BOLSONES": "Bolsones / materiales", "FERTILIZANTES": "Fertilizantes"}
CATEGORIAS_SERENOS = {"NORMAL": "Normal (aceite)", "INSALUBRE": "Insalubre (cereal, fertilizantes, bolsones)", "PELIGROSO": "Peligroso (amoníaco, gasoil, posta)"}
VIATICOS = {"WHITE": "Viáticos White", "GALVAN": "Viáticos Galván"}
NIVELES_TALLY = {"H": "Básico (hábil)", "100": "Extra 100 %", "150": "Extra 150 %", "F3": "Feriado (×3)"}
TIERS_SERENOS = {"HABIL": "Día hábil", "INHABIL": "Día inhábil", "DOMINGO": "Domingo y feriado"}
FACTOR_FERIADO_TALLY = 3

VIGENCIA_SEMILLA = "2026-08-01"
# (servicio, categoria, nivel, ARS por turno): tabla de agosto 2026
TARIFAS_SEMILLA = [
    ("TALLY", "ACEITE", "H", 264807.54), ("TALLY", "ACEITE", "100", 476653.57), ("TALLY", "ACEITE", "150", 582576.59),
    ("TALLY", "CEREAL", "H", 328361.35), ("TALLY", "CEREAL", "100", 540207.38), ("TALLY", "CEREAL", "150", 646130.40),
    ("TALLY", "BOLSONES", "H", 370730.56), ("TALLY", "BOLSONES", "100", 582576.59), ("TALLY", "BOLSONES", "150", 688499.61),
    ("TALLY", "FERTILIZANTES", "H", 434284.37), ("TALLY", "FERTILIZANTES", "100", 646130.40), ("TALLY", "FERTILIZANTES", "150", 752053.42),
    ("SERENO", "NORMAL", "HABIL", 193493.56), ("SERENO", "NORMAL", "INHABIL", 290239.54), ("SERENO", "NORMAL", "DOMINGO", 386930.38),
    ("SERENO", "INSALUBRE", "HABIL", 290229.31), ("SERENO", "INSALUBRE", "INHABIL", 435353.11), ("SERENO", "INSALUBRE", "DOMINGO", 580462.60),
    ("SERENO", "PELIGROSO", "HABIL", 348316.28), ("SERENO", "PELIGROSO", "INHABIL", 522503.33), ("SERENO", "PELIGROSO", "DOMINGO", 696633.10),
    ("VIATICO", "WHITE", "TURNO", 17588.21), ("VIATICO", "GALVAN", "TURNO", 28710.71),
]


def sembrar(db: Session) -> None:
    """Carga la tabla de agosto 2026 la primera vez (despues se mantiene desde la pantalla de tarifas)."""
    if db.scalar(select(TarifaPersonal).limit(1)):
        return
    for servicio, categoria, nivel, valor in TARIFAS_SEMILLA:
        db.add(TarifaPersonal(servicio=servicio, categoria=categoria, nivel=nivel, valor=valor, vigencia=VIGENCIA_SEMILLA))


def tabla(db: Session, ref: date | None) -> tuple[dict[tuple[str, str, str], float], str]:
    """Tarifas vigentes a la fecha `ref`: para cada (servicio, categoria, nivel), la ultima vigencia que no pasa de esa fecha
    (si todas son posteriores, la mas antigua). Devuelve la tabla y la vigencia mas reciente usada."""
    iso = (ref or date.today()).isoformat()
    elegidas: dict[tuple[str, str, str], TarifaPersonal] = {}
    for r in db.scalars(select(TarifaPersonal).order_by(TarifaPersonal.vigencia)):
        k = (r.servicio, r.categoria, r.nivel)
        if k not in elegidas or r.vigencia <= iso:
            elegidas[k] = r
    return {k: r.valor for k, r in elegidas.items()}, max((r.vigencia for r in elegidas.values()), default="")


def _d(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _dt(raw) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------------------- reglas
_TALLY_SABADO = {"01-07": "100", "07-13": "H", "13-19": "100", "19-01": "150"}
_TALLY_DOMINGO = {"01-07": "150", "07-13": "100", "13-19": "100", "19-01": "150"}


def nivel_tally(fecha: date, turno: str, feriados: set[str], no_laborables: set[str]) -> tuple[str, str]:
    """(tipo de dia, escalon) de un turno de Head Tally. La fecha es la del dia en que empieza el turno."""
    tipo = tipo_dia(fecha, feriados, no_laborables)
    if tipo in ("FERIADO", "NO_LABORABLE"):
        return tipo, "F3"
    if tipo == "SABADO":
        return tipo, _TALLY_SABADO[turno]
    if tipo == "DOMINGO":
        return tipo, _TALLY_DOMINGO[turno]
    return tipo, "H" if turno in ("07-13", "13-19") else "100"


def tier_sereno(fecha: date, ventana: str, feriados: set[str], no_laborables: set[str]) -> tuple[str, str]:
    """(tipo de dia, tarifa) de un turno de serenos. Los feriados (y los dias no laborables) se cobran todo como domingo."""
    tipo = tipo_dia(fecha, feriados, no_laborables)
    if tipo in ("FERIADO", "NO_LABORABLE", "DOMINGO"):
        return tipo, "DOMINGO"
    if tipo == "SABADO":
        return tipo, "HABIL" if ventana == "06-12" else "INHABIL"
    return tipo, "HABIL" if ventana in ("06-12", "12-18") else "INHABIL"


def ventanas_serenos(amarre: str, zarpe: str) -> list[dict]:
    """Turnos de serenos desde el amarre hasta el zarpe: todas las ventanas de 6 horas que el barco toca en algun momento."""
    a, b = _dt(amarre), _dt(zarpe)
    if not a or not b or b <= a:
        return []
    out = []
    dia = a.date()
    while dia <= b.date():
        base = datetime.combine(dia, datetime.min.time())
        for v in VENTANAS_SERENOS:
            h1 = int(v[:2])
            ini, fin = base + timedelta(hours=h1), base + timedelta(hours=h1 + 6)
            if a < fin and b > ini:
                out.append({"fecha": dia.isoformat(), "ventana": v, "cat": "", "cant": 1, "precio": 0, "nombre": ""})
        dia += timedelta(days=1)
    return out


# ----------------------------------------------------------------------------------------------------------- calculos
def _r2(n: float) -> float:
    return round(n + 0.0, 2)


def calcular_tally(db: Session, *, categoria: str, turnos: list[dict], precios: dict, pct: float, dolar: float, ref: date | None) -> dict:
    """Tally: cada turno a su escalon, precio por escalon (de la categoria, o el escrito a mano), cargas sociales y total en pesos y dolares."""
    feriados, no_lab = conjuntos(db)
    base, vigencia = tabla(db, ref or next((_d(t.get("fecha")) for t in turnos if _d(t.get("fecha"))), None))
    cat = categoria if categoria in CATEGORIAS_TALLY else ""
    h = base.get(("TALLY", cat, "H"), 0.0) if cat else 0.0
    de_tabla = {"H": h, "100": base.get(("TALLY", cat, "100"), 0.0) if cat else 0.0,
                "150": base.get(("TALLY", cat, "150"), 0.0) if cat else 0.0, "F3": h * FACTOR_FERIADO_TALLY}
    filas, cuenta = [], {k: 0 for k in NIVELES_TALLY}
    for t in turnos:
        f = _d(t.get("fecha"))
        if not f or t.get("turno") not in TURNOS_TALLY:
            continue
        tipo, auto = nivel_tally(f, t["turno"], feriados, no_lab)
        nivel = t.get("nivel") if t.get("nivel") in NIVELES_TALLY else auto
        cuenta[nivel] += 1
        filas.append({"fecha": f.isoformat(), "turno": t["turno"], "act": t.get("act") or "", "tipo_dia": tipo, "nivel_auto": auto, "nivel": nivel})
    resumen, subtotal = [], 0.0
    for nivel, etiqueta in NIVELES_TALLY.items():
        manual = float(precios.get(nivel) or 0)
        precio = manual if manual > 0 else de_tabla[nivel]
        total = cuenta[nivel] * precio
        subtotal += total
        resumen.append({"nivel": nivel, "etiqueta": etiqueta, "cantidad": cuenta[nivel], "precio": _r2(precio), "precio_tabla": _r2(de_tabla[nivel]),
                        "manual": manual > 0, "total": _r2(total)})
    for fl in filas:
        fl["precio"] = next(r["precio"] for r in resumen if r["nivel"] == fl["nivel"])
    cargas = subtotal * pct / 100
    total = subtotal + cargas
    return {"categoria": cat, "vigencia": vigencia, "filas": filas, "resumen": resumen, "subtotal": _r2(subtotal), "cargas_pct": pct, "cargas": _r2(cargas),
            "total": _r2(total), "total_usd": _r2(total / dolar) if dolar else None, "faltan": [] if cat else ["categoria"]}


def calcular_serenos(db: Session, *, categoria: str, viatico: str, viatico_precio: float, turnos: list[dict] | None, amarre: str, zarpe: str,
                     pct: float, dolar: float, ref: date | None) -> dict:
    """Serenos: tarifa de cada turno segun el dia, la hora y la categoria; cargas sociales sobre los sueldos; viaticos por turno aparte."""
    feriados, no_lab = conjuntos(db)
    generados = turnos is None
    filas_in = ventanas_serenos(amarre, zarpe) if generados else turnos
    base, vigencia = tabla(db, ref or _d(amarre) or next((_d(t.get("fecha")) for t in filas_in if _d(t.get("fecha"))), None))
    cat_global = categoria if categoria in CATEGORIAS_SERENOS else ""
    filas, subtotal, cantidad = [], 0.0, 0
    for t in filas_in:
        f = _d(t.get("fecha"))
        if not f or t.get("ventana") not in VENTANAS_SERENOS:
            continue
        cat = t.get("cat") if t.get("cat") in CATEGORIAS_SERENOS else cat_global
        tipo, tier = tier_sereno(f, t["ventana"], feriados, no_lab)
        cant = 1  # en cada turno va un solo sereno (nunca dos)
        manual = float(t.get("precio") or 0)
        unit = manual if manual > 0 else (base.get(("SERENO", cat, tier), 0.0) if cat else 0.0)
        total = unit * cant
        subtotal += total
        cantidad += cant
        filas.append({"fecha": f.isoformat(), "ventana": t["ventana"], "cat": t.get("cat") if t.get("cat") in CATEGORIAS_SERENOS else "", "cat_efectiva": cat,
                      "cant": cant, "nombre": " ".join(str(t.get("nombre") or "").split())[:40].upper(), "tipo_dia": tipo, "tier": tier, "precio_tabla": _r2(base.get(("SERENO", cat, tier), 0.0)) if cat else 0.0,
                      "precio": _r2(unit), "manual": manual > 0, "total": _r2(total)})
    v = viatico if viatico in VIATICOS else ""
    v_tabla = base.get(("VIATICO", v, "TURNO"), 0.0) if v else 0.0
    v_unit = viatico_precio if viatico_precio > 0 else v_tabla
    viaticos = v_unit * cantidad if v else 0.0
    cargas = subtotal * pct / 100
    total = subtotal + cargas + viaticos
    faltan = (["categoria"] if not cat_global and any(not fl["cat"] for fl in filas) else []) + (["viatico"] if filas and not v and viatico != "NINGUNO" else [])
    out = {"categoria": cat_global, "vigencia": vigencia, "filas": filas, "cantidad": cantidad, "subtotal": _r2(subtotal), "cargas_pct": pct, "cargas": _r2(cargas),
           "viatico": {"tipo": v, "unit": _r2(v_unit), "unit_tabla": _r2(v_tabla), "manual": viatico_precio > 0, "cantidad": cantidad, "total": _r2(viaticos)},
           "total": _r2(total), "total_usd": _r2(total / dolar) if dolar else None, "faltan": faltan}
    if generados:
        out["turnos_auto"] = filas_in
    return out


# ------------------------------------------------------------------------------------------------ limpieza del estado
def _fecha(raw) -> str:
    d = _d(raw)
    return d.isoformat() if d else ""


def _num(v, tope: float) -> float:
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0
    return round(n, 4) if 0 <= n <= tope else 0.0


def clean_tally(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    turnos = []
    for t in (raw.get("turnos") if isinstance(raw.get("turnos"), list) else [])[:120]:
        if isinstance(t, dict) and _fecha(t.get("fecha")) and str(t.get("turno")) in TURNOS_TALLY:
            turnos.append({"fecha": _fecha(t["fecha"]), "turno": str(t["turno"]), "act": " ".join(str(t.get("act") or "").split())[:30].upper(),
                           "nivel": t.get("nivel") if t.get("nivel") in NIVELES_TALLY else "",
                           "nombre": " ".join(str(t.get("nombre") or "").split())[:40]})  # el encargado: solo sale en el Excel de encargados
    pr = raw.get("precios") if isinstance(raw.get("precios"), dict) else {}
    resumen = []
    for r in (raw.get("resumen") if isinstance(raw.get("resumen"), list) else [])[:4]:
        if isinstance(r, dict) and r.get("nivel") in NIVELES_TALLY:
            resumen.append({"nivel": r["nivel"], "cantidad": int(_num(r.get("cantidad"), 1000)), "precio": _num(r.get("precio"), 1e12)})
    return {"categoria": raw.get("categoria") if raw.get("categoria") in CATEGORIAS_TALLY else "", "armado": bool(raw.get("armado")), "turnos": turnos,
            "cuenta_ajena": bool(raw.get("cuenta_ajena")), "omitido": bool(raw.get("omitido")) and not raw.get("cuenta_ajena"),
            "precios": {k: _num(pr.get(k), 1e12) for k in NIVELES_TALLY}, "resumen": resumen,
            "subtotal_ars": _num(raw.get("subtotal_ars"), 1e13), "cargas_ars": _num(raw.get("cargas_ars"), 1e13), "total_ars": _num(raw.get("total_ars"), 1e13)}


def clean_serenos(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    turnos = []
    for t in (raw.get("turnos") if isinstance(raw.get("turnos"), list) else [])[:200]:
        if isinstance(t, dict) and _fecha(t.get("fecha")) and str(t.get("ventana")) in VENTANAS_SERENOS:
            turnos.append({"fecha": _fecha(t["fecha"]), "ventana": str(t["ventana"]), "cat": t.get("cat") if t.get("cat") in CATEGORIAS_SERENOS else "",
                           "cant": 1, "precio": _num(t.get("precio"), 1e12),
                           "nombre": " ".join(str(t.get("nombre") or "").split())[:40].upper()})
    return {"categoria": raw.get("categoria") if raw.get("categoria") in CATEGORIAS_SERENOS else "",
            "viatico": raw.get("viatico") if raw.get("viatico") in (*VIATICOS, "NINGUNO") else "", "viatico_precio": _num(raw.get("viatico_precio"), 1e12),
            "armado": bool(raw.get("armado")), "turnos": turnos, "cantidad": int(_num(raw.get("cantidad"), 10000)), "cuenta_ajena": bool(raw.get("cuenta_ajena")),
            "omitido": bool(raw.get("omitido")) and not raw.get("cuenta_ajena"),
            "subtotal_ars": _num(raw.get("subtotal_ars"), 1e13), "cargas_ars": _num(raw.get("cargas_ars"), 1e13),
            "viaticos_ars": _num(raw.get("viaticos_ars"), 1e13), "total_ars": _num(raw.get("total_ars"), 1e13)}
