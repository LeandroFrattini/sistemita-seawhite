from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import COOKIE_NAME, read_session_cookie
from .config import BASE_DIR
from .database import SessionLocal
from .models import User
from .routers import admin, auth, clients, exports, imports, lineup, proformador, reports, vessels
from .seed import init_db

app = FastAPI(title="Sistemita SeaWhiters")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

_CHANGE_PW_ALLOWLIST = {"/login", "/logout", "/cambiar-clave"}


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.middleware("http")
async def force_password_change(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/static") and path not in _CHANGE_PW_ALLOWLIST:
        data = read_session_cookie(request.cookies.get(COOKIE_NAME))
        if data:
            db = SessionLocal()
            try:
                user = db.get(User, data.get("uid"))
                if user and user.must_change_password:
                    return RedirectResponse("/cambiar-clave", status_code=302)
            finally:
                db.close()
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def _handle_http_exc(request: Request, exc: StarletteHTTPException):
    location = (exc.headers or {}).get("Location")
    if location:
        return RedirectResponse(location, status_code=302)
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.include_router(auth.router)
app.include_router(lineup.router)
app.include_router(clients.router)
app.include_router(imports.router)
app.include_router(admin.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(vessels.router)
app.include_router(proformador.router)
