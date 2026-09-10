"""Ayudante local "Lineup Mailer".

Escucha en http://127.0.0.1:8765 y cuando la app se lo pide, crea el mail
DIRECTAMENTE en Outlook (no un .eml): Outlook agrega su firma por defecto y
este ayudante inserta el cuerpo del reporte ARRIBA de esa firma, asi la firma
queda abajo de todo. No se toca ninguna configuracion de Outlook.

Requisitos: Windows + Outlook de escritorio + paquete pywin32.
Se instala/arranca con instalar-helper.bat.
"""
from __future__ import annotations

import json
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8765
_LOCK = threading.Lock()


def compose_in_outlook(to: str, subject: str, html: str, cc: str = "") -> None:
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # olMailItem
        if to:
            mail.To = to.replace(",", ";")
        if cc:
            mail.CC = cc.replace(",", ";")
        mail.Subject = subject or ""

        # Accediendo al Inspector, Outlook precarga la firma por defecto.
        _ = mail.GetInspector
        sig = mail.HTMLBody or ""

        m = re.search(r"<body[^>]*>", sig, re.IGNORECASE)
        if m:
            mail.HTMLBody = sig[: m.end()] + html + sig[m.end():]
        else:
            mail.HTMLBody = html + sig

        mail.Display(False)  # abre la ventana de redaccion, sin enviar
    finally:
        pythoncom.CoUninitialize()


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/ping"):
            self._json(200, {"ok": True, "app": "lineup-mailer"})
        else:
            self._json(404, {"ok": False})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/compose"):
            self._json(404, {"ok": False})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"ok": False, "error": "json invalido"})
            return
        try:
            with _LOCK:
                compose_in_outlook(
                    str(data.get("to", "")),
                    str(data.get("subject", "")),
                    str(data.get("html", "")),
                    str(data.get("cc", "")),
                )
            self._json(200, {"ok": True})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"ok": False, "error": str(exc)})

    def log_message(self, *args) -> None:  # silencio
        pass


def main() -> None:
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Lineup Mailer escuchando en http://{HOST}:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
