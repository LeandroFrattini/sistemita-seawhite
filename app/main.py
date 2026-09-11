from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import BASE_DIR
from .routers import admin, auth, clients, exports, imports, lineup, reports, vessels
from .seed import init_db

app = FastAPI(title="Sistemita SeaWhiters")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


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
