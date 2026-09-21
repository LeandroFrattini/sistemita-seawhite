import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import (
    COOKIE_NAME,
    PENDING_COOKIE_NAME,
    PENDING_MAX_AGE,
    attach_session,
    authenticate,
    current_user,
    hash_password,
    make_pending_cookie,
    optional_user,
    read_pending_cookie,
)
from ..database import get_db
from ..models import User
from ..security import (
    client_ip,
    consume_recovery_code,
    decrypt_secret,
    ip_limiter,
    is_https,
    lock_minutes,
    user_limiter,
    validate_new_password,
    verify_totp,
)
from ..templating import templates

router = APIRouter()
log = logging.getLogger("seguridad")

MSG_BAD_LOGIN = "Usuario o contraseña incorrectos"


def _locked_response(request: Request, template: str, seconds: int, ctx: dict | None = None):
    msg = f"Demasiados intentos fallidos. Probá de nuevo en {lock_minutes(seconds)} min."
    return templates.TemplateResponse(request, template, {**(ctx or {}), "error": msg}, status_code=429)


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
    ukey = f"u:{username.strip().lower()}"
    ikey = f"ip:{client_ip(request)}"
    wait = max(user_limiter.remaining_lock(ukey), ip_limiter.remaining_lock(ikey))
    if wait:
        log.warning("login bloqueado usuario=%s ip=%s", username.strip(), client_ip(request))
        return _locked_response(request, "login.html", wait)

    user = authenticate(db, username, password)
    if not user:
        user_limiter.fail(ukey)
        ip_limiter.fail(ikey)
        log.warning("login fallido usuario=%s ip=%s", username.strip(), client_ip(request))
        return templates.TemplateResponse(request, "login.html", {"error": MSG_BAD_LOGIN}, status_code=401)

    user_limiter.reset(ukey)

    if user.totp_enabled:
        # clave correcta pero falta el segundo factor: cookie corta, sin sesion todavia
        resp = RedirectResponse("/login/2fa", status_code=302)
        resp.set_cookie(
            PENDING_COOKIE_NAME, make_pending_cookie(user), httponly=True, samesite="lax",
            secure=is_https(request), max_age=PENDING_MAX_AGE,
        )
        return resp

    log.info("login ok usuario=%s ip=%s", user.username, client_ip(request))
    dest = "/cambiar-clave" if user.must_change_password else "/"
    resp = RedirectResponse(dest, status_code=302)
    attach_session(resp, request, user)
    return resp


def _pending_user(request: Request, db: Session) -> User | None:
    from ..auth import password_stamp

    data = read_pending_cookie(request.cookies.get(PENDING_COOKIE_NAME))
    if not data:
        return None
    user = db.get(User, data.get("uid"))
    if not user or not user.is_active or not user.totp_enabled:
        return None
    if data.get("pv") != password_stamp(user):
        return None
    return user


@router.get("/login/2fa", response_class=HTMLResponse)
def login_2fa_form(request: Request, db: Session = Depends(get_db)):
    if not _pending_user(request, db):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(request, "login_2fa.html", {"error": None})


@router.post("/login/2fa")
def login_2fa_submit(request: Request, code: str = Form(...), db: Session = Depends(get_db)):
    user = _pending_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ukey = f"u:{user.username.lower()}"
    ikey = f"ip:{client_ip(request)}"
    wait = max(user_limiter.remaining_lock(ukey), ip_limiter.remaining_lock(ikey))
    if wait:
        return _locked_response(request, "login_2fa.html", wait)

    ok = False
    secret = decrypt_secret(user.totp_secret_enc)
    step = verify_totp(secret, code, user.totp_last_step) if secret else None
    if step is not None:
        user.totp_last_step = step
        ok = True
    else:
        remaining = consume_recovery_code(user.totp_recovery, code)
        if remaining is not None:
            user.totp_recovery = remaining
            ok = True
            log.warning("2fa: codigo de recuperacion usado usuario=%s", user.username)

    if not ok:
        user_limiter.fail(ukey)
        ip_limiter.fail(ikey)
        log.warning("2fa fallido usuario=%s ip=%s", user.username, client_ip(request))
        return templates.TemplateResponse(
            request, "login_2fa.html", {"error": "Código incorrecto o vencido."}, status_code=401
        )

    db.commit()
    user_limiter.reset(ukey)
    log.info("login ok (2fa) usuario=%s ip=%s", user.username, client_ip(request))
    dest = "/cambiar-clave" if user.must_change_password else "/"
    resp = RedirectResponse(dest, status_code=302)
    resp.delete_cookie(PENDING_COOKIE_NAME)
    attach_session(resp, request, user)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    resp.delete_cookie(PENDING_COOKIE_NAME)
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
    problem = validate_new_password(password, user.username)
    if problem:
        ctx["error"] = problem
        return templates.TemplateResponse(request, "change_password.html", ctx, status_code=400)
    if password != password2:
        ctx["error"] = "Las dos contraseñas no coinciden."
        return templates.TemplateResponse(request, "change_password.html", ctx, status_code=400)
    user.password_hash = hash_password(password.strip())
    user.must_change_password = False
    db.commit()
    log.info("cambio de contraseña usuario=%s", user.username)
    # la huella de la contraseña cambió: se reemite la sesión de ESTE navegador
    # (las de otros dispositivos quedan cerradas)
    resp = RedirectResponse("/", status_code=302)
    attach_session(resp, request, user)
    return resp
