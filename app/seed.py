from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import Base, SessionLocal, engine
from .models import (
    AppSetting,
    Client,
    EventTemplate,
    Lineup,
    ProformaBunkerBoya,
    ProformaCoefTramo,
    ProformaConceptoFijo,
    ProformaOtaRemolcadorTarifa,
    ProformaParametro,
    ProformaPilotageTramo,
    ProformaTarifaTurno,
    ProformaTugTarifa,
    Terminal,
    User,
)

DEFAULT_SIGNATURE_HTML = """<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#333333;">
  <div style="font-weight:bold;">Saludos / Regards</div>
  <br>
  <div style="font-size:16px;font-weight:bold;color:#1F4E79;">Leandro Frattini</div>
  <div style="color:#1F4E79;">Operations Department</div>
  <br>
  <div>Facundo Zurivia 401</div>
  <div>Bahia Blanca (B8000), Bs As, Argentina</div>
  <div>+54 9 291 4421772</div>
  <br>
  <div><a href="mailto:lfrattini@seawhite.com.ar" style="color:#1F4E79;">lfrattini@seawhite.com.ar</a></div>
  <div><a href="https://www.seawhite.com.ar" style="color:#1F4E79;font-weight:bold;">www.seawhite.com.ar</a></div>
</div>"""

DEFAULT_TERMINALS = [
    # (code, name, berth_label, sort_order)
    ("ADM", "ADM Agro", "ADM berth", 10),
    ("9TBB", "TBBCA 9", "Pier 9 TBB berth", 20),
    ("CARGILL", "Cargill", "Cargill berth", 30),
    ("LDC", "LDC", "LDC berth", 40),
    ("2/3 GALVAN", "2/3 Galvan", "2/3 Galvan berth", 50),
]

DEFAULT_FLAMMABLE_TERMINALS = [
    ("FLAMMABLE PIER N 1", "Flammable Berth 1", "Flammable Pier N 1", 10),
    ("FLAMMABLE PIER N 2", "Flammable Berth 2", "Flammable Pier N 2", 20),
    ("FLAMMABLE PIER N 3", "Flammable Berth 3", "Flammable Pier N 3", 30),
    ("MEGA TERMINAL", "Mega", "Mega Terminal", 40),
    ("PROFERTIL", "Profertil", "Profertil", 50),
]

# Muelles propios -- van al pie del line-up Grain (sort_order alto) y NUNCA
# al Excel (interno ni de clientes) ni al line-up finalizado del dia; solo
# sirven para poder armar el legajo en Barcos (ID) y mandar los reportes de
# ese barco a nuestros clientes.
DEFAULT_EXTRA_TERMINALS = [
    ("OTAMERICA SITIO 1", "Otamerica Sitio 1", "Otamerica Sitio 1 berth", 900),
    ("OTAMERICA SITIO 2", "Otamerica Sitio 2", "Otamerica Sitio 2 berth", 910),
]

# ALTER TABLE ... ADD COLUMN para bases creadas antes de agregar estas columnas
_MIGRATIONS = [
    ("terminals", "kind", "TEXT DEFAULT 'GRAIN'"),
    ("terminals", "status_note", "TEXT DEFAULT ''"),
    ("lineups", "kind", "TEXT DEFAULT 'GRAIN'"),
    ("vessel_calls", "second_call", "BOOLEAN DEFAULT FALSE"),
    ("operated_vessels", "period", "TEXT DEFAULT ''"),
    ("users", "must_change_password", "BOOLEAN DEFAULT FALSE"),
    ("clients", "client_type", "TEXT DEFAULT 'AGENCY'"),
    ("vessel_reports", "shift_data", "TEXT DEFAULT ''"),
    ("vessel_files", "statement_of_facts", "TEXT DEFAULT ''"),
    ("vessel_reports", "batch_id", "TEXT DEFAULT ''"),
    ("terminals", "exclude_from_excel", "BOOLEAN DEFAULT FALSE"),
    ("vessel_calls", "needs_report", "BOOLEAN DEFAULT TRUE"),
    ("lineups", "notice", "TEXT DEFAULT ''"),
    ("users", "is_pda_admin", "BOOLEAN DEFAULT FALSE"),
    ("proformas", "remolques_in", "INTEGER DEFAULT 0"),
    ("proformas", "remolques_out", "INTEGER DEFAULT 0"),
    ("proformas", "immigration_in_boya", "BOOLEAN DEFAULT FALSE"),
    ("proformas", "immigration_out_boya", "BOOLEAN DEFAULT FALSE"),
    ("proformas", "calado", "FLOAT DEFAULT 0"),
    ("proformas", "calado_entrada", "FLOAT DEFAULT 0"),
    ("proformas", "calado_salida", "FLOAT DEFAULT 0"),
]


