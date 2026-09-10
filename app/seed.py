from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import Base, SessionLocal, engine
from .models import AppSetting, Client, Lineup, Terminal, User

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
    ("vessel_calls", "second_call", "BOOLEAN DEFAULT 0"),
    ("operated_vessels", "period", "TEXT DEFAULT ''"),
]


def _migrate(db: Session) -> None:
    for table, column, decl in _MIGRATIONS:
        cols = {r[1] for r in db.execute(text(f"PRAGMA table_info({table})"))}
        if column not in cols:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))
    # backfill period de barcos operados viejos, desde operated_at
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
