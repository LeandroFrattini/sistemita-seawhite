"""Normaliza los logos de las agencias: se recortan los margenes vacios y se
acomodan en un lienzo fijo, asi todos salen del mismo tamano en los documentos."""
from __future__ import annotations

import io

from PIL import Image, ImageChops

CANVAS = (800, 400)  # proporcion 2:1, parecida a la caja del encabezado de los documentos
MAX_UPSCALE = 12.0


def normalize_logo(data: bytes) -> bytes:
    """Devuelve un PNG de 800x400 con el logo recortado y centrado. Falla con ValueError."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - cualquier archivo ilegible
        raise ValueError("No se pudo leer la imagen del logo") from exc

    img = img.convert("RGBA")

    # contenido = lo que no es transparente ni casi blanco
    not_white = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, (255, 255, 255)))
    not_white = not_white.convert("L").point(lambda v: 255 if v > 12 else 0)
    opaque = img.getchannel("A").point(lambda v: 255 if v > 10 else 0)
    bbox = ImageChops.multiply(not_white, opaque).getbbox()
    if bbox is None:
        raise ValueError("El logo parece estar vacío o ser todo blanco")
    img = img.crop(bbox)

    w, h = img.size
    scale = min(CANVAS[0] / w, CANVAS[1] / h, MAX_UPSCALE)
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    img = img.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGBA", CANVAS, (255, 255, 255, 0))
    canvas.paste(img, ((CANVAS[0] - new_size[0]) // 2, (CANVAS[1] - new_size[1]) // 2), img)
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    return out.getvalue()
