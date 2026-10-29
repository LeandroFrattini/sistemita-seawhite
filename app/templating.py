from datetime import timedelta, timezone

from fastapi.templating import Jinja2Templates

from .config import BASE_DIR, settings
from .dates import display_eta

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Todos los timestamps se guardan en UTC (server_default=func.now(), hora
# del servidor) -- Argentina es UTC-3 fijo (sin horario de verano desde
# 2009), asi que alcanza con un offset fijo en vez de zoneinfo/tzdata.
_AR_TZ = timezone(timedelta(hours=-3), name="ART")


def localdt(value, fmt: str = "%d/%m/%Y %H:%M") -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_AR_TZ).strftime(fmt)


def hace(value) -> str:
    """'hace 5 min', 'hace 2 h', 'ayer 10:24', 'hace 3 días' o la fecha: para ver de un vistazo cuanto hace que paso algo."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    from datetime import datetime

    seg = (datetime.now(timezone.utc) - value).total_seconds()
    if seg < 60:
        return "recién"
    if seg < 3600:
        return f"hace {int(seg // 60)} min"
    if seg < 86400 and value.astimezone(_AR_TZ).date() == datetime.now(_AR_TZ).date():
        return f"hace {int(seg // 3600)} h"
    dias = (datetime.now(_AR_TZ).date() - value.astimezone(_AR_TZ).date()).days
    if dias == 1:
        return "ayer " + value.astimezone(_AR_TZ).strftime("%H:%M")
    if dias < 7:
        return f"hace {dias} días"
    return value.astimezone(_AR_TZ).strftime("%d/%m/%Y")


def color_idx(texto) -> int:
    """0 a 5, siempre el mismo para el mismo texto (para darle a cada persona su color)."""
    return sum(ord(c) for c in (texto or "?")) % 6


def fmt_zarpe(value: str) -> str:
    """'2026-09-20T20:15' (datetime-local) -> '20/09/2026 20:15'."""
    if not value:
        return ""
    try:
        d, t = value.split("T")
        y, m, day = d.split("-")
        return f"{day}/{m}/{y} {t}"
    except ValueError:
        return value


def _static_version(name: str) -> str:
    # mtime del archivo: cada deploy con cambios de CSS/JS cambia la URL y
    # el navegador no se queda con la version vieja en cache.
    try:
        return str(int((BASE_DIR / "app" / "static" / name).stat().st_mtime))
    except OSError:
        return "0"


templates.env.globals["static_v"] = _static_version
# funcion (no valor) para que se lea la configuracion en cada render
templates.env.globals["mfa_enabled"] = lambda: settings.mfa_enabled
templates.env.filters["localdt"] = localdt
templates.env.filters["etadisp"] = display_eta
templates.env.filters["fmtzarpe"] = fmt_zarpe


def ars(value, decimales: int = 2) -> str:
    """1234567.891 -> '$ 1.234.567,89' (formato argentino)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    s = f"{n:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "$ " + s


_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def mes_nombre(value: str) -> str:
    """'2026-10' -> 'octubre 2026'."""
    try:
        return f"{_MESES[int(value[5:7]) - 1]} {value[:4]}"
    except (ValueError, IndexError, TypeError):
        return str(value or "")


templates.env.filters["ars"] = ars
templates.env.filters["hace"] = hace
templates.env.filters["color_idx"] = color_idx
templates.env.filters["mesnom"] = mes_nombre
