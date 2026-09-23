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


def calcular_pilotage(db: Session, uf: float, calado_pies: float, *, km_clave: str = "pilotage_km_recorrido",
                       service_clave: str = "pilotage_service_usd", dos_practicos: bool = False) -> float:
    """Formula real del tarifario ESEM: UF = Eslora x Manga x Puntal / 800
    (= FC, propio de cada barco), multiplicado por un %calado segun el
    tramo de calado de ESE movimiento (entrada o salida por separado).
    Por defecto usa el recorrido Extranjero I.White-Profertil, 1 practico;
    para el recorrido Monoboyas (Boya 17) se pasan las claves alternativas
    (km y service distintos, el resto de los coeficientes es igual).
    dos_practicos (manga > 39.9m, en cualquier ruta): duplica la tarifa de
    gobierno (Maniobra+Navegacion) -- el service/related fijo NO se duplica."""
    factor = coeficiente_pilotage_por_calado(db, calado_pies)
    if not factor or not uf:
        return 0.0
    coef_maniobra = get_param(db, "pilotage_coef_maniobra", 14.0)
    coef_navegacion = get_param(db, "pilotage_coef_navegacion", 8.0)
    coef_km = get_param(db, "pilotage_coef_km", 12.0)
    km = get_param(db, km_clave, 53.0)
    descuento = get_param(db, "pilotage_descuento", 0.2)
    service = get_param(db, service_clave, 6600.0)

    maniobra = (uf * coef_maniobra) * factor
    navegacion = (uf * coef_navegacion + coef_km * km) * factor
    tarifa_gobierno = (maniobra + navegacion) * (1 - descuento)
    if dos_practicos:
        tarifa_gobierno *= 2
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
    # estan cargados. Si la manga supera 39.9m (40m), va tarifario de DOS
    # PRACTICOS: se duplica la tarifa de gobierno (igual que en Otamerica).
    dos_practicos = manga > 39.9
    remark_pilotage = "BASIS OUR TARIFF WITH SERVICE PROVIDER" + (
        " (TWO PILOTS -- BEAM OVER 40M)" if dos_practicos else ""
    )
    if calado_entrada:
        valor = calcular_pilotage(db, uf, calado_entrada, dos_practicos=dos_practicos)
        if valor:
            lineas.append(_linea("PILOTAGE IN", valor, remark_pilotage))
    if calado_salida:
        valor = calcular_pilotage(db, uf, calado_salida, dos_practicos=dos_practicos)
        if valor:
            lineas.append(_linea("PILOTAGE OUT", valor, remark_pilotage))

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


def get_boya(db: Session, boya: str) -> "models.ProformaBunkerBoya | None":
    return db.scalar(select(models.ProformaBunkerBoya).where(models.ProformaBunkerBoya.boya == boya))


