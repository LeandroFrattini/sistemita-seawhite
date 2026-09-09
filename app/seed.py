from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import settings
from .database import Base, SessionLocal, engine
from .models import Client, Lineup, Terminal, User

DEFAULT_TERMINALS = [
    # (code, name, berth_label, sort_order)
    ("ADM", "ADM Agro", "ADM berth", 10),
    ("9TBB", "TBBCA 9", "Pier 9 TBB berth", 20),
    ("CARGILL", "Cargill", "Cargill berth", 30),
    ("LDC", "LDC", "LDC berth", 40),
    ("2/3 GALVAN", "2/3 Galvan", "2/3 Galvan berth", 50),
]

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
        _seed_admin(db)
        _seed_terminals(db)
        _seed_clients(db)
        _seed_lineup(db)
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
    if db.scalar(select(Terminal).limit(1)):
        return
    for code, name, berth, order in DEFAULT_TERMINALS:
        db.add(Terminal(code=code, name=name, berth_label=berth, sort_order=order, active=True))


def _seed_clients(db: Session) -> None:
    if db.scalar(select(Client).limit(1)):
        return
    for name, to_name, fmt in DEFAULT_CLIENTS:
        db.add(Client(name=name, to_name=to_name, emails="", report_format=fmt, active=True))


def _seed_lineup(db: Session) -> None:
    if db.scalar(select(Lineup).where(Lineup.status == "draft")):
        return
    db.add(
        Lineup(
            port_name=settings.port_name,
            lineup_date=date.today().strftime("%d/%m/%y"),
            status="draft",
        )
    )
