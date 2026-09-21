import hashlib

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import is_https

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="lineup-session")
# cookie intermedia entre "clave correcta" y "codigo del segundo factor"
_pending_serializer = URLSafeTimedSerializer(settings.secret_key, salt="lineup-2fa-pending")
COOKIE_NAME = "lineup_session"
PENDING_COOKIE_NAME = "lineup_2fa_pending"
# 30 dias, y el vencimiento se controla en el servidor (no solo en el
# navegador): una cookie robada deja de servir cuando vence.
SESSION_MAX_AGE = 60 * 60 * 24 * 30
PENDING_MAX_AGE = 5 * 60

# hash de relleno para gastar el mismo tiempo cuando el usuario no existe
# (evita descubrir usuarios validos midiendo la demora de la respuesta)
_DUMMY_HASH = pwd_context.hash("relleno-para-igualar-tiempos")


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(raw, hashed)
    except ValueError:
        return False


def password_stamp(user: User) -> str:
    """Huella de la contraseña actual. Va dentro de la cookie: si el usuario
    (o un admin) cambia la contraseña, todas las sesiones anteriores dejan de valer."""
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def make_session_cookie(user: User) -> str:
    return _serializer.dumps({"uid": user.id, "u": user.username, "pv": password_stamp(user)})


def attach_session(response, request: Request, user: User) -> None:
    """Pone la cookie de sesion: HttpOnly, SameSite=Lax y Secure cuando el
    acceso es por HTTPS (en local, sobre http, no se marca Secure para poder probar)."""
    response.set_cookie(
        COOKIE_NAME,
        make_session_cookie(user),
        httponly=True,
        samesite="lax",
        secure=is_https(request),
        max_age=SESSION_MAX_AGE,
    )


def read_session_cookie(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return _serializer.loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def make_pending_cookie(user: User) -> str:
    return _pending_serializer.dumps({"uid": user.id, "pv": password_stamp(user)})


def read_pending_cookie(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return _pending_serializer.loads(raw, max_age=PENDING_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def session_user(request: Request, db: Session) -> User | None:
    """Usuario de la sesion, o None si no hay sesion valida (firma, vencimiento,
    usuario activo y contraseña sin cambios desde que se inició)."""
    data = read_session_cookie(request.cookies.get(COOKIE_NAME))
    if not data:
        return None
    user = db.get(User, data.get("uid"))
    if not user or not user.is_active:
        return None
    if data.get("pv") != password_stamp(user):
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = session_user(request, db)
    if not user:
        raise _redirect_login()
    return user


def admin_required(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administradores")
    return user


def pda_admin_required(user: User = Depends(current_user)) -> User:
    """Permiso especifico para editar el tarifario del Proformador -- se
    activa por perfil (checkbox en Admin -> Usuarios), no por is_admin."""
    if not user.is_admin and not user.is_pda_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere permiso de Administrador de PDA")
    return user


def administracion_required(user: User = Depends(current_user)) -> User:
    """Permiso especifico para entrar a la seccion Administracion -- se
    activa por perfil (checkbox en Admin -> Usuarios), no por is_admin."""
    if not user.is_admin and not user.is_administracion:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere permiso de Administracion")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return session_user(request, db)


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if not user:
        verify_password(password, _DUMMY_HASH)  # mismo costo que un usuario real
        return None
    if verify_password(password, user.password_hash) and user.is_active:
        return user
    return None


class _redirect_login(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
