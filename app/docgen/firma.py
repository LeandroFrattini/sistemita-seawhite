"""Prepara la firma del capitan para pegarla en los documentos: se le saca el
fondo blanco (queda solo el trazo), se recorta al contenido y se achica si es
muy grande. Asi se ve igual sobre cualquier planilla y no tapa lineas ni texto."""
from __future__ import annotations

import io

from PIL import Image, ImageOps, ImageStat

MAX_SIZE = (900, 360)
WORK_SIZE = 2200  # las fotos grandes se achican antes de procesarlas
PAPER_MARGIN = 22  # cuanto mas oscuro que el papel tiene que ser un punto para contar como trazo
INK_RANGE = 120  # que tan rapido el trazo pasa de transparente a opaco


def normalize_firma(data: bytes) -> bytes:
    """Devuelve un PNG con fondo transparente. Falla con ValueError."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - cualquier archivo ilegible
        raise ValueError("No se pudo leer la imagen de la firma") from exc

    img = ImageOps.exif_transpose(img)  # fotos del celular: respeta la rotacion
    img.thumbnail((WORK_SIZE, WORK_SIZE), Image.LANCZOS)
    img = img.convert("RGBA")
    rgb = img.convert("RGB")
    gray = rgb.convert("L")

    # el "papel" no siempre es blanco puro (foto del celular): se toma como fondo lo claro que predomina
    hist = gray.histogram()
    total, acc, paper = sum(hist), 0, 255
    for level, count in enumerate(hist):
        acc += count
        if acc >= total * 0.6:
            paper = level
            break
    paper = max(150, min(250, paper + 8))
    white_from = paper - PAPER_MARGIN

    # transparencia segun lo oscuro del trazo (y respetando una transparencia que ya traiga)
    alpha = gray.point(lambda v: 0 if v >= white_from else min(255, int((white_from - v) * 255 / INK_RANGE)))
    original_alpha = img.getchannel("A")
    alpha = Image.eval(alpha, lambda v: v)  # copia
    if original_alpha.getextrema() != (255, 255):
        from PIL import ImageChops

        alpha = ImageChops.multiply(alpha, original_alpha)

    bbox = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if bbox is None:
        raise ValueError("La firma parece estar vacía o ser toda blanca")

    # color del trazo: promedio de los puntos oscuros (queda parejo, sin halo gris en los bordes)
    dark = gray.point(lambda v: 255 if v < 110 else 0)
    ink = (0, 0, 0)
    if dark.getbbox() is not None:
        mean = ImageStat.Stat(rgb, mask=dark).mean
        ink = tuple(int(c) for c in mean[:3])

    out = Image.new("RGBA", img.size, ink + (0,))
    out.putalpha(alpha)
    out = out.crop(bbox)
    out.thumbnail(MAX_SIZE, Image.LANCZOS)

    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()