def calcular_bunker(db: Session, datos: dict) -> list[dict]:
    """Proforma de bunker (Boya 3 / Boya 11 / Boya 17) -- barco que solo se
    desvia a tomar combustible, no toca muelle. Formulas confirmadas contra
    ejemplos reales (Geogas/Indianapolis)."""
    dolar = float(datos.get("dolar_venta") or 0) or 1.0
    trn = float(datos.get("trn") or 0)
    eslora = float(datos.get("eslora") or 0)
    manga = float(datos.get("manga") or 0)
    puntal = float(datos.get("puntal") or 0)
    calado_entrada = float(datos.get("calado_entrada") or 0)
    calado_salida = float(datos.get("calado_salida") or 0)
    dias_estadia = float(datos.get("dias_estadia") or 0)
    cantidad_barcazas = float(datos.get("cantidad_barcazas") or 1)
    turnos_clearance = float(datos.get("turnos_customs_clearance") or 0)
    turnos_bunker_control = float(datos.get("turnos_customs_bunker_control") or 0)
    usa_boat = bool(datos.get("usa_boat_surveyor"))
    horas_boat = float(datos.get("horas_boat_surveyor") or 0)
    turnos_sipa = float(datos.get("turnos_sipa") or 0)
    uf = (eslora * manga * puntal / 800) if (eslora and manga and puntal) else 0.0

    boya_cfg = get_boya(db, datos.get("boya") or "BOYA_11")
    lineas = []

    if boya_cfg and boya_cfg.cobra_pilotage:
        if calado_entrada:
            v = calcular_pilotage(db, uf, calado_entrada, km_clave="pilotage_monoboya_km",
                                   service_clave="pilotage_monoboya_service_usd")
            if v:
                lineas.append(_linea("PILOTAGE IN", v, "BASIS OUR TARIFF WITH SERVICE PROVIDER"))
        if calado_salida:
            v = calcular_pilotage(db, uf, calado_salida, km_clave="pilotage_monoboya_km",
                                   service_clave="pilotage_monoboya_service_usd")
            if v:
                lineas.append(_linea("PILOTAGE OUT", v, "BASIS OUR TARIFF WITH SERVICE PROVIDER"))

    if boya_cfg and boya_cfg.cobra_channel_anchor and trn:
        anchor_rate = get_param(db, "bunker_anchor_dues_usd_trn", 0.15)
        lineas.append(_linea(
            "ANCHOR DUES", anchor_rate * trn * (dias_estadia or 1),
            "PER DAY OF STAY (divided in 3 thirds -- 0000/0800, 0800/1600, 1600/2400)",
        ))
        toll_rate = get_param(db, "bunker_channel_toll_usd_tn", 2.05)
        coef = coeficiente_channel_toll(db, trn)
        lineas.append(_linea(
            "CHANNEL TOLL", toll_rate * (0.2 * trn) * coef * 0.7, "",
        ))

    shift_usd = get_param(db, "bunker_customs_shift_usd", 300.0)
    if turnos_clearance:
        lineas.append(_linea(
            "CUSTOMS FOR CLEARANCE", shift_usd * turnos_clearance,
            "300 (ABT) PER SHIFT OF 6 HOURS -- MINIMUM 2 SHIFTS REQUIRED FOR CLEARANCES AT ROADS.",
        ))
    if turnos_bunker_control:
        lineas.append(_linea(
            "CUSTOMS FOR BUNKER CONTROL", shift_usd * turnos_bunker_control,
            "300 (ABT) PER SHIFT OF 6 HOURS -- USUALLY MIN. 4 SHIFTS ARE REQUIRED TO COVER POSSIBLE BUNKERING DELAYS.",
        ))

    if boya_cfg and cantidad_barcazas:
        lineas.append(_linea(
            "OSRO CERTIFICATE", boya_cfg.osro_usd * cantidad_barcazas,
            f"BASIS {cantidad_barcazas:g} BUNKER BARGE TRIP(S)",
        ))

    # Free Pratique: solo se cobra si el barco procede del exterior (igual
    # que en Carga/Descarga y Otamerica)
    if trn and datos.get("procede_exterior"):
        coef_a = get_param(db, "libre_platica_coef", 6942.9)
        base = get_param(db, "libre_platica_base", 416574)
        resta_trn = get_param(db, "libre_platica_resta_trn", 1001)
        ars = ((trn - resta_trn) / 1000) * coef_a + base
        lineas.append(_linea("FREE PRATIQUE", ars / dolar, f"BASIS TRN {trn:g}"))

    migrations_usd = get_param(db, "bunker_migrations_usd", 1875.0)
    if datos.get("procede_exterior"):
        lineas.append(_linea("MIGRATIONS IN", migrations_usd, "BASIS ENTRANCE CLEARANCE"))
    if datos.get("destino_exterior"):
        lineas.append(_linea("MIGRATIONS OUT", migrations_usd, "BASIS DEPARTURE CLEARANCE"))

    taxis_usd = get_param(db, "bunker_taxis_usd", 200.0)
    lineas.append(_linea("TAXIS FOR MIGRATION OFFICER/AUTHS", taxis_usd, ""))

    if boya_cfg and boya_cfg.cobra_sipa and turnos_sipa:
        sipa_usd = get_param(db, "bunker_sipa_usd_turno", 42.0)
        lineas.append(_linea(
            "COASTGUARD FIREMEN PERSONNEL ON BOARD BUNKER BARGE", sipa_usd * turnos_sipa,
            f"ABT BASIS {turnos_sipa:g} SHIFT(S) OF 4 HOURS ON BOARD",
        ))

    if boya_cfg and usa_boat:
        monto_boat = boya_cfg.boat_trip_usd + (boya_cfg.boat_hora_usd * horas_boat)
        lineas.append(_linea(
            "BOAT/S FOR BQS SURVEYOR", monto_boat,
            f"IF USED -- PER TRIP -- BOAT STAY ALONGSIDE USD {boya_cfg.boat_hora_usd:g} PER HOUR",
        ))

    return lineas


