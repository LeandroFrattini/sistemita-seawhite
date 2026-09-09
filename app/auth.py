from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeSerializer(settings.secret_key, salt="lineup-session")
COOKIE_NAME = "lineup_session"


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(raw, hashed)
    except ValueError:
        return False


def make_session_cookie(user: User) -> str:
    return _serializer.dumps({"uid": user.id, "u": user.username})


def read_session_cookie(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return _serializer.loads(raw)
    except BadSignature:
        return None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    data = read_session_cookie(request.cookies.get(COOKIE_NAME))
    if not data:
        raise _redirect_login()
    user = db.get(User, data.get("uid"))
    if not user or not user.is_active:
        raise _redirect_login()
    return user


def admin_required(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administradores")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    data = read_session_cookie(request.cookies.get(COOKIE_NAME))
    if not data:
        return None
    return db.get(User, data.get("uid"))


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip()))
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


class _redirect_login(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
