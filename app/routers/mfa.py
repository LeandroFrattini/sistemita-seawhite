"""Alta del segundo factor (Google Authenticator / Microsoft Authenticator / Authy)."""
import json
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import User
from ..security import (
    decrypt_secret,
    encrypt_secret,
    lock_minutes,
    new_recovery_codes,
    new_totp_secret,
    totp_qr_svg,
    totp_uri,
    user_limiter,
    verify_totp,
)
from ..templating import templates

router = APIRouter()
log = logging.getLogger("seguridad")


def _recovery_left(user: User) -> int:
    try:
        return len(json.loads(user.totp_recovery or "[]"))
    except ValueError:
        return 0


def _render(request: Request, user: User, db: Session, *, error: str | None = None,
            codes: list[str] | None = None, status_code: int = 200):
    ctx = {
        "user": user, "error": error, "codes": codes,
        "enabled": user.totp_enabled, "recovery_left": _recovery_left(user),
        "qr": None, "manual_key": None,
    }
    if not user.totp_enabled:
        secret = decrypt_secret(user.totp_secret_enc) if user.totp_secret_enc else None
        if not secret:
            secret = new_totp_secret()
            user.totp_secret_enc = encrypt_secret(secret)
            db.commit()
        ctx["qr"] = totp_qr_svg(totp_uri(secret, user.username))
        ctx["manual_key"] = " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
    return templates.TemplateResponse(request, "seguridad.html", ctx, status_code=status_code)


@router.get("/seguridad", response_class=HTMLResponse)
def seguridad(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.mfa_enabled:
        return RedirectResponse("/", status_code=302)
    return _render(request, user, db)


@router.post("/seguridad/activar", response_class=HTMLResponse)
def activar(
    request: Request,
    code: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not settings.mfa_enabled or user.totp_enabled:
        return RedirectResponse("/seguridad" if settings.mfa_enabled else "/", status_code=302)

    key = f"setup:{user.id}"
    wait = user_limiter.remaining_lock(key)
    if wait:
        return _render(request, user, db, status_code=429,
                       error=f"Demasiados intentos. Probá de nuevo en {lock_minutes(wait)} min.")

    secret = decrypt_secret(user.totp_secret_enc) if user.totp_secret_enc else None
    step = verify_totp(secret, code, 0) if secret else None
    if step is None:
        user_limiter.fail(key)
        return _render(request, user, db, status_code=400,
                       error="Ese código no coincide. Revisá que la hora del celular sea automática e intentá de nuevo.")

    codes, hashed = new_recovery_codes()
    user.totp_enabled = True
    user.totp_last_step = step
    user.totp_recovery = hashed
    db.commit()
    user_limiter.reset(key)
    log.info("2fa activado usuario=%s", user.username)
    return _render(request, user, db, codes=codes)
