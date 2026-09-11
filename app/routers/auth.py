from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    authenticate,
    current_user,
    hash_password,
    make_session_cookie,
    optional_user,
)
from ..database import get_db
from ..models import User
from ..templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if optional_user(request, db):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate(db, username, password)
    if not user:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Usuario o contraseña incorrectos"}, status_code=401
        )
    dest = "/cambiar-clave" if user.must_change_password else "/"
    resp = RedirectResponse(dest, status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        make_session_cookie(user),
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/cambiar-clave", response_class=HTMLResponse)
def change_password_form(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(
        request, "change_password.html", {"user": user, "error": None, "obligatorio": user.must_change_password}
    )


@router.post("/cambiar-clave")
def change_password_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    password: str = Form(...),
    password2: str = Form(...),
):
    ctx = {"user": user, "obligatorio": user.must_change_password}
    if len(password.strip()) < 4:
        ctx["error"] = "Mínimo 4 caracteres."
        return templates.TemplateResponse(request, "change_password.html", ctx, status_code=400)
    if password != password2:
        ctx["error"] = "Las dos contraseñas no coinciden."
        return templates.TemplateResponse(request, "change_password.html", ctx, status_code=400)
    user.password_hash = hash_password(password.strip())
    user.must_change_password = False
    db.commit()
    return RedirectResponse("/", status_code=302)
