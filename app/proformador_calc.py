"""Motor de calculo del Proformador.

Formulas confirmadas contra PDAs reales de Blue Star (ver seed.py para los
valores base). Pilotaje/practicos: tarifario ESEM por calado, solo cargado
para el recorrido mas comun (Extranjero, I.White-Profertil, 1 practico) --
otros recorridos/banderas/2 practicos todavia no estan cargados.

Todos los montos se redondean a numeros enteros (sin decimales). Wharfage y
Channel Toll se redondean siempre PARA ARRIBA; el resto usa redondeo normal.
"""
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def calcular_fc(eslora, manga, puntal):
    if not eslora or not manga or not puntal:
        return None
    return round(eslora * manga * puntal / 800)


def get_param(db: Session, clave: str, default: float = 0.0) -> float:
    p = db.scalar(select(models.ProformaParametro).where(models.ProformaParametro.clave == clave))
    return p.valor if p else default


def _tramo(model_cls, db: Session, campo_tope: str, valor_col: str, referencia: float, default: float = 0.0):
    tramos = db.scalars(select(model_cls).order_by(model_cls.orden)).all()
    for t in tramos:
        tope = getattr(t, campo_tope)
        if tope is None or referencia <= tope:
            return getattr(t, valor_col)
    return getattr(tramos[-1], valor_col) if tramos else default


def coeficiente_channel_toll(db: Session, cantidad: float) -> float:
    return _tramo(models.ProformaCoefTramo, db, "hasta_toneladas", "coeficiente", cantidad, 1.0)


def tarifa_tug_por_loa(db: Session, eslora: float) -> float:
    return _tramo(models.ProformaTugTarifa, db, "hasta_loa", "valor_usd", eslora, 0.0)


def coeficiente_pilotage_por_calado(db: Session, calado_pies: float) -> float:
    return _tramo(models.ProformaPilotageTramo, db, "hasta_pies", "valor_usd", calado_pies, 0.0)


def calcular_pilotage(db: Session, uf: float, calado_pies: float) -> float:
    """Formula real del tarifario ESEM (Extranjero, I.White-Profertil, 1
    practico): UF = Eslora x Manga x Puntal / 800 (= FC, propio de cada
    barco), multiplicado por un %calado segun el tramo de calado de ESE
    movimiento (entrada o salida por separado)."""
    factor = coeficiente_pilotage_por_calado(db, calado_pies)
    if not factor or not uf:
        return 0.0
    coef_maniobra = get_param(db, "pilotage_coef_maniobra", 14.0)
    coef_navegacion = get_param(db, "pilotage_coef_navegacion", 8.0)
    coef_km = get_param(db, "pilotage_coef_km", 12.0)
    km = get_param(db, "pilotage_km_recorrido", 53.0)
    descuento = get_param(db, "pilotage_descuento", 0.2)
    service = get_param(db, "pilotage_service_usd", 6600.0)

    maniobra = (uf * coef_maniobra) * factor
    navegacion = (uf * coef_navegacion + coef_km * km) * factor
    tarifa_gobierno = (maniobra + navegacion) * (1 - descuento)
    return tarifa_gobierno + service


def tarifa_turno(db: Session, servicio: str, categoria: str, dia_tipo: str) -> float:
    t = db.scalar(
        select(models.ProformaTarifaTurno).where(
            models.ProformaTarifaTurno.servicio == servicio,
            models.ProformaTarifaTurno.categoria == categoria,
            models.ProformaTarifaTurno.dia_tipo == dia_tipo,
        )
    )
    return t.valor_ars_dia if t else 0.0


def _linea(concepto, monto, observacion="", informativo=False):
    return {"concepto": concepto, "monto_usd": round(monto or 0), "observacion": observacion, "informativo": informativo}


