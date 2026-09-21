"""Piezas de seguridad compartidas: limite de intentos de login, politica de
contrasenas, segundo factor (TOTP), cabeceras HTTP y chequeo de origen.

Todo en memoria / sin dependencias de la base salvo el secreto TOTP, que se
guarda cifrado en el usuario."""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from urllib.parse import urlparse

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request

from .config import settings

log = logging.getLogger("seguridad")

# --------------------------------------------------------------------------- #
# Cliente / HTTPS detras del proxy de Render
# --------------------------------------------------------------------------- #


def is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https"


def client_ip(request: Request) -> str:
    """IP del cliente. En Render el trafico pasa por Cloudflare, que fija
    CF-Connecting-IP (el cliente no lo puede pisar: Cloudflare lo reescribe).
    Sin esa cabecera (desarrollo local) se cae a la IP de la conexion."""
    for header in ("cf-connecting-ip", "true-client-ip"):
        value = request.headers.get(header, "").strip()
        if value:
            return value
    return request.client.host if request.client else "desconocida"


# --------------------------------------------------------------------------- #
# Limite de intentos fallidos (login y segundo factor)
# --------------------------------------------------------------------------- #


class AttemptLimiter:
    """Bloqueo temporal tras N fallos dentro de una ventana. En memoria: si el
    servidor se reinicia se limpia, lo cual es aceptable para un solo proceso."""

    def __init__(self, max_fails: int, window: int, lock_for: int):
        self.max_fails = max_fails
        self.window = window
        self.lock_for = lock_for
        self._fails: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def remaining_lock(self, key: str) -> int:
        """Segundos que faltan de bloqueo (0 si no esta bloqueado)."""
        now = time.time()
        with self._lock:
            until = self._locked_until.get(key, 0)
            if until <= now:
                self._locked_until.pop(key, None)
                return 0
            return int(until - now) + 1

    def fail(self, key: str) -> None:
        now = time.time()
        with self._lock:
            recent = [t for t in self._fails.get(key, []) if now - t < self.window]
            recent.append(now)
            self._fails[key] = recent
            if len(recent) >= self.max_fails:
                self._locked_until[key] = now + self.lock_for
                self._fails.pop(key, None)

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()


# por usuario: 5 fallos en 15 min -> 15 min bloqueado. Por IP: mas holgado
# (varias personas pueden compartir la IP de la oficina).
user_limiter = AttemptLimiter(max_fails=5, window=15 * 60, lock_for=15 * 60)
ip_limiter = AttemptLimiter(max_fails=25, window=15 * 60, lock_for=15 * 60)


def lock_minutes(seconds: int) -> int:
    return max(1, (seconds + 59) // 60)


# --------------------------------------------------------------------------- #
# Politica de contrasenas (solo para las que se eligen desde ahora)
# --------------------------------------------------------------------------- #

MIN_PASSWORD_LEN = 10
_COMUNES = {
    "1234567890", "12345678910", "0123456789", "contraseña", "contrasena1", "contraseña1",
    "contrasena123", "contraseña123", "password123", "password1234", "qwertyuiop", "qwerty12345",
    "abcdefghij", "1q2w3e4r5t", "seawhite123", "seawhite1234", "sistemita123", "administrador",
}


def validate_new_password(password: str, username: str = "") -> str | None:
    """Devuelve un mensaje de error, o None si la contraseña sirve."""
    pw = password.strip()
    if len(pw) < MIN_PASSWORD_LEN:
        return f"Mínimo {MIN_PASSWORD_LEN} caracteres."
    if len(set(pw)) < 4:
        return "Usá una contraseña con más variedad de caracteres."
    low = pw.lower()
    if username and (low == username.lower() or username.lower() in low and len(username) >= 4):
        return "La contraseña no puede contener tu usuario."
    if low in _COMUNES:
        return "Esa contraseña es demasiado común. Elegí otra."
    if pw.isdigit():
        return "No puede ser solo números."
    return None


# --------------------------------------------------------------------------- #
# Segundo factor: TOTP (Google Authenticator, Microsoft Authenticator, Authy)
# --------------------------------------------------------------------------- #

ISSUER = "Sistemita SeaWhiters"


def _fernet() -> Fernet:
    key = hashlib.sha256((settings.secret_key + "|totp-secret").encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def totp_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def totp_qr_svg(uri: str) -> str:
    import segno

    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#123f73", light="#ffffff")


def verify_totp(secret: str, code: str, last_step: int = 0) -> int | None:
    """Verifica el codigo con +-1 paso (30 s) de tolerancia de reloj.
    Devuelve el paso usado, o None si es invalido o ya se uso (anti-replay)."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    now = int(time.time())
    for offset in (-1, 0, 1):
        t = now + offset * totp.interval
        if hmac.compare_digest(totp.at(t), code):
            step = t // totp.interval
            return step if step > last_step else None
    return None


def _hash_recovery(code: str) -> str:
    norm = "".join(ch for ch in code.lower() if ch.isalnum())
    return hmac.new(settings.secret_key.encode(), norm.encode(), hashlib.sha256).hexdigest()


def new_recovery_codes(n: int = 8) -> tuple[list[str], str]:
    """Devuelve (codigos en claro para mostrar UNA vez, JSON de hashes para guardar)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = ["".join(secrets.choice(alphabet) for _ in range(10)) for _ in range(n)]
    pretty = [f"{c[:5]}-{c[5:]}" for c in codes]
    return pretty, json.dumps([_hash_recovery(c) for c in codes])


def consume_recovery_code(stored_json: str, code: str) -> str | None:
    """Si el codigo es valido devuelve el JSON actualizado (sin ese codigo)."""
    try:
        hashes = json.loads(stored_json or "[]")
    except ValueError:
        return None
    target = _hash_recovery(code)
    for h in hashes:
        if hmac.compare_digest(h, target):
            hashes.remove(h)
            return json.dumps(hashes)
    return None


# --------------------------------------------------------------------------- #
# Cabeceras de seguridad y chequeo de origen
# --------------------------------------------------------------------------- #

# La app usa scripts/estilos inline y llama al ayudante de Outlook local
# (127.0.0.1:8765), por eso 'unsafe-inline' y ese connect-src puntual.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com data:",
    "img-src 'self' data: blob: https:",
    "connect-src 'self' http://127.0.0.1:8765 http://localhost:8765",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def security_headers(request: Request, is_static: bool) -> dict[str, str]:
    h = {
        "Content-Security-Policy": CSP,
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if is_https(request):
        h["Strict-Transport-Security"] = "max-age=31536000"
    if not is_static:
        # paginas con datos internos: que no queden en cache del navegador
        h["Cache-Control"] = "no-store"
    return h


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def origin_ok(request: Request) -> bool:
    """Defensa extra contra CSRF: un POST desde el navegador tiene que venir
    del mismo sitio. Sin Origin ni Referer (clientes que no son navegador) se deja pasar."""
    if request.method in _SAFE_METHODS:
        return True
    host = request.headers.get("host", "")
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if value:
            if value == "null":
                return False
            return urlparse(value).netloc == host
    return True


def warn_if_insecure_config() -> None:
    if settings.secret_key.startswith("cambia-esto"):
        log.warning(
            "SECRET_KEY es el valor por defecto: las sesiones se pueden falsificar. "
            "Definila como variable de entorno."
        )
    elif len(settings.secret_key) < 32:
        log.warning("SECRET_KEY es corta (menos de 32 caracteres).")
