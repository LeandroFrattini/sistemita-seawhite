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
