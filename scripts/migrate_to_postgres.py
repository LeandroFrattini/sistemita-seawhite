"""Copia todos los datos de la base SQLite local a la base Postgres de Render.

Se corre UNA vez, despues de crear el web service + la base en Render
(render.yaml), para no arrancar con la base vacia / con los datos de
ejemplo que la app siembra sola la primera vez que prende.

Es seguro correrlo mas de una vez: antes de copiar, borra el contenido
de las tablas de destino (no borra ni toca la base SQLite de origen).

Uso (desde la carpeta del proyecto, con el venv activado):
    python scripts/migrate_to_postgres.py "postgresql://user:pass@host/db"

La URL "postgresql://...." es la "External Database URL" que Render
muestra en la pantalla de la base de datos (pestaña Connect / Info).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.config import settings
from app.database import Base

# orden de dependencia: primero las tablas sin FK, despues las que
# dependen de ellas. El borrado (antes de copiar) se hace al reves.
TABLES_IN_ORDER = [
    m.User,
    m.Terminal,
    m.Client,
    m.Lineup,
    m.VesselCall,
    m.VesselExtraAgency,
    m.ArchivedLineup,
    m.OperatedVessel,
    m.VesselFile,
    m.VesselFileAgency,
    m.VesselReport,
    m.AppSetting,
    m.ReportLog,
]


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def main(target_url: str) -> None:
    target_url = _normalize(target_url)
    if not target_url.startswith("postgresql"):
        print("Esa URL no parece de Postgres. Pasa la 'External Database URL' de Render.")
        sys.exit(1)

    src_engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(target_url)

    Session = sessionmaker(future=True)
    src = Session(bind=src_engine)
    dst = Session(bind=dst_engine)

    try:
        # crea las tablas si todavia no existen (deploy nuevo)
        Base.metadata.create_all(dst_engine)

        print("Borrando datos existentes en destino...")
        for model in reversed(TABLES_IN_ORDER):
            dst.execute(model.__table__.delete())
        dst.commit()

        for model in TABLES_IN_ORDER:
            table = model.__table__
            cols = [c.name for c in table.columns]
            rows = src.execute(select(model)).scalars().all()
            for row in rows:
                dst.execute(table.insert().values(**{c: getattr(row, c) for c in cols}))
            dst.commit()
            print(f"  {table.name}: {len(rows)} fila(s) copiada(s)")

            id_col = table.columns.get("id")
            if id_col is not None:
                seq = f"{table.name}_id_seq"
                dst.execute(
                    text(
                        f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table.name}), 1), "
                        f"(SELECT MAX(id) FROM {table.name}) IS NOT NULL)"
                    )
                )
        dst.commit()
        print("Listo -- la base de Render ya tiene los mismos datos que tu base local.")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Uso: python scripts/migrate_to_postgres.py "postgresql://user:pass@host/db"')
        sys.exit(1)
    main(sys.argv[1])