def calcular_proforma(db: Session, datos: dict) -> list[dict]:
    """datos esperados: dolar_venta, tipo_operacion, trn, cantidad, dias_muelle,
    dias_fondeo, remolques_in, remolques_out, turnos, tipo_carga,
    categoria_watchmen, dia_tipo, procede_exterior, destino_exterior,
    immigration_in_boya, immigration_out_boya, eslora"""
    dolar = float(datos.get("dolar_venta") or 0) or 1.0
    trn = float(datos.get("trn") or 0)
    cantidad = float(datos.get("cantidad") or 0)
    dias_muelle = float(datos.get("dias_muelle") or 0)
    dias_fondeo = float(datos.get("dias_fondeo") or 0)
    turnos = float(datos.get("turnos") or 0)
    eslora = float(datos.get("eslora") or 0)
    manga = float(datos.get("manga") or 0)
    puntal = float(datos.get("puntal") or 0)
    remolques_in = int(datos.get("remolques_in") or 0)
    remolques_out = int(datos.get("remolques_out") or 0)
    calado_entrada = float(datos.get("calado_entrada") or 0)
    calado_salida = float(datos.get("calado_salida") or 0)
    # UF (Unidad Fiscal) sin redondear -- el "FC" que se muestra es solo
    # informativo/redondeado, la formula de pilotaje necesita el valor real
    uf = (eslora * manga * puntal / 800) if (eslora and manga and puntal) else 0.0
    tipo_operacion = datos.get("tipo_operacion") or "Carga"
    dia_tipo = datos.get("dia_tipo") or "SEMANA"
    accion = "LOADING" if tipo_operacion != "Descarga" else "DISCHARGING"

    lineas = []

    # Pilotaje/practicaje -- se cobra por movimiento (entrada y salida por
    # separado, cada uno con su propio calado), en base a la Unidad Fiscal
    # (UF, = FC) de ESTE barco. Solo recorrido Extranjero I.White-Profertil,
    # 1 practico (el mas comun); otros recorridos/banderas todavia no
    # estan cargados.
    if calado_entrada:
        valor = calcular_pilotage(db, uf, calado_entrada)
        if valor:
            lineas.append(_linea("PILOTAGE IN", valor, "BASIS OUR TARIFF WITH SERVICE PROVIDER"))
    if calado_salida:
        valor = calcular_pilotage(db, uf, calado_salida)
        if valor:
            lineas.append(_linea("PILOTAGE OUT", valor, "BASIS OUR TARIFF WITH SERVICE PROVIDER"))

    wharfage_rate = get_param(db, "wharfage_usd_trn_dia", 0.46)
    channel_toll_rate = get_param(db, "channel_toll_usd_tn", 2.05)
    fondeadero_rate = get_param(db, "fondeadero_usd_trn_dia", 0.15)

    if dias_muelle and trn:
        lineas.append(_linea(
            "WHARFAGE (Uso de muelle)", math.ceil(wharfage_rate * trn * dias_muelle),
            f"BASIS {dias_muelle:g} COMPLETE DAY(S) OF PORT STAY",
        ))

    if cantidad:
        coef = coeficiente_channel_toll(db, cantidad)
        lineas.append(_linea(
            "CHANNEL TOLL (Vias navegables)", math.ceil(channel_toll_rate * cantidad * coef),
            f"BASIS {cantidad:g} MT OF CARGO",
        ))

    if tipo_operacion == "Bunker" and dias_fondeo and trn:
        lineas.append(_linea(
            "USO DE FONDEADERO", fondeadero_rate * trn * dias_fondeo,
            f"BASIS {dias_fondeo:g} DAY(S) AT ANCHORAGE",
        ))

    # Free Pratique: solo se cobra si el barco procede del exterior
    if trn and datos.get("procede_exterior"):
        coef_a = get_param(db, "libre_platica_coef", 6942.9)
        base = get_param(db, "libre_platica_base", 416574)
        resta_trn = get_param(db, "libre_platica_resta_trn", 1001)
        ars = ((trn - resta_trn) / 1000) * coef_a + base
        lineas.append(_linea(
            "FREE PRATIQUE EXPENSES", ars / dolar, f"BASIS TRN {trn:g}",
        ))

    # Tugs -- informativo, discriminado en/salida
    if eslora and (remolques_in or remolques_out):
        valor_tug = tarifa_tug_por_loa(db, eslora)
        if remolques_in:
            lineas.append(_linea(
                "TUGS IN", valor_tug * remolques_in,
                "BASIS OUR TARIFF WITH SERVICE PROVIDER", informativo=True,
            ))
        if remolques_out:
            lineas.append(_linea(
                "TUGS OUT", valor_tug * remolques_out,
                "BASIS OUR TARIFF WITH SERVICE PROVIDER", informativo=True,
            ))

    # Watchmen: en base a DIAS COMPLETOS de estadia (no a los turnos)
    if dias_muelle:
        categoria_watchmen = datos.get("categoria_watchmen") or "NORMAL"
        sereno_dia = tarifa_turno(db, "SERENO", categoria_watchmen, dia_tipo)
        if sereno_dia:
            lineas.append(_linea(
                "WATCHMEN", (sereno_dia * dias_muelle) / dolar,
                f"BASIS {dias_muelle:g} COMPLETE DAY(S) OF PORT STAY",
            ))

    # Tally: en base a los SHIFTS (turnos)
    if turnos:
        categoria_tally = datos.get("tipo_carga") or "ACEITE"
        tally_dia = tarifa_turno(db, "TALLY", categoria_tally, dia_tipo)
        if tally_dia:
            lineas.append(_linea(
                "HEAD TALLY CLERK", (tally_dia / 4 * turnos) / dolar,
                f"BASIS {turnos:g} SHIFT(S) FOR {accion} ALL CARGO",
            ))

    conceptos_fijos = db.scalars(
        select(models.ProformaConceptoFijo).where(models.ProformaConceptoFijo.activo == True)
        .order_by(models.ProformaConceptoFijo.orden)
    ).all()

    # Immigration: si se hace en boya (in y/o out), un unico cargo fijo;
    # si no, los conceptos normales condicionados a procedencia/destino
    inmigracion_en_boya = datos.get("immigration_in_boya") or datos.get("immigration_out_boya")
    if inmigracion_en_boya:
        monto_boya = get_param(db, "immigration_boya_usd", 1875.0)
        lineas.append(_linea("IMMIGRATION (AT BUOY)", monto_boya, "BASIS CLEARANCE AT BUOY"))

    for c in conceptos_fijos:
        if c.clave == "immigration_in":
            if inmigracion_en_boya or not datos.get("procede_exterior"):
                continue
            lineas.append(_linea(c.nombre, c.valor_usd, "BASIS ENTRANCE CLEARANCE AT BERTH"))
        elif c.clave == "immigration_out":
            if inmigracion_en_boya or not datos.get("destino_exterior"):
                continue
            lineas.append(_linea(c.nombre, c.valor_usd, "BASIS DEPARTURE CLEARANCE AT BERTH"))
        else:
            lineas.append(_linea(c.nombre, c.valor_usd, c.condicion or ""))

    return lineas