def clasificar_buque_otamerica(desplazamiento: float) -> tuple[str, int, int]:
    """Clasifica el buque por desplazamiento (tns) y devuelve (tipo, tugs_in, tugs_out),
    segun la guia de Otamerica: Panamax hasta 89.290, Aframax 89.291-139.391,
    Suezmax >139.391 -- Panamax entra con 3 tugs in/2 out, Aframax/Suezmax con 4 in/2 out."""
    if desplazamiento <= 89290:
        return "PANAMAX", 3, 2
    if desplazamiento <= 139391:
        return "AFRAMAX", 4, 2
    return "SUEZMAX", 4, 2


def tarifa_ota_remolcador_por_loa(db: Session, eslora: float) -> float:
    return _tramo(models.ProformaOtaRemolcadorTarifa, db, "hasta_loa", "valor_usd", eslora, 0.0)


def calcular_otamerica(db: Session, datos: dict) -> list[dict]:
    """Proforma de Otamerica (Sitio 1 / Sitio 2, carga de crudo). Reutiliza
    casi todas las formulas de Carga/Descarga (pilotaje monoboya -- misma
    ruta que Boya 17, channel toll, free pratique, watchmen, conceptos
    fijos), salvo Head Tally Clerk que no aplica. Wharfage y Remolcadores
    usan la tarifa propia de la terminal en vez de la generica ESEM."""
    dolar = float(datos.get("dolar_venta") or 0) or 1.0
    trn = float(datos.get("trn") or 0)
    cantidad = float(datos.get("cantidad") or 0)
    dias_muelle = float(datos.get("dias_muelle") or 0)
    eslora = float(datos.get("eslora") or 0)
    manga = float(datos.get("manga") or 0)
    puntal = float(datos.get("puntal") or 0)
    desplazamiento = float(datos.get("desplazamiento") or 0)
    calado_entrada = float(datos.get("calado_entrada") or 0)
    calado_salida = float(datos.get("calado_salida") or 0)
    dia_tipo = datos.get("dia_tipo") or "SEMANA"
    uf = (eslora * manga * puntal / 800) if (eslora and manga and puntal) else 0.0

    lineas = []

    # Pilotaje -- misma ruta Monoboyas que Boya 17 (Otamerica 1/2 tambien
    # son monoboyas), por movimiento (entrada/salida por separado). Si la
    # manga supera 39.9m (40m), va tarifario de DOS PRACTICOS: se duplica
    # la tarifa de gobierno (Maniobra+Navegacion), el service fijo no cambia.
    dos_practicos = manga > 39.9
    remark_pilotage = "BASIS OUR TARIFF WITH SERVICE PROVIDER" + (
        " (TWO PILOTS -- BEAM OVER 40M)" if dos_practicos else ""
    )
    if calado_entrada:
        v = calcular_pilotage(db, uf, calado_entrada, km_clave="pilotage_monoboya_km",
                               service_clave="pilotage_monoboya_service_usd", dos_practicos=dos_practicos)
        if v:
            lineas.append(_linea("PILOTAGE IN", v, remark_pilotage))
    if calado_salida:
        v = calcular_pilotage(db, uf, calado_salida, km_clave="pilotage_monoboya_km",
                               service_clave="pilotage_monoboya_service_usd", dos_practicos=dos_practicos)
        if v:
            lineas.append(_linea("PILOTAGE OUT", v, remark_pilotage))

    # Wharfage -- tarifa propia de Otamerica (0.07 x TRN x dia, no la generica 0.46)
    wharfage_rate = get_param(db, "otamerica_wharfage_usd_trn_dia", 0.07)
    if dias_muelle and trn:
        lineas.append(_linea(
            "WHARFAGE (Uso de muelle)", math.ceil(wharfage_rate * trn * dias_muelle),
            f"BASIS {dias_muelle:g} COMPLETE DAY(S) OF PORT STAY",
        ))

    # Channel Toll -- 2.05 x cantidad cargada x coeficiente (por TRN, no por
    # cantidad como en Carga/Descarga) x factor de recorrido propio de Otamerica
    if cantidad and trn:
        channel_toll_rate = get_param(db, "channel_toll_usd_tn", 2.05)
        coef = coeficiente_channel_toll(db, trn)
        factor_recorrido = get_param(db, "otamerica_channel_toll_factor", 0.9)
        lineas.append(_linea(
            "CHANNEL TOLL (Vias navegables)", math.ceil(channel_toll_rate * cantidad * coef * factor_recorrido),
            f"BASIS {cantidad:g} MT OF CARGO",
        ))

    # ISPS -- propio de Otamerica
    if cantidad:
        isps_rate = get_param(db, "otamerica_isps_usd_tn", 0.01)
        lineas.append(_linea("ISPS", cantidad * isps_rate, f"BASIS {cantidad:g} MT OF CARGO"))

    # Boat/s for Surveyor -- siempre 2 viajes (embarque/desembarque en el
    # nuevo muelle), a cargo nuestro (suma al total, no es informativo)
    boat_surveyor_usd = get_param(db, "otamerica_boat_surveyor_usd", 1300.0)
    if boat_surveyor_usd:
        lineas.append(_linea(
            "BOATS FOR SURVEYOR", boat_surveyor_usd * 2,
            "BASIS 2 TRIPS TO NEW BERTH -- BOAT FOR EMBARK/DISEMBARK SURVEYOR SHOULD BE ORDERED BY AGENT AS "
            "TERMINAL NOT AUTH. SURVEYORS TO BOARD WITH TERMINAL BOATS AND/OR THROUGH SHORE ACCESS.",
        ))

    # Free Pratique: solo si el barco procede del exterior
    if trn and datos.get("procede_exterior"):
        coef_a = get_param(db, "libre_platica_coef", 6942.9)
        base = get_param(db, "libre_platica_base", 416574)
        resta_trn = get_param(db, "libre_platica_resta_trn", 1001)
        ars = ((trn - resta_trn) / 1000) * coef_a + base
        lineas.append(_linea("FREE PRATIQUE EXPENSES", ars / dolar, f"BASIS TRN {trn:g}"))

    # Watchmen: en base a dias completos de estadia (igual que Carga/Descarga)
    if dias_muelle:
        categoria_watchmen = datos.get("categoria_watchmen") or "NORMAL"
        sereno_dia = tarifa_turno(db, "SERENO", categoria_watchmen, dia_tipo)
        if sereno_dia:
            lineas.append(_linea(
                "WATCHMEN", (sereno_dia * dias_muelle) / dolar,
                f"BASIS {dias_muelle:g} COMPLETE DAY(S) OF PORT STAY",
            ))

    # Migrations -- en Otamerica siempre va la tarifa "en boya" (USD 1875
    # cada una), no la de muelle normal (1250) que usa Carga/Descarga
    migrations_usd = get_param(db, "otamerica_migrations_usd", 1875.0)
    if datos.get("procede_exterior"):
        lineas.append(_linea("MIGRATIONS IN", migrations_usd, "BASIS ENTRANCE CLEARANCE"))
    if datos.get("destino_exterior"):
        lineas.append(_linea("MIGRATIONS OUT", migrations_usd, "BASIS DEPARTURE CLEARANCE"))

    # Conceptos fijos (customs, etc.) -- mismos que Carga/Descarga, salvo:
    # immigration_in/out (reemplazados arriba por Migrations en boya),
    # LINE HANDLERS IN/OUT (no van, ya estan cubiertos por Mooring/Unmooring),
    # TRANSPORT (tarifa propia de Otamerica, USD 300 en vez de la generica)
    transport_usd = get_param(db, "otamerica_transport_usd", 300.0)
    conceptos_fijos = db.scalars(
        select(models.ProformaConceptoFijo).where(models.ProformaConceptoFijo.activo == True)
        .order_by(models.ProformaConceptoFijo.orden)
    ).all()
    for c in conceptos_fijos:
        if c.clave in ("immigration_in", "immigration_out"):
            continue
        if c.nombre in ("LINE HANDLERS IN", "LINE HANDLERS OUT"):
            continue
        if c.nombre == "TRANSPORT":
            lineas.append(_linea(c.nombre, transport_usd, c.condicion or ""))
            continue
        lineas.append(_linea(c.nombre, c.valor_usd, c.condicion or ""))

    # --- Informativos al final (en gris, no suman al total): remolcadores,
    # amarre/desamarre y barreras de contencion -- referencia de costo, los
    # paga el cliente directo al proveedor/terminal ------------------------

    # Remolcadores -- tarifa propia de Otamerica por LOA, cantidad segun
    # clasificacion del buque (Panamax 3in/2out, Aframax/Suezmax 4in/2out).
    if eslora and desplazamiento:
        tipo_buque, tugs_in, tugs_out = clasificar_buque_otamerica(desplazamiento)
        valor_tug = tarifa_ota_remolcador_por_loa(db, eslora)
        if valor_tug:
            lineas.append(_linea(
                "TUGS IN", valor_tug * tugs_in,
                f"BASIS {tugs_in} TUG(S) ({tipo_buque}) -- OUR TARIFF WITH SERVICE PROVIDER", informativo=True,
            ))
            lineas.append(_linea(
                "TUGS OUT", valor_tug * tugs_out,
                f"BASIS {tugs_out} TUG(S) ({tipo_buque}) -- OUR TARIFF WITH SERVICE PROVIDER", informativo=True,
            ))

    # Amarre / Desamarre -- siempre tarifa de dia habil; el recargo de
    # fin de semana/feriado se deja solo como referencia en la observacion
    amarre_usd = get_param(db, "otamerica_amarre_usd", 7162.0)
    if amarre_usd:
        recargo = (
            f"RATE INCREASES BY 50% (USD {amarre_usd * 1.5:,.0f}) IF PERFORMED OUTSIDE 07:00-19:00 ON WEEKDAYS "
            f"OR ON SATURDAYS 07:00-13:00; BY 100% (USD {amarre_usd * 2:,.0f}) ON SATURDAYS 13:00-24:00, "
            "SUNDAYS OR HOLIDAYS."
        )
        lineas.append(_linea("MOORING (Amarre)", amarre_usd, recargo, informativo=True))
        lineas.append(_linea("UNMOORING (Desamarre)", amarre_usd, recargo, informativo=True))

    # Barreras de contencion marina -- siempre se cobra, por dia completo
    if dias_muelle:
        barreras_rate = get_param(db, "otamerica_barreras_usd_dia", 2046.0)
        lineas.append(_linea(
            "MARINE CONTAINMENT BOOMS DEPLOYMENT", barreras_rate * dias_muelle,
            f"BASIS {dias_muelle:g} COMPLETE DAY(S)", informativo=True,
        ))

    return lineas
