"""Tabla de mareas (predicciones del Servicio de Hidrografia Naval) para Puerto Ingeniero White, que se muestra en el Line-up.

Los datos se guardan en la tabla `mareas`. Vienen de dos lados:
- un archivo con el ano cargado (app/data/mareas_iwhi_YYYY.json) que se siembra al arrancar, para que funcione aunque el SHN no responda;
- la consulta del SHN (www.hidro.gov.ar, tablas de marea), que se hace sola cuando falta un mes (por ejemplo al empezar un ano nuevo).
Son predicciones: la marea real puede diferir por viento y presion, por eso en pantalla se muestran como tentativas.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import BASE_DIR
from .models import Marea

log = logging.getLogger("mareas")

PUERTO = "IWHI"
NOMBRE = "Puerto Ingeniero White"
NIVEL_MEDIO = 2.74  # m sobre el plano de reduccion (de la tabla del SHN): arriba es pleamar, abajo bajamar
URL = "https://www.hidro.gov.ar/oceanografia/tmareas/RE_TablasDeMarea.asp"
_AR = timezone(timedelta(hours=-3), name="ART")
DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_ULTIMO_INTENTO: dict[str, float] = {}  # mes -> cuando se intento bajarlo (para no insistir si el SHN no responde)
REINTENTO_SEG = 3600

_FILA = re.compile(r'<td\s+CLASS="text-primary">\s*(\d{0,2})\s*</td>\s*<td>(\d{2}:\d{2})</td>\s*<td>([\d,.]+)</td>', re.I)


def hoy() -> date:
    return datetime.now(_AR).date()


def parsear(html: str, anio: int, mes: int) -> list[tuple[str, str, float]]:
    """(fecha ISO, 'HH:MM', altura en m) de cada pleamar/bajamar del mes, o [] si la respuesta no es del mes pedido."""
    if f"{mes:02d}" not in html or f"/{anio}" not in html or "Predicciones de las Pleamares" not in html:
        return []
    out, dia = [], 0
    for d, hora, alt in _FILA.findall(html):
        if d:
            dia = int(d)
        if not dia:
            continue
        try:
            out.append((date(anio, mes, dia).isoformat(), hora, float(alt.replace(",", "."))))
        except ValueError:
            continue
    return out


def descargar(anio: int, mes: int, puerto: str = PUERTO, timeout: int = 15) -> list[tuple[str, str, float]]:
    """Consulta el SHN y devuelve las mareas del mes (lista vacia si no se pudo)."""
    req = urllib.request.Request(URL, data=urllib.parse.urlencode({"FAnio": anio, "Localidad": puerto, "FMes": f"{mes:02d}"}).encode(),
                                 headers={"User-Agent": "Mozilla/5.0 (Sistemita SeaWhiters)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", "replace")
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    if f"{meses[mes - 1]}/{anio}" not in html.lower():
        return []
    return parsear(html, anio, mes)


def _guardar(db: Session, filas: list[tuple[str, str, float]], puerto: str = PUERTO) -> int:
    existentes = {(m.fecha, m.hora) for m in db.scalars(select(Marea).where(Marea.puerto == puerto, Marea.fecha.in_({f for f, _h, _a in filas})))}
    nuevas = [Marea(puerto=puerto, fecha=f, hora=h, altura=a) for f, h, a in filas if (f, h) not in existentes]
    db.add_all(nuevas)
    db.commit()
    return len(nuevas)


def _tiene_mes(db: Session, anio: int, mes: int, puerto: str = PUERTO) -> bool:
    ini = date(anio, mes, 1).isoformat()
    fin = (date(anio + (mes == 12), mes % 12 + 1, 1)).isoformat()
    return db.scalar(select(Marea.id).where(Marea.puerto == puerto, Marea.fecha >= ini, Marea.fecha < fin).limit(1)) is not None


def sembrar(db: Session) -> None:
    """Carga los archivos de app/data/mareas_*.json que todavia no estan en la base."""
    for f in sorted((BASE_DIR / "app" / "data").glob("mareas_*.json")):
        try:
            datos = json.loads(f.read_text(encoding="utf-8"))
            filas = [(x[0], x[1], float(x[2])) for x in datos["mareas"]]
            meses = {x[0][:7] for x in filas}
            faltan = [x for x in filas if not _tiene_mes(db, int(x[0][:4]), int(x[0][5:7]), datos.get("puerto", PUERTO))]
            if faltan and meses:
                _guardar(db, faltan, datos.get("puerto", PUERTO))
        except Exception:
            log.exception("mareas: no se pudo sembrar %s", f.name)


def asegurar(db: Session, desde: date, hasta: date) -> None:
    """Si falta algun mes del rango, intenta bajarlo del SHN (una vez por hora como maximo). Nunca levanta error."""
    d = date(desde.year, desde.month, 1)
    while d <= hasta:
        clave = f"{d.year}-{d.month:02d}"
        if not _tiene_mes(db, d.year, d.month) and time.time() - _ULTIMO_INTENTO.get(clave, 0) > REINTENTO_SEG:
            _ULTIMO_INTENTO[clave] = time.time()
            try:
                filas = descargar(d.year, d.month)
                if filas:
                    _guardar(db, filas)
                else:
                    log.warning("mareas: el SHN no devolvio datos para %s", clave)
            except Exception:
                log.exception("mareas: no se pudo bajar %s del SHN", clave)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def proximos(db: Session, dias: int = 3, desde: date | None = None) -> dict:
    """Las mareas de hoy y los dias siguientes, listas para mostrar."""
    ini = desde or hoy()
    fin = ini + timedelta(days=dias - 1)
    asegurar(db, ini, fin)
    filas = list(db.scalars(select(Marea).where(Marea.puerto == PUERTO, Marea.fecha >= ini.isoformat(), Marea.fecha <= fin.isoformat()).order_by(Marea.fecha, Marea.hora)))
    out = []
    for k in range(dias):
        d = ini + timedelta(days=k)
        ev = [{"hora": m.hora, "altura": m.altura, "tipo": "pleamar" if m.altura >= NIVEL_MEDIO else "bajamar"} for m in filas if m.fecha == d.isoformat()]
        out.append({"fecha": d.isoformat(), "dia": DIAS_ES[d.weekday()], "eventos": ev})
    return {"puerto": NOMBRE, "nivel_medio": NIVEL_MEDIO, "dias": out, "hay_datos": any(x["eventos"] for x in out)}
