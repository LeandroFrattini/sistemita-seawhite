"""Utilidades para parsear y formatear las fechas del line-up.

Las celdas ETA / ETB / ETC se guardan como texto tal cual las tipea el
usuario. Pueden ser una fecha (varios formatos) o texto libre como
"At roads" / "Alongside" / "".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

DISPLAY_FMT = "%d/%m/%y"  # 09/09/26  (igual que el Excel: dd/mm/yy)

_MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

_TRY_FORMATS = (
    "%d/%m/%y", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y",
    "%Y-%m-%d", "%d.%m.%y", "%d.%m.%Y", "%m/%d/%y", "%m/%d/%Y",
)


def parse_date(value: str | None, *, ref_year: int | None = None) -> date | None:
    """Devuelve un date si el texto parsea como fecha, sino None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in _TRY_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if fmt in ("%d/%m", "%d-%m", "%d.%m"):
                dt = dt.replace(year=ref_year or date.today().year)
            return dt.date()
        except ValueError:
            continue
    # "10/09" sin año
    for sep in ("/", "-", "."):
        parts = s.split(sep)
        if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
            d, m = int(parts[0]), int(parts[1])
            try:
                return date(ref_year or date.today().year, m, d)
            except ValueError:
                return None
    return None


def fmt_display(d: date | None) -> str:
    return d.strftime(DISPLAY_FMT) if d else ""


def fmt_dm(d: date | None) -> str:
    """09.09  (para el texto del formato WBL)."""
    return d.strftime("%d.%m") if d else ""


def fmt_long(d: date | None) -> str:
    """'Sep 11th'  (para los Prospects del formato WBL)."""
    if not d:
        return ""
    day = d.day
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{_MONTHS[d.month - 1]} {day}{suffix}"


def is_dateish(value: str | None) -> bool:
    return parse_date(value) is not None


def as_date_or_text(value: str | None) -> tuple[date | None, str]:
    """(date, "") si es fecha; (None, texto) si es texto libre."""
    d = parse_date(value)
    if d:
        return d, ""
    return None, (str(value).strip() if value else "")


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def eta_sort_key(primary: str, fallback: str = "") -> tuple:
    """Clave para ordenar barcos por fecha estimada (ETA o ETB, el que se
    pase como "primary", con el otro de respaldo si esta vacio o no
    parsea). "Alongside" y "At roads" no son fecha pero significan que el
    barco ya llego o esta al lado del puerto -- van primero que cualquier
    fecha, Alongside antes que At roads. Sin nada cargado, al final."""
    raw = (primary or "").strip() or (fallback or "").strip()
    low = raw.lower()
    if "alongside" in low:
        return (0, 0, date.min)
    if "roads" in low:
        return (0, 1, date.min)
    d = parse_date(primary) or parse_date(fallback)
    if d:
        return (1, 0, d)
    return (2, 0, date.max)