def _migrate(db: Session) -> None:
    dialect = db.bind.dialect.name
    for table, column, decl in _MIGRATIONS:
        if dialect == "sqlite":
            cols = {r[1] for r in db.execute(text(f"PRAGMA table_info({table})"))}
        else:
            cols = {
                r[0]
                for r in db.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                    {"t": table},
                )
            }
        if column not in cols:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))
    if dialect == "sqlite":
        # backfill period de barcos operados viejos, desde operated_at
        # (strftime es de SQLite -- en Postgres la base arranca vacia, no hace falta)
        db.execute(
            text(
                "UPDATE operated_vessels SET period = strftime('%Y-%m', operated_at) "
                "WHERE period IS NULL OR period = ''"
            )
        )
    db.commit()

# Clientes de arranque tomados de la columna PRINCIPAL del Excel.
# Cargar los mails desde la pantalla "Clientes".
DEFAULT_CLIENTS = [
    ("WBL", "WBL", "WBL_TEXT"),
    ("AMI", "", "EXCEL"),
    ("Blue Star", "", "EXCEL"),
    ("Oceanway", "", "EXCEL"),
    ("Nabsa", "", "EXCEL"),
    ("Alpemar", "", "EXCEL"),
    ("Fertimport", "", "EXCEL"),
    ("ISA", "", "EXCEL"),
]

# --- Proformador: formulas confirmadas contra PDAs reales de Blue Star ---
PROFORMA_PARAMETROS = [
    ("wharfage_usd_trn_dia", "Uso de muelle (USD x TRN x dia)", 0.46),
    ("channel_toll_usd_tn", "Vias navegables (USD x tonelada x coef)", 2.05),
    ("fondeadero_usd_trn_dia", "Uso de fondeadero (USD x TRN x dia) -- usado en Bunker", 0.15),
    ("libre_platica_coef", "Free Pratique -- coeficiente (x TRN/1000)", 6942.9),
    ("libre_platica_base", "Free Pratique -- base fija ARS", 416574.0),
    ("libre_platica_resta_trn", "Free Pratique -- TRN de referencia a restar", 1001.0),
    ("immigration_boya_usd", "Immigration en boya (IN y/o OUT) -- USD fijo", 1875.0),
    ("pilotage_coef_maniobra", "Pilotaje -- coeficiente Maniobra/Practicaje (x UF)", 14.0),
    ("pilotage_coef_navegacion", "Pilotaje -- coeficiente Navegacion/Pilotaje (x UF)", 8.0),
    ("pilotage_coef_km", "Pilotaje -- coeficiente x km de recorrido", 12.0),
    ("pilotage_km_recorrido", "Pilotaje -- km del recorrido (I.White-Profertil)", 53.0),
    ("pilotage_descuento", "Pilotaje -- descuento decreto 716/26 (0-1)", 0.2),
    ("pilotage_service_usd", "Pilotaje -- service/related fijo por movimiento (USD)", 6600.0),
    ("pilotage_monoboya_km", "Pilotaje Monoboyas (Boya 17) -- km del recorrido", 25.0),
    ("pilotage_monoboya_service_usd", "Pilotaje Monoboyas (Boya 17) -- service/related fijo", 8140.0),
    ("bunker_channel_toll_usd_tn", "Bunker -- Channel Toll (USD x 20%TRN x coef x 0.7)", 2.05),
    ("bunker_anchor_dues_usd_trn", "Bunker -- Anchor Dues (USD x TRN x dia)", 0.15),
    ("bunker_customs_shift_usd", "Bunker -- Customs, USD por turno de 6hs", 300.0),
    ("bunker_taxis_usd", "Bunker -- Taxis para oficial de migraciones/autoridades (USD fijo)", 200.0),
    ("bunker_migrations_usd", "Bunker -- Migrations IN/OUT, cada uno (USD fijo)", 1875.0),
    ("bunker_sipa_usd_turno", "Bunker -- SIPA/Prefectura Boya 3, USD por turno de 4hs (ABT)", 42.0),
    ("otamerica_wharfage_usd_trn_dia", "Otamerica -- Uso de muelle (USD x TRN x dia)", 0.07),
    ("otamerica_isps_usd_tn", "Otamerica -- ISPS (USD x tonelada cargada)", 0.01),
    ("otamerica_barreras_usd_dia", "Otamerica -- Barreras de contencion marina (USD x dia o fraccion)", 2046.0),
    ("otamerica_amarre_usd", "Otamerica -- Amarre y Desamarre, cada uno, dia habil (USD fijo)", 7162.0),
    ("otamerica_migrations_usd", "Otamerica -- Migrations IN/OUT, tarifa en boya, cada una (USD fijo)", 1875.0),
    ("otamerica_channel_toll_factor", "Otamerica -- Channel Toll, factor de recorrido", 0.9),
]

