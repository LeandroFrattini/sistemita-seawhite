"""Carga el Statement of Facts real (pasado por Leandro) en el legajo del
M/V YAMI BENEFIT, directo contra la base de Render.

Es seguro correrlo mas de una vez: antes de insertar, se fija si ya existe
un evento con la misma fecha/hora/texto y lo salta (no duplica).

Uso (desde la carpeta del proyecto, con el venv activado):
    python scripts/load_sof_yami_benefit.py "postgresql://user:pass@host/db"

La URL "postgresql://...." es la "External Database URL" que Render
muestra en la pantalla de la base de datos (pestaña Connect / Info).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import models as m

VESSEL_NAME = "YAMI BENEFIT"

ENTRIES = [
    ("12/09/2026", "09:00", "", 'EOSP, Load berth was occupied by M/V "TEXEL ISLAND" since Sept 11th, 0218 hrs.'),
    ("12/09/2026", "10:00", "", "Notice of readiness tendered by master."),
    ("12/09/2026", "11:48", "", "Vessel arrived and anchored at outer anchorage as per coast guard instructions."),
    ("12/09/2026", "11:48", "", "Notice of readiness re-tendered by master."),
    ("12/09/2026", "11:48", "24:00", "Vessel remained anchored awaiting berth availability."),
    ("13/09/2026", "00:00", "09:06", "Vessel remained anchored awaiting berthing instructions."),
    ("13/09/2026", "04:48", "", 'M/V "TEXEL ISLAND" sailed to buoy N°17, load berth became free.'),
    ("13/09/2026", "09:06", "", "Anchor Aweigh and proceed towards buoy N°11 P/S."),
    ("13/09/2026", "12:00", "", "Arrived at Buoy N°11, pilot boarded and continue navigation towards berth."),
    ("13/09/2026", "14:38", "", "Arrived at inner roads and two tugboats made fast."),
    ("13/09/2026", "15:12", "", "First line ashore."),
    ("13/09/2026", "15:28", "", "Tugs released."),
    ("13/09/2026", "15:42", "", "Made all fast at ADM Terminal."),
    ("13/09/2026", "15:42", "", "Notice of readiness re-tendered by master."),
    ("13/09/2026", "15:48", "", "Shore gangway placed. Pilot off. Port Authorities on board."),
    ("13/09/2026", "15:48", "",
     "Berthing Conditions:\nDraft: Fwd: 10.14 Mts / Aft: 10.14 Mts\n"
     "Rob: Ifo: 627.37 Mt / Mgo: 151.60 Mt / Fw: 89.00 Mt / Lo: 43,332 lts"),
    ("13/09/2026", "16:10", "", "Inward clearance granted by port authorities."),
    ("13/09/2026", "16:10", "24:00", "Vessel remains alongside at orders."),
    ("14/09/2026", "00:00", "07:00", "Vessel remains alongside at orders."),
    ("14/09/2026", "07:00", "07:30", "Cargo hold N°2,3,4 and 5 inspected and approved by Fides control surveyors."),
    ("14/09/2026", "07:40", "", "Senasa gave ok to load."),
    ("14/09/2026", "07:45", "", "Commenced loading operations by one gang into cargo hold N°5."),
]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    engine = create_engine(sys.argv[1])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        vf = db.scalar(
            select(m.VesselFile)
            .where(m.VesselFile.vessel_name.ilike(VESSEL_NAME), m.VesselFile.status == "open")
            .order_by(m.VesselFile.id.desc())
        )
        if not vf:
            print(f'No encontre ningun legajo ABIERTO para "{VESSEL_NAME}". Nada para hacer.')
            sys.exit(1)
        print(f"Legajo encontrado: #{vf.id} {vf.vessel_name}")

        existing = {
            (e.event_date, e.time_from, e.text)
            for e in db.scalars(select(m.SofEntry).where(m.SofEntry.vessel_file_id == vf.id))
        }
        added = 0
        for event_date, time_from, time_to, text in ENTRIES:
            if (event_date, time_from, text) in existing:
                continue
            db.add(m.SofEntry(
                vessel_file_id=vf.id, event_date=event_date, time_from=time_from,
                time_to=time_to, category="", location="", text=text, created_by="admin",
            ))
            added += 1
        db.commit()
        print(f"Listo: {added} eventos agregados ({len(ENTRIES) - added} ya estaban).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
