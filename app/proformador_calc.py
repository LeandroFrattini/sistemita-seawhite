"""Motor de calculo del Proformador.

Formulas confirmadas contra PDAs reales de Blue Star (ver seed.py para los
valores base). Pilotaje/practicos queda afuera a proposito: va por calado,
es un mundo aparte con su propio tarifario.
"""
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
    return {"concepto": concepto, "monto_usd": round(monto or 0, 2), "observacion": observacion, "informativo": informativo}


def calcular_proforma(db: Session, datos: dict) -> list[dict]:
    """datos esperados: dolar_venta, tipo_operacion, trn, cantidad, dias_muelle,
    dias_fondeo, cantidad_remolques, turnos, tipo_carga, categoria_watchmen,
    dia_tipo, procede_exterior, destino_exterior, eslora"""
    dolar = float(datos.get("dolar_venta") or 0) or 1.0
    trn = float(datos.get("trn") or 0)
    cantidad = float(datos.get("cantidad") or 0)
    dias_muelle = float(datos.get("dias_muelle") or 0)
    dias_fondeo = float(datos.get("dias_fondeo") or 0)
    turnos = float(datos.get("turnos") or 0)
    eslora = float(datos.get("eslora") or 0)
    cantidad_remolques = int(datos.get("cantidad_remolques") or 0)
    tipo_operacion = datos.get("tipo_operacion") or "Carga"
    dia_tipo = datos.get("dia_tipo") or "SEMANA"

    lineas = []

    wharfage_rate = get_param(db, "wharfage_usd_trn_dia", 0.46)
    channel_toll_rate = get_param(db, "channel_toll_usd_tn", 2.05)
    fondeadero_rate = get_param(db, "fondeadero_usd_trn_dia", 0.15)

    if dias_muelle and trn:
        lineas.append(_linea(
            "WHARFAGE (Uso de muelle)", wharfage_rate * trn * dias_muelle,
            f"USD {wharfage_rate:g} x TRN {trn:g} x {dias_muelle:g} dia(s)",
        ))

    if cantidad:
        coef = coeficiente_channel_toll(db, cantidad)
        lineas.append(_linea(
            "CHANNEL TOLL (Vias navegables)", channel_toll_rate * cantidad * coef,
            f"USD {channel_toll_rate:g} x {cantidad:g} tn x coef {coef:g}",
        ))

    if tipo_operacion == "Bunker" and dias_fondeo and trn:
        lineas.append(_linea(
            "USO DE FONDEADERO", fondeadero_rate * trn * dias_fondeo,
            f"USD {fondeadero_rate:g} x TRN {trn:g} x {dias_fondeo:g} dia(s)",
        ))

    if trn:
        coef_a = get_param(db, "libre_platica_coef", 6942.9)
        base = get_param(db, "libre_platica_base", 416574)
        resta_trn = get_param(db, "libre_platica_resta_trn", 1001)
        ars = ((trn - resta_trn) / 1000) * coef_a + base
        lineas.append(_linea(
            "FREE PRATIQUE EXPENSES", ars / dolar, f"Basis TRN {trn:g} (calculado en ARS / TC {dolar:g})",
        ))

    if eslora and cantidad_remolques:
        valor_tug = tarifa_tug_por_loa(db, eslora)
        lineas.append(_linea(
            "TUGS", valor_tug * cantidad_remolques,
            f"{cantidad_remolques} remolcador(es) x USD {valor_tug:g} segun LOA {eslora:g} -- informativo",
            informativo=True,
        ))

    if turnos:
        categoria_watchmen = datos.get("categoria_watchmen") or "NORMAL"
        sereno_dia = tarifa_turno(db, "SERENO", categoria_watchmen, dia_tipo)
        if sereno_dia:
            lineas.append(_linea(
                "WATCHMEN (Serenos)", (sereno_dia / 4 * turnos) / dolar,
                f"ARS {sereno_dia:g}/dia [{categoria_watchmen}/{dia_tipo}] / 4 x {turnos:g} turno(s) / TC {dolar:g}",
            ))
        categoria_tally = datos.get("tipo_carga") or "ACEITE"
        tally_dia = tarifa_turno(db, "TALLY", categoria_tally, dia_tipo)
        if tally_dia:
            lineas.append(_linea(
                "HEAD TALLY CLERK", (tally_dia / 4 * turnos) / dolar,
                f"ARS {tally_dia:g}/dia [{categoria_tally}/{dia_tipo}] / 4 x {turnos:g} turno(s) / TC {dolar:g}",
            ))

    conceptos_fijos = db.scalars(
        select(models.ProformaConceptoFijo).where(models.ProformaConceptoFijo.activo == True)
        .order_by(models.ProformaConceptoFijo.orden)
    ).all()
    for c in conceptos_fijos:
        if c.clave == "immigration_in" and not datos.get("procede_exterior"):
            continue
        if c.clave == "immigration_out" and not datos.get("destino_exterior"):
            continue
        lineas.append(_linea(c.nombre, c.valor_usd, c.condicion or ""))

    return lineas
