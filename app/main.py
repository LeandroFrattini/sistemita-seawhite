from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import session_user
from .config import BASE_DIR, settings
from .database import SessionLocal
from .routers import (
    admin,
    administracion,
    auth,
    clients,
    exports,
    imports,
    lineup,
    mfa,
    operaciones,
    proformador,
    reports,
    vessels,
)
from .security import origin_ok, security_headers, warn_if_insecure_config
from .seed import init_db

# Sin /docs, /redoc ni /openapi.json: no hay motivo para publicar el mapa de
# rutas de una app interna.
app = FastAPI(title="Sistemita SeaWhiters", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

_CHANGE_PW_ALLOWLIST = {"/login", "/login/2fa", "/logout", "/cambiar-clave"}
# rutas que un usuario obligado a activar el 2FA si puede usar mientras tanto
_MFA_SETUP_ALLOWLIST = _CHANGE_PW_ALLOWLIST | {"/seguridad", "/seguridad/activar"}


@app.on_event("startup")
def _startup() -> None:
    warn_if_insecure_config()
    init_db()


@app.middleware("http")
async def enforce_account_state(request: Request, call_next):
    """Antes de dejar usar el sistema: contraseña pendiente de cambio y, para
    perfiles con permisos sensibles, segundo factor obligatorio."""
    path = request.url.path
    if not path.startswith("/static") and path not in _MFA_SETUP_ALLOWLIST:
        db = SessionLocal()
        try:
            user = session_user(request, db)
            if user and user.must_change_password:
                return RedirectResponse("/cambiar-clave", status_code=302)
            if settings.mfa_enabled and user and user.requires_2fa and not user.totp_enabled:
                return RedirectResponse("/seguridad", status_code=302)
        finally:
            db.close()
    return await call_next(request)


@app.middleware("http")
async def harden_http(request: Request, call_next):
    """Chequeo de origen en POST (anti-CSRF) y cabeceras de seguridad en todo."""
    if not origin_ok(request):
        return JSONResponse({"error": "Origen no permitido"}, status_code=403)
    response = await call_next(request)
    is_static = request.url.path.startswith("/static")
    for name, value in security_headers(request, is_static).items():
        response.headers.setdefault(name, value)
    return response


@app.exception_handler(StarletteHTTPException)
async def _handle_http_exc(request: Request, exc: StarletteHTTPException):
    location = (exc.headers or {}).get("Location")
    if location:
        return RedirectResponse(location, status_code=302)
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.include_router(auth.router)
app.include_router(mfa.router)
app.include_router(lineup.router)
app.include_router(clients.router)
app.include_router(imports.router)
app.include_router(admin.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(vessels.router)
app.include_router(proformador.router)
app.include_router(operaciones.router)
app.include_router(administracion.router)
