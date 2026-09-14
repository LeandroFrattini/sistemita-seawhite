from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import Base, SessionLocal, engine
from .models import AppSetting, Client, EventTemplate, Lineup, Terminal, User

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
        _seed_clients(db)
        _seed_lineup(db)
        _seed_signature(db)
        _seed_event_templates(db)
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


def _seed_clients(db: Session) -> None:
    if db.scalar(select(Client).limit(1)):
        return
    for name, to_name, fmt in DEFAULT_CLIENTS:
        db.add(Client(name=name, to_name=to_name, emails="", report_format=fmt, active=True))


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