# Configuracion propia de cada boya de bunker (Formulas la deja editar)
PROFORMA_BUNKER_BOYAS = [
    ("BOYA_3", "Boya 3", 4900.0, 4900.0, 400.0, False, False, True),
    ("BOYA_11", "Boya 11", 2880.0, 3300.0, 350.0, True, False, False),
    ("BOYA_17", "Boya 17", 2880.0, 1700.0, 350.0, True, True, False),
]

PROFORMA_COEF_TRAMOS = [
    (5000, 0.60),
    (10000, 0.85),
    (17000, 1.0),
    (None, 1.15),
]

PROFORMA_TUG_TARIFAS = [
    (150, 7500.0),
    (180, 9800.0),
    (200, 12270.0),
    (None, 14750.0),
]

# Arancel de Remolcadores propio de Otamerica, por tramo de LOA (m) -- USD
# por remolcador y por maniobra (tarifario Otamerica 2026)
PROFORMA_OTA_REMOLCADOR_TARIFAS = [
    (240, 17495.0),
    (250, 19234.0),
    (260, 21280.0),
    (270, 23429.0),
    (None, 25475.0),
]

# Pilotaje/practicaje por tramo de calado (pies) -- tarifario ESEM, recorrido
# "Extranjero, By11o17-I.WHITE h/Profertil, 1 practico" (el mas comun).
# Esto NO es un monto fijo: es el "%calado" que multiplica a la formula de
# Maniobra/Navegacion, que a su vez depende de la Unidad Fiscal (UF) propia
# de CADA barco (UF = Eslora x Manga x Puntal / 800 -- el mismo calculo que
# el "FC"). Otros recorridos/banderas/2 practicos no estan cargados.
PROFORMA_PILOTAGE_TRAMOS = [
    (28, 1.0),    # <28 pies / lastre
    (30, 1.075),  # >28<30 pies
    (32, 1.15),   # >30<32 pies
    (34, 1.225),  # >32<34 pies
    (None, 1.3),  # >34 pies
]

PROFORMA_CONCEPTOS_FIJOS = [
    ("immigration_in", "IMMIGRATION IN", 1250.0, "Si el barco procede del exterior"),
    ("immigration_out", "IMMIGRATION OUT", 1250.0, "Si el barco se dirige al exterior"),
    (None, "LINE HANDLERS IN", 4050.0, "Basis normal hours and tariff with service provider"),
    (None, "LINE HANDLERS OUT", 1900.0, "Basis normal hours and tariff with service provider"),
    (None, "TRANSPORT", 100.0, "Port authorities in/out"),
    (None, "CUSTOMS", 300.0, "Give entrance if berthed in overtime"),
    (None, "MARITIME CENTRE", 80.0, ""),
    (None, "SENASA GARBAGE INSPECTION", 150.0, ""),
    (None, "CUSTOMS FOR LOADING/DISCH IN O/T", 300.0, "Cada shift en O/T (a pedido del agente, obligatorio)"),
    (None, "CUSTOM FOR PERMANENCE", 300.0, "Cada shift de 6hs alongside sin O/T ordenado"),
]

# TALLY (Encargado): valor ARS por dia, por tipo de carga
PROFORMA_TARIFAS_TALLY = {
    "ACEITE": (3959402.33, 4807845.69, 5656289.05),
    "CEREAL": (4638157.02, 5486600.38, 6335043.75),
    "BOLSONES": (5090660.18, 5939103.54, 6787546.91),
    "FERTILIZANTE": (5769414.87, 6617858.24, 7466301.60),
}

