"""Formatos de fecha y numeros para los documentos (cada plantilla conserva
el estilo que ya tenia)."""
from __future__ import annotations

import re
from datetime import date

MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]


def excel_serial(d: date) -> int:
    return (d - date(1899, 12, 30)).days


def ordinal_suffix(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def en_ordinal_upper(d: date) -> str:
    """SEPTEMBER 28TH, 2026 (Pedido de Carga y BILL)."""
    return f"{MONTHS_EN[d.month - 1].upper()} {d.day}{ordinal_suffix(d.day).upper()}, {d.year}"


def en_parts_heinlein(d: date) -> tuple[str, str, str, str]:
    """('October', '04', 'th', '2026'): los Word de Heinlein llevan el dia con dos digitos."""
    return MONTHS_EN[d.month - 1], f"{d.day:02d}", ordinal_suffix(d.day), str(d.year)


_THOUSANDS = re.compile(r"\d{1,3}([.,]\d{3})+")
_DECIMAL = re.compile(r"\d+([.,]\d+)?")


def parse_number(text: str) -> int | float | None:
    """'21.173' / '21,173' -> 21173; '12.5' -> 12.5; cualquier otra cosa -> None."""
    t = (text or "").strip().replace(" ", "")
    if not t:
        return None
    if _THOUSANDS.fullmatch(t):
        return int(re.sub(r"[.,]", "", t))
    if _DECIMAL.fullmatch(t):
        v = float(t.replace(",", "."))
        return int(v) if v.is_integer() and "." not in t and "," not in t else v
    return None
