"""Firmas digitales de los serenos: se cargan una vez y salen solas en el recibo del sereno cuando se lo elige.

- `preparar`: deja la imagen lista para el recibo (PNG con fondo transparente, recortada a la tinta y achicada).
- `leer_zip`: lee un ZIP con una imagen por sereno (con los topes de tamano que corresponden a un archivo que viene de afuera).
- `emparejar`: propone a que sereno corresponde cada archivo por su nombre («01_Becerra_Jose.png» -> BECERRA JOSE), aunque este escrito un poco distinto.
Las firmas son datos personales: se guardan en la base (no en el repositorio) y solo las ve quien tiene acceso a los datos reservados.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from difflib import SequenceMatcher

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_ARCHIVO = 8 * 1024 * 1024        # una imagen de firma (sin comprimir)
MAX_ZIP = 40 * 1024 * 1024           # el ZIP subido
MAX_TOTAL_ZIP = 120 * 1024 * 1024    # lo que ocupan todas las imagenes ya descomprimidas
MAX_IMAGENES = 60
MAX_PIXELES = 40_000_000             # contra imagenes bomba
ANCHO_MAX, ALTO_MAX = 420, 150       # tamano guardado (el doble de lo que se ve en el recibo, para que se vea nitida)
EXTENSIONES = (".png", ".jpg", ".jpeg", ".webp")


class FirmaInvalida(ValueError):
    """El archivo no sirve como firma (con el motivo para mostrarle al usuario)."""


def preparar(datos: bytes) -> bytes:
    """Imagen cualquiera -> PNG con fondo transparente, recortado a la firma y achicado. Si el fondo es blanco (sin transparencia) lo pasa a transparente."""
    if not datos or len(datos) > MAX_ARCHIVO:
        raise FirmaInvalida("La imagen está vacía o pesa más de 8 MB.")
    try:
        Image.MAX_IMAGE_PIXELS = MAX_PIXELES
        im = Image.open(io.BytesIO(datos))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise FirmaInvalida("El archivo no es una imagen válida (PNG o JPG).") from None
    im = ImageOps.exif_transpose(im).convert("RGBA")
    alfa = im.getchannel("A")
    if alfa.getextrema()[0] >= 250:  # sin transparencia: el blanco pasa a ser transparente (la tinta queda con su intensidad)
        gris = ImageOps.invert(im.convert("L"))
        alfa = gris.point(lambda v: 0 if v < 18 else min(255, int((v - 18) * 255 / 200)))
        im.putalpha(alfa)
    caja = alfa.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not caja:
        raise FirmaInvalida("No se ve ninguna firma en la imagen (está en blanco).")
    margen = 6
    im = im.crop((max(0, caja[0] - margen), max(0, caja[1] - margen), min(im.width, caja[2] + margen), min(im.height, caja[3] + margen)))
    if im.width > ANCHO_MAX or im.height > ALTO_MAX:
        im.thumbnail((ANCHO_MAX, ALTO_MAX), Image.LANCZOS)
    salida = io.BytesIO()
    im.save(salida, "PNG", optimize=True)
    return salida.getvalue()


def medidas(png: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(png)) as im:
        return im.size


def leer_zip(datos: bytes) -> list[tuple[str, bytes]]:
    """[(nombre de archivo, bytes)] de las imagenes del ZIP, con topes (cantidad, peso y rutas raras). Lanza FirmaInvalida si no se puede leer."""
    if len(datos) > MAX_ZIP:
        raise FirmaInvalida("El ZIP pesa más de 40 MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        raise FirmaInvalida("El archivo no es un ZIP válido.") from None
    out, total = [], 0
    for info in z.infolist():
        nombre = info.filename.replace("\\", "/")
        base = nombre.rsplit("/", 1)[-1]
        if info.is_dir() or not base or base.startswith(".") or "__MACOSX" in nombre or not base.lower().endswith(EXTENSIONES):
            continue
        if info.file_size > MAX_ARCHIVO:
            raise FirmaInvalida(f"«{base}» pesa más de 8 MB.")
        total += info.file_size
        if total > MAX_TOTAL_ZIP or len(out) >= MAX_IMAGENES:
            raise FirmaInvalida("El ZIP trae demasiadas imágenes o pesa demasiado.")
        out.append((base, z.read(info)))
    if not out:
        raise FirmaInvalida("El ZIP no trae imágenes (PNG o JPG).")
    return out


# ------------------------------------------------------------------------------------------------------------- emparejar
def _limpio(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]+", " ", txt)).strip()


def _nombre_de_archivo(archivo: str) -> str:
    base = re.sub(r"\.[A-Za-z0-9]+$", "", archivo.rsplit("/", 1)[-1])
    base = re.sub(r"^[\d\s._()-]+", "", base)           # el numero de orden del principio («01_», «17-»)
    return _limpio(base.replace("_", " ").replace("-", " "))


def _parecido(a: str, b: str) -> float:
    """Que tan parecidos son dos nombres, sin importar el orden (apellido nombre / nombre apellido)."""
    inv = " ".join(reversed(a.split()))
    return max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, inv, b).ratio())


def emparejar(archivo: str, serenos: list[tuple[int, str]]) -> dict:
    """Propone a que sereno corresponde un archivo: {sereno_id, nombre, seguro, puntaje, alternativas}. `serenos` = [(id, nombre)].
    `seguro` solo si el mejor parecido es claro y le saca ventaja al segundo (si no, se pide elegir a mano)."""
    n = _nombre_de_archivo(archivo)
    ranking = sorted(((_parecido(n, _limpio(nom)), i, nom) for i, nom in serenos), reverse=True)
    if not ranking or not n:
        return {"sereno_id": None, "nombre": "", "seguro": False, "puntaje": 0.0, "alternativas": []}
    mejor = ranking[0]
    segundo = ranking[1][0] if len(ranking) > 1 else 0.0
    seguro = mejor[0] >= 0.8 and (mejor[0] - segundo) >= 0.06
    return {"sereno_id": mejor[1] if seguro else None, "nombre": mejor[2], "seguro": seguro, "puntaje": round(mejor[0], 3),
            "alternativas": [{"id": i, "nombre": nom, "puntaje": round(p, 3)} for p, i, nom in ranking[:3]]}
