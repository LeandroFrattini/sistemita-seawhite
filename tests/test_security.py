import json
import re
import time

import pyotp

from app.database import SessionLocal
from app.models import User
from app.security import decrypt_secret, validate_new_password

from .conftest import get_user, login, make_user

STRONG = "correcto-caballo-bateria-2026"


# --- superficie expuesta ---------------------------------------------------- #

def test_docs_y_openapi_apagados(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_cabeceras_de_seguridad(client):
    r = client.get("/login")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "127.0.0.1:8765" in r.headers["content-security-policy"]  # ayudante de Outlook
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in r.headers  # http: sin HSTS


def test_hsts_solo_por_https_y_static_cacheable(client):
    r = client.get("/login", headers={"x-forwarded-proto": "https"})
    assert "max-age=31536000" in r.headers["strict-transport-security"]
    s = client.get("/static/app.css")
    assert s.status_code == 200
    assert "no-store" not in s.headers.get("cache-control", "")
    assert s.headers["x-content-type-options"] == "nosniff"


def test_sin_sesion_redirige_a_login(client):
    assert client.get("/lineup").headers["location"] == "/login"
    assert client.get("/admin").headers["location"] == "/login"


# --- login: fuerza bruta y cookie ------------------------------------------- #

def test_bloqueo_tras_5_fallos_aunque_luego_la_clave_sea_correcta(client):
    make_user("juan")
    for _ in range(5):
        assert login(client, "juan", "mala").status_code == 401
    r = login(client, "juan", "claveLarga-2026")
    assert r.status_code == 429
    assert "Demasiados intentos" in r.text


def test_mismo_mensaje_usuario_inexistente_y_clave_mala(client):
    make_user("juan")
    a = login(client, "juan", "mala")
    b = login(client, "fantasma", "mala")
    assert a.status_code == b.status_code == 401
    assert "Usuario o contraseña incorrectos" in a.text
    assert "Usuario o contraseña incorrectos" in b.text


def test_cookie_secure_solo_por_https(client):
    make_user("juan")
    http = login(client, "juan", "claveLarga-2026")
    assert "secure" not in http.headers["set-cookie"].lower()
    assert "httponly" in http.headers["set-cookie"].lower()
    client.cookies.clear()
    https = login(client, "juan", "claveLarga-2026", headers={"x-forwarded-proto": "https"})
    assert "secure" in https.headers["set-cookie"].lower()


def test_usuario_desactivado_pierde_la_sesion(client):
    make_user("juan")
    login(client, "juan", "claveLarga-2026")
    assert client.get("/").status_code == 200
    with SessionLocal() as db:
        db.query(User).filter(User.username == "juan").one().is_active = False
        db.commit()
    assert client.get("/").headers["location"] == "/login"


# --- CSRF por origen --------------------------------------------------------- #

def test_post_de_otro_origen_rechazado(client):
    make_user("juan")
    r = client.post("/login", data={"username": "juan", "password": "claveLarga-2026"},
                    headers={"origin": "https://sitio-malicioso.example"})
    assert r.status_code == 403
    ok = client.post("/login", data={"username": "juan", "password": "claveLarga-2026"},
                     headers={"origin": "http://testserver"})
    assert ok.status_code == 302


# --- contraseñas ------------------------------------------------------------- #

def test_politica_de_contrasenas():
    assert validate_new_password("corta") is not None
    assert validate_new_password("1234567890123") is not None
    assert validate_new_password("aaaaaaaaaaaa") is not None
    assert validate_new_password("juanperez2026", "juanperez") is not None
    assert validate_new_password("contraseña123") is not None
    assert validate_new_password(STRONG, "juan") is None


def test_cambio_de_clave_exige_politica_y_cierra_otras_sesiones(client):
    make_user("juan", must_change_password=True)
    login(client, "juan", "claveLarga-2026")
    vieja = client.cookies.get("lineup_session")
    assert client.get("/").headers["location"] == "/cambiar-clave"

    debil = client.post("/cambiar-clave", data={"password": "abc12345", "password2": "abc12345"})
    assert debil.status_code == 400 and "Mínimo 10" in debil.text
    dif = client.post("/cambiar-clave", data={"password": STRONG, "password2": STRONG + "x"})
    assert dif.status_code == 400

    ok = client.post("/cambiar-clave", data={"password": STRONG, "password2": STRONG})
    assert ok.status_code == 302
    assert client.get("/").status_code == 200  # este navegador sigue con sesion

    client.cookies.set("lineup_session", vieja)  # otra sesion abierta antes del cambio
    assert client.get("/").headers["location"] == "/login"


# --- segundo factor ---------------------------------------------------------- #

def _activar_2fa(client, username):
    """Deja el 2FA activado para el usuario logueado. Devuelve (secreto, codigos)."""
    page = client.get("/seguridad")
    assert page.status_code == 200 and "<svg" in page.text
    secret = decrypt_secret(get_user(username).totp_secret_enc)
    r = client.post("/seguridad/activar", data={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    codes = re.findall(r"<code>([a-z0-9]{5}-[a-z0-9]{5})</code>", r.text)
    assert len(codes) == 8
    return secret, codes


def test_perfil_privilegiado_obligado_a_activar_2fa(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    assert client.get("/").headers["location"] == "/seguridad"
    assert client.get("/administracion").headers["location"] == "/seguridad"
    assert client.get("/seguridad").status_code == 200
    _activar_2fa(client, "jefe")
    assert client.get("/administracion").status_code == 200


def test_usuario_comun_no_esta_obligado(client):
    make_user("operador")
    login(client, "operador", "claveLarga-2026")
    assert client.get("/").status_code == 200


def test_login_con_2fa_codigo_bueno_malo_y_replay(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    secret, _ = _activar_2fa(client, "jefe")
    client.get("/logout")
    client.cookies.clear()

    r = login(client, "jefe", "claveLarga-2026")
    assert r.headers["location"] == "/login/2fa"
    assert client.get("/administracion").headers["location"] == "/login"  # aun sin sesion

    assert client.post("/login/2fa", data={"code": "000000"}).status_code == 401
    # el codigo usado al activar no se puede reutilizar (anti-replay): se usa el del paso siguiente
    siguiente = pyotp.TOTP(secret).at(int(time.time()) + 30)
    ok = client.post("/login/2fa", data={"code": siguiente})
    assert ok.status_code == 302
    assert client.get("/administracion").status_code == 200

    client.get("/logout")
    client.cookies.clear()
    login(client, "jefe", "claveLarga-2026")
    assert client.post("/login/2fa", data={"code": siguiente}).status_code == 401  # replay


def test_codigo_de_recuperacion_sirve_una_sola_vez(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    _, codes = _activar_2fa(client, "jefe")

    for intento in range(2):
        client.cookies.clear()
        login(client, "jefe", "claveLarga-2026")
        r = client.post("/login/2fa", data={"code": codes[0]})
        assert r.status_code == (302 if intento == 0 else 401)
    assert len(json.loads(get_user("jefe").totp_recovery)) == 7


def test_2fa_bloquea_tras_fallos(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    _activar_2fa(client, "jefe")
    client.cookies.clear()
    login(client, "jefe", "claveLarga-2026")
    for _ in range(5):
        client.post("/login/2fa", data={"code": "111111"})
    assert client.post("/login/2fa", data={"code": "222222"}).status_code == 429


def test_secreto_totp_se_guarda_cifrado(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    client.get("/seguridad")
    guardado = get_user("jefe").totp_secret_enc
    secret = decrypt_secret(guardado)
    assert secret and secret not in guardado


def test_admin_puede_reiniciar_2fa(client):
    make_user("jefe", is_administracion=True)
    login(client, "jefe", "claveLarga-2026")
    _activar_2fa(client, "jefe")
    jefe_id = get_user("jefe").id

    client.cookies.clear()
    login(client, "admin", "admin")
    client.post("/cambiar-clave", data={"password": STRONG, "password2": STRONG})
    _activar_2fa(client, "admin")
    r = client.post(f"/admin/users/{jefe_id}/reset-2fa")
    assert r.status_code == 302
    u = get_user("jefe")
    assert not u.totp_enabled and not u.totp_secret_enc and not u.totp_recovery


def test_no_admin_no_puede_reiniciar_2fa(client):
    make_user("operador")
    login(client, "operador", "claveLarga-2026")
    assert client.post("/admin/users/1/reset-2fa").status_code == 403