# WATCHMEN (Sereno): valor ARS por dia, por categoria propia (no coincide
# 1 a 1 con las de Tally -- INSALUBRE agrupa cereal/fertilizante, PELIGROSO
# es por operar en posta, no por tipo de carga)
PROFORMA_TARIFAS_SERENO = {
    "NORMAL": (2678628.27, 2935005.12, 4216304.87),
    "INSALUBRE": (3960429.67, 4345007.74, 6267746.40),
    "PELIGROSO": (4730186.77, 5191782.46, 7499153.70),
}

PROFORMA_DIAS_TIPO = ["SEMANA", "SABADO", "DOMINGO_FERIADO"]

# Punto de partida de la biblioteca de eventos (Admin -> Eventos la sigue
# completando). Los {PLACEHOLDER} entre llaves se dejan para editar a mano
# al insertar (terminal, surveyor, barcaza, cantidad de bodegas, etc).
# Sacados de los .eml reales que paso Leandro (MV ANAHITA, MV PHAEDRA, MV
# BAI GUAN, MV FLORA) + la biblioteca de referencia que mostro (DELAYS PORT /
# OPERATION PORT / BUNKERS PORT), deduplicados y reagrupados.
DEFAULT_EVENT_TEMPLATES = [
    ("ARRIVED", "Anchor aweigh and proceeded to Buoy 11 P/S as per Coast Guard instructions."),
    ("ARRIVED", "Arrived and anchored at Bahia Blanca roads."),
    ("ARRIVED", "Arrived and anchored at outer anchorage."),
    ("ARRIVED", "Arrived at Buoy 11 P/S, pilot boarded and continued navigation towards berth."),
    ("ARRIVED", "Arrived at inner roads and two tugs made fast."),
    ("ARRIVED", "End of sea passage (EOSP). Load berth occupied by another vessel."),
    ("ARRIVED", "End of sea passage. Load berth was free."),
    ("ARRIVED", "First line ashore."),
    ("ARRIVED", "Gangway placed / Pilot off / Agent and authorities on board."),
    ("ARRIVED", "Inward clearance granted by Port Authorities."),
    ("ARRIVED", "Made all fast alongside {TERMINAL} terminal."),
    ("ARRIVED", "Made all fast at {TERMINAL} Terminal."),
    ("ARRIVED", "Notice of readiness tendered by Master."),
    ("ARRIVED", "Notice of readiness re-tendered by Master."),
    ("ARRIVED", "Occupying vessel sailed to buoy, load berth became free."),
    ("ARRIVED", "Pilots boarded and passed Buoy 11."),
    ("ARRIVED", "Shore gangway placed. Pilot off. Port Authorities on board."),
    ("ARRIVED", "Tugs cast off / released."),
    ("ARRIVED", "Vessel remained anchored awaiting berth availability."),
    ("ARRIVED", "Vessel remained anchored awaiting berthing instructions."),
    ("BUNKERING", "Bunker barge {BARGE} away."),
    ("BUNKERING", "Desloping barge away."),
    ("BUNKERING", "Fresh water barge away."),
    ("DELAYS", "Awaiting Customs and terminal surveyors in order to perform final Draft Survey."),
    ("DELAYS", "Awaiting Customs' authorization to start loading."),
    ("DELAYS", "Awaiting Master to sign cargo documents."),
    ("DELAYS", "Awaiting Master to sign mate's receipt."),
    ("DELAYS", "Awaiting Shippers to present cargo documents."),
    ("DELAYS", "Delay due to adverse weather conditions."),
    ("DELAYS", "Delay due to draft check."),
    ("DELAYS", "Delay due to strong winds."),
    ("DELAYS", "Stevedores not appointed by Shippers."),
    ("OPERATION", "Awaiting SeNaSA's green light to commence loading operations."),
    ("OPERATION", "Awaiting shore readiness."),
    ("OPERATION", "Cargo holds inspected and approved by {SURVEYOR} surveyors."),
    ("OPERATION", "Commenced discharging operations."),
    ("OPERATION", "Commenced loading operations by {N} gangs into holds {HOLDS}."),
    ("OPERATION", "Completed loading operations."),
    ("OPERATION", "Discharging completed."),
    ("OPERATION", "Final draft survey carried out by {SURVEYOR} surveyors."),
    ("OPERATION", "Fumigation of cargo holds carried out by {COMPANY}."),
    ("OPERATION", "Holds sealing carried out by {COMPANY}."),
    ("OPERATION", "Initial draft survey carried out by {SURVEYOR} surveyors."),
    ("OPERATION", "Preparing works ashore."),
    ("OPERATION", "Senasa gave OK to load."),
    ("OPERATION", "Vessel remains alongside at orders."),
    ("SAILING", "Outward clearance granted by Port Authorities."),
    ("SAILING", "Pilot on board and tugs made fast for sailing."),
    ("SAILING", "Sailed to Buoy {N}."),
    ("SAILING", "Sailed to destination (as per VTS times)."),
    ("SAILING", "Vessel alongside awaiting favourable tide for sailing."),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    db: Session = SessionLocal()
    try:
        _migrate(db)
        _seed_admin(db)
        _seed_terminals(db)
        _seed_flammable_terminals(db)
        _seed_extra_terminals(db)
        _seed_clients(db)
        _seed_lineup(db)
        _seed_signature(db)
        _seed_event_templates(db)
        _seed_proformador(db)
        db.commit()
    finally:
        db.close()


def _seed_admin(db: Session) -> None:
    if db.scalar(select(User).limit(1)):
        return
    db.add(
        User(
            username=settings.bootstrap_admin_user,
            password_hash=hash_password(settings.bootstrap_admin_password),
            full_name="Administrador",
            is_admin=True,
            is_active=True,
        )
    )


def _seed_terminals(db: Session) -> None:
    if db.scalar(select(Terminal).where(Terminal.kind == "GRAIN").limit(1)):
        return
    for code, name, berth, order in DEFAULT_TERMINALS:
        db.add(Terminal(kind="GRAIN", code=code, name=name, berth_label=berth,
                        sort_order=order, active=True))


def _seed_flammable_terminals(db: Session) -> None:
    if db.scalar(select(Terminal).where(Terminal.kind == "FLAMMABLE").limit(1)):
        return
    for code, name, berth, order in DEFAULT_FLAMMABLE_TERMINALS:
        db.add(Terminal(kind="FLAMMABLE", code=code, name=name, berth_label=berth,
                        sort_order=order, active=True))


def _seed_extra_terminals(db: Session) -> None:
    """Aditivo (corre siempre, no solo si la tabla esta vacia) -- asi si se
    suma un muelle propio nuevo a DEFAULT_EXTRA_TERMINALS llega solo a las
    bases que ya tenian datos, igual que _seed_event_templates."""
    existing = {c for (c,) in db.execute(select(Terminal.code).where(Terminal.kind == "GRAIN"))}
    for code, name, berth, order in DEFAULT_EXTRA_TERMINALS:
        if code not in existing:
            db.add(Terminal(kind="GRAIN", code=code, name=name, berth_label=berth,
                            sort_order=order, active=True, exclude_from_excel=True))


def _seed_clients(db: Session) -> None:
    if db.scalar(select(Client).limit(1)):
        return
    for name, to_name, fmt in DEFAULT_CLIENTS:
        db.add(Client(name=name, to_name=to_name, emails="", report_format=fmt, active=True))


def _seed_proformador(db: Session) -> None:
    # Aditivo por clave (no solo "si la tabla esta vacia"): asi un parametro
    # nuevo que se suma a PROFORMA_PARAMETROS despues llega solo a las bases
    # que ya tenian otros cargados, en vez de quedar faltante en silencio.
    existentes = {p.clave for p in db.scalars(select(ProformaParametro))}
    max_orden = db.scalar(select(func.max(ProformaParametro.orden))) or -1
    for clave, etiqueta, valor in PROFORMA_PARAMETROS:
        if clave not in existentes:
            max_orden += 1
            db.add(ProformaParametro(clave=clave, etiqueta=etiqueta, valor=valor, orden=max_orden))

    if not db.scalar(select(ProformaCoefTramo).limit(1)):
        for i, (hasta, coef) in enumerate(PROFORMA_COEF_TRAMOS):
            db.add(ProformaCoefTramo(hasta_toneladas=hasta, coeficiente=coef, orden=i))

    if not db.scalar(select(ProformaTugTarifa).limit(1)):
        for i, (hasta, valor) in enumerate(PROFORMA_TUG_TARIFAS):
            db.add(ProformaTugTarifa(hasta_loa=hasta, valor_usd=valor, orden=i))

    if not db.scalar(select(ProformaPilotageTramo).limit(1)):
        for i, (hasta, valor) in enumerate(PROFORMA_PILOTAGE_TRAMOS):
            db.add(ProformaPilotageTramo(hasta_pies=hasta, valor_usd=valor, orden=i))

    if not db.scalar(select(ProformaConceptoFijo).limit(1)):
        for i, (clave, nombre, valor, cond) in enumerate(PROFORMA_CONCEPTOS_FIJOS):
            db.add(ProformaConceptoFijo(clave=clave, nombre=nombre, valor_usd=valor, condicion=cond, orden=i))

    if not db.scalar(select(ProformaTarifaTurno).limit(1)):
        orden = 0
        for categoria, valores in PROFORMA_TARIFAS_TALLY.items():
            for dia_tipo, valor in zip(PROFORMA_DIAS_TIPO, valores):
                db.add(ProformaTarifaTurno(servicio="TALLY", categoria=categoria, dia_tipo=dia_tipo,
                                            valor_ars_dia=valor, orden=orden))
                orden += 1
        for categoria, valores in PROFORMA_TARIFAS_SERENO.items():
            for dia_tipo, valor in zip(PROFORMA_DIAS_TIPO, valores):
                db.add(ProformaTarifaTurno(servicio="SERENO", categoria=categoria, dia_tipo=dia_tipo,
                                            valor_ars_dia=valor, orden=orden))
                orden += 1

    if not db.scalar(select(ProformaBunkerBoya).limit(1)):
        for i, (boya, etiqueta, osro, boat_trip, boat_hora, ch_anchor, pilotage, sipa) in enumerate(PROFORMA_BUNKER_BOYAS):
            db.add(ProformaBunkerBoya(
                boya=boya, etiqueta=etiqueta, osro_usd=osro, boat_trip_usd=boat_trip, boat_hora_usd=boat_hora,
                cobra_channel_anchor=ch_anchor, cobra_pilotage=pilotage, cobra_sipa=sipa, orden=i,
            ))

    if not db.scalar(select(ProformaOtaRemolcadorTarifa).limit(1)):
        for i, (hasta, valor) in enumerate(PROFORMA_OTA_REMOLCADOR_TARIFAS):
            db.add(ProformaOtaRemolcadorTarifa(hasta_loa=hasta, valor_usd=valor, orden=i))


def _seed_lineup(db: Session) -> None:
    for kind, port in (("GRAIN", settings.port_name), ("FLAMMABLE", "BAHIA BLANCA FLAMMABLE STATIONS")):
        if db.scalar(select(Lineup).where(Lineup.status == "draft", Lineup.kind == kind)):
            continue
        db.add(Lineup(kind=kind, port_name=port,
                      lineup_date=date.today().strftime("%d/%m/%y"), status="draft"))


def _seed_signature(db: Session) -> None:
    if not db.get(AppSetting, "report_signature_html"):
        db.add(AppSetting(key="report_signature_html", value=DEFAULT_SIGNATURE_HTML))
    if not db.get(AppSetting, "report_cc"):
        db.add(AppSetting(key="report_cc", value="operations@seawhite.com.ar"))
    if not db.get(AppSetting, "flammable_list_emails"):
        db.add(AppSetting(key="flammable_list_emails", value=""))


def _seed_event_templates(db: Session) -> None:
    """Agrega los wordings de DEFAULT_EVENT_TEMPLATES que todavia no esten
    cargados (por texto exacto) -- no solo la primera vez, asi una base que
    ya tenia algunos wordings recibe los nuevos que se van sumando a la
    lista sin duplicar los que el usuario ya edito o agrego el mismo."""
    # "BUNKERS" (nombre viejo) -> "BUNKERING", para las bases que ya lo
    # tenian sembrado con el nombre anterior
    db.query(EventTemplate).filter(EventTemplate.category == "BUNKERS").update(
        {EventTemplate.category: "BUNKERING"}
    )
    # la categoria vieja "STATUS" quedo duplicada/superada por ARRIVED y
    # OPERATION (frases mas completas) -- se borra, salvo la version corta
    # de "Commenced Loading." que se conserva reubicada en OPERATION
    for e in db.scalars(select(EventTemplate).where(EventTemplate.category == "STATUS")):
        if e.text.strip() == "Commenced Loading.":
            e.category = "OPERATION"
        else:
            db.delete(e)
    db.flush()
    existing = {(e.category, e.text) for e in db.scalars(select(EventTemplate))}
    max_order = db.scalar(select(func.max(EventTemplate.sort_order))) or 0
    for i, (category, text_) in enumerate(DEFAULT_EVENT_TEMPLATES):
        if (category, text_) in existing:
            continue
        max_order += 1
        db.add(EventTemplate(category=category, text=text_, sort_order=max_order, active=True))
