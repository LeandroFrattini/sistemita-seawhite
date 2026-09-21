"""Entorno de pruebas: base SQLite temporal y claves fijas, definidos ANTES de
importar la app (la configuracion se lee al importar)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="lineup-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "clave-de-pruebas-larga-de-mas-de-treinta-y-dos-caracteres"
os.environ["BOOTSTRAP_ADMIN_USER"] = "admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "admin"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.config import Settings, settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import OperatedVessel, User, VesselCall, VesselExtraAgency  # noqa: E402
from app.security import ip_limiter, user_limiter  # noqa: E402
from app.seed import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def mfa_on(monkeypatch):
    """Por defecto la app trae el 2FA apagado; las pruebas lo encienden salvo
    las que verifican justamente el modo apagado (que lo vuelven a apagar)."""
    monkeypatch.setattr(settings, "mfa_enabled", True)


@pytest.fixture()
def client():
    """Cliente limpio: usuarios reiniciados (queda solo admin/admin) y
    contadores de intentos en cero."""
    init_db()
    with SessionLocal() as db:
        db.query(User).delete()
        db.query(VesselExtraAgency).delete()
        db.query(VesselCall).delete()
        db.query(OperatedVessel).delete()
        db.commit()
    init_db()  # vuelve a sembrar admin/admin
    user_limiter.clear_all()
    ip_limiter.clear_all()
    with TestClient(app, follow_redirects=False) as c:
        yield c


def make_user(username="operador", password="claveLarga-2026", **flags):
    with SessionLocal() as db:
        u = User(username=username, password_hash=hash_password(password),
                 must_change_password=flags.pop("must_change_password", False), **flags)
        db.add(u)
        db.commit()
        return u.id


def get_user(username):
    with SessionLocal() as db:
        return db.query(User).filter(User.username == username).one()


def login(client, username, password, **kw):
    return client.post("/login", data={"username": username, "password": password}, **kw)
