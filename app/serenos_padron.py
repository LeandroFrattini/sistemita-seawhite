"""Padron de serenos (nombre y CUIL, sin tarifa): se carga en Administracion y se elige en el paso de Serenos de la proforma final."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Sereno

# La lista que paso Administracion (se carga una sola vez; despues se edita desde la pantalla)
PADRON_INICIAL = [
    ("BECERRA JOSE", "20-29919553-9"),
    ("BEVACQUA CRISTIAN", "20-23121466-7"),
    ("CURRULEF CRISTIAN", "20-28501658-5"),
    ("CURRULEF HECTOR", "20-10598488-0"),
    ("CURRULEF JORGE", "20-26704828-3"),
    ("GATTAFONI EDGARDO", "20-11825439-3"),
    ("GATTAFONI JONATAN", "20-29776416-1"),
    ("GATTAFONI MARTIN", "20-25134133-9"),
    ("GATTAFONI MIGUEL", "23-30192067-9"),
    ("GOMEZ FERNANDO", "20-34954868-3"),
    ("GOMEZ LUCAS", "20-32481816-3"),
    ("GOMEZ RAUL", "20-12136862-6"),
    ("GUERRA JAVIER", "20-22537227-7"),
    ("KOLMAN RICARDO", "20-11825564-0"),
    ("SARDEN RUBEN", "20-16813935-8"),
    ("TRINIDAD MARTIN", "20-26172020-6"),
]
# Dos mas que figuraban en la solapa CUIL del libro de serenos y no en la primera lista (se cargan una sola vez)
PADRON_V2 = [("BENTANCOURT RAUL", "20-10228584-1"), ("TREUQUE MIGUEL", "20-26571818-4")]
MARCADOR = "serenos_padron_inicial"
MARCADOR_V2 = "serenos_padron_v2"


def limpiar_nombre(txt) -> str:
    """Apellido y nombre en mayusculas, sin espacios de mas (maximo 40, que es lo que entra en la proforma)."""
    return " ".join(str(txt or "").split()).upper()[:40]


def cuil_valido(digitos: str) -> bool:
    """Digito verificador del CUIL/CUIT (modulo 11)."""
    if len(digitos) != 11 or not digitos.isdigit():
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    resto = sum(int(d) * p for d, p in zip(digitos[:10], pesos)) % 11
    verif = 11 - resto
    verif = 0 if verif == 11 else (9 if verif == 10 else verif)
    return verif == int(digitos[10])


def normalizar_cuil(txt) -> str | None:
    """'20299195539' / '20-29919553-9' -> '20-29919553-9'; None si no tiene 11 digitos."""
    d = re.sub(r"\D", "", str(txt or ""))
    return f"{d[:2]}-{d[2:10]}-{d[10]}" if len(d) == 11 else None


def sembrar(db: Session) -> None:
    """Carga la lista inicial una sola vez (si despues borran a alguien no vuelve a aparecer)."""
    existentes = {c for (c,) in db.execute(select(Sereno.cuil))}
    for marcador, lista in ((MARCADOR, PADRON_INICIAL), (MARCADOR_V2, PADRON_V2)):
        if db.get(AppSetting, marcador):
            continue
        for nombre, cuil in lista:
            if cuil not in existentes:
                db.add(Sereno(nombre=nombre, cuil=cuil))
                existentes.add(cuil)
        db.add(AppSetting(key=marcador, value="1"))
