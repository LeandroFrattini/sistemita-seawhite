"""Actualiza el line-up Flammable de PRODUCCION para que coincida con la
base real que paso Leandro (captura del 15/09/2026) -- corrige fechas/
cantidades/destinos de los barcos que ya estaban cargados, agrega los que
faltaban, y deja el status_note de FLAMMABLE PIER N 1 con los dos periodos
de obra. NO borra nada por las suyas -- al final imprime una lista de
filas que estan en la base pero no en la captura, para que Leandro decida
si hay que sacarlas.

Uso:
    python scripts/update_flammable_baseline.py "postgresql://..."
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import models as m

PIER1_NOTE = (
    "OUT OF SERVICE SINCE 02/09 UNTIL 18/09 DUE TO REVAMPING WORKS)/ "
    "(OUT OF SERVICE SINCE 21/09 UNTIL 28/09 DUE TO REVAMPING WORKS"
)

# terminal_code -> [(sort_order, name, berth_label)] para las que faltan
NEW_TERMINALS = [
    ("LUIS PIEDRABUENA TERMINAL", "Luis Piedrabuena", "Luis Piedrabuena Terminal", 60),
    ("MILENIO TERMINAL", "Milenio (Base Naval Puerto Belgrano)", "Milenio Terminal", 70),
]

# updates a filas existentes, por id de vessel_call
UPDATES = {
    48: dict(eta="At roads"),
    49: dict(eta="23/09/26", etb="30/09/26", etc="01/10/26"),
    51: dict(eta="20/09/26", etb="20/09/26", etc="23/09/26"),
    52: dict(eta="17/09/26", etb="18/09/26", etc="20/09/26", quantity="", grade="GASOIL", shipper="", destination=""),
    112: dict(eta="At roads", quantity="7000/15000", grade="BUTANE/PROPANE", shipper="TGS", destination="BRAZIL", etc="17/09/26"),
    54: dict(eta="29/09/26", etb="29/09/26", etc="01/10/26"),
    113: dict(eta="22/09/26", etb="23/09/26", etc="24/09/26", destination="USA"),
    56: dict(eta="Alongside", etb=""),
    57: dict(eta="24/09/26"),
    60: dict(eta="17/09/26", etb="17/09/26", etc="18/09/26", quantity="12500", grade="GASOIL", shipper="MEGA", destination=""),
    62: dict(eta="12/09/26", etb="22/09/26", etc="23/09/26"),
    63: dict(eta="27/09/26", destination=""),
}

# filas nuevas: (terminal_code, vessel_name, campos...)
NEW_ROWS = [
    ("FLAMMABLE PIER N 1", "BOW PANTHER", dict(
        eta="22/09/26", etb="29/09/26", etc="30/09/26", operation="LOAD",
        quantity="6600", grade="CSS", shipper="UNIPAR", destination="USA",
    )),
    ("FLAMMABLE PIER N 3", "FERNI H", dict(
        eta="17/09/26", etb="17/09/26", etc="20/09/26", operation="DISCH/LOAD",
        quantity="15000", grade="NAPH/GASOIL", shipper="TRAFIGURA", destination="HOMETRADE",
    )),
    ("MEGA TERMINAL", "LA DIGUE", dict(
        eta="17/09/26", etb="20/09/26", etc="21/09/26", operation="LOAD",
        quantity="12500", grade="GASOIL", shipper="MEGA", destination="", second_call=True,
    )),
    ("PROFERTIL", "ARGENMAR MISTRAL", dict(
        eta="15/09/26", etb="15/09/26", etc="17/09/26", operation="LOAD",
        quantity="27500", grade="UREA", shipper="PROFERTIL", destination="HOMETRADE",
    )),
    ("PROFERTIL", "IONA ISLAND", dict(
        eta="18/09/26", etb="18/09/26", etc="20/09/26", operation="LOAD",
        quantity="30000", grade="UREA", shipper="PROFERTIL", destination="HOMETRADE",
    )),
]

# filas que quedan en la base pero NO aparecen en la captura -- no se tocan,
# solo se listan al final para que Leandro decida
FLAG_FOR_REVIEW = [59, 61, 53]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    engine = create_engine(sys.argv[1])
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        terminals = {t.code: t for t in db.scalars(select(m.Terminal).where(m.Terminal.kind == "FLAMMABLE"))}

        pier1 = terminals.get("FLAMMABLE PIER N 1")
        if pier1:
            pier1.status_note = PIER1_NOTE
            print("status_note de FLAMMABLE PIER N 1 actualizado")

        max_order = max((t.sort_order for t in terminals.values()), default=0)
        for code, name, berth, order in NEW_TERMINALS:
            if code not in terminals:
                t = m.Terminal(kind="FLAMMABLE", code=code, name=name, berth_label=berth,
                               sort_order=max(order, max_order + 10), active=True)
                db.add(t)
                db.flush()
                terminals[code] = t
                print(f"terminal nueva: {code}")

        updated = 0
        for call_id, fields in UPDATES.items():
            call = db.get(m.VesselCall, call_id)
            if not call:
                print(f"AVISO: no encontre vessel_call id={call_id}, lo salteo")
                continue
            for k, v in fields.items():
                setattr(call, k, v)
            updated += 1
        print(f"filas actualizadas: {updated}")

        lineup = db.scalar(
            select(m.Lineup).where(m.Lineup.kind == "FLAMMABLE", m.Lineup.status == "draft")
            .order_by(m.Lineup.id.desc())
        )
        created = 0
        for code, vessel_name, fields in NEW_ROWS:
            term = terminals[code]
            max_sort = db.scalar(
                select(m.VesselCall.sort_order).where(
                    m.VesselCall.lineup_id == lineup.id, m.VesselCall.terminal_id == term.id
                ).order_by(m.VesselCall.sort_order.desc()).limit(1)
            ) or 0
            call = m.VesselCall(
                lineup_id=lineup.id, terminal_id=term.id, sort_order=max_sort + 10,
                vessel_name=vessel_name, vessel_type="Tanker", **fields,
            )
            db.add(call)
            created += 1
        print(f"filas nuevas creadas: {created}")

        db.commit()

        print("\n--- Para revisar a mano (estan en la base, NO aparecen en la captura) ---")
        for call_id in FLAG_FOR_REVIEW:
            call = db.get(m.VesselCall, call_id)
            if call:
                print(f"  id={call.id}  {call.vessel_name}  terminal={call.terminal.code}  "
                      f"eta={call.eta} etb={call.etb} etc={call.etc}  2nd_call={call.second_call}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
