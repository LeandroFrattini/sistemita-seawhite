"""Empaqueta un reporte como archivo .eml listo para abrir en Outlook.

El header ``X-Unsent: 1`` hace que Outlook lo abra como borrador editable
con el boton Enviar (no como mensaje recibido).
"""
from __future__ import annotations

import io
from email.message import EmailMessage
from email.utils import formatdate

from .config import settings


def build_eml(
    *,
    subject: str,
    to_emails: list[str],
    html_body: str,
    text_body: str,
    cc_emails: list[str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = ", ".join(to_emails)
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)
    if settings.mail_from_address:
        msg["From"] = f"{settings.mail_from_name} <{settings.mail_from_address}>"
    msg["Date"] = formatdate(localtime=True)
    msg["X-Unsent"] = "1"

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    for name, data, mime in attachments or []:
        maintype, _, subtype = mime.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=name)

    buf = io.BytesIO()
    buf.write(msg.as_bytes())
    return buf.getvalue()


def safe_filename(text: str) -> str:
    keep = "-_. ()"
    return "".join(c for c in text if c.isalnum() or c in keep).strip() or "reporte"
