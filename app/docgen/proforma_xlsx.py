"""Excel final de la proforma, con el formato de las proformas reales de Sea White (hoja de la agencia, SERENOS y TALLY).

Se parte de la plantilla `templates/proforma_final.xlsx` (la proforma de PORT ALBERNI sin datos: membrete, estilos, anchos e imagenes) y se
escribe el XML de las hojas (como el resto de los documentos del sistema: no se usa openpyxl para no perder formato ni imagenes).
Los renglones de la hoja de la agencia, la grilla de SERENOS y la lista de TALLY se arman segun lo que haya, con formulas (como las originales,
para que las chicas puedan retocar) y con su valor guardado, para que se vea bien tambien en Vista protegida o en el celular.
Todo va en PESOS y en USD, con el dolar unico del paso 1. Ademas lleva dos hojas ocultas: `_estado` (para volver a cargar la proforma)
y `_resumen` (la foto de lo cargado en cada paso, con sus notas).
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

from lxml import etree

from .fechas import excel_serial, parse_number
from .xlsx_fill import M, NS_CT, NS_MAIN, NS_PKG_REL, NS_XDR, Xlsx, _col_idx, _split

PLANTILLA = Path(__file__).resolve().parent / "templates" / "proforma_final.xlsx"
SALIDA = {"xml_declaration": True, "encoding": "UTF-8", "standalone": True}
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DIAS_EN = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

# estilos de la plantilla (indices de cellXfs de la proforma de PORT ALBERNI)
E_LINEA = {"A": 14, "B": 40, "C": 14, "D": 1, "E": 15}      # renglon: numero, guion, concepto, pesos, USD
E_VACIA = {"A": 14, "B": 40, "C": 14, "D": 1, "E": 54}      # fila en blanco antes del total
E_TOTAL = {"A": 14, "B": 53, "C": 55, "D": 56, "E": 57}     # TOTAL
E_PIE_TITULO = {"A": 14, "B": 53, "C": 58}                  # FOR YOUR ACCOUNT
FONDO = 24                                                   # celda blanca (tapa las lineas de la cuadricula)


_INVALIDOS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def limpio(t) -> str:
    """Texto apto para el XML de un Excel (sin caracteres de control)."""
    return _INVALIDOS.sub("", str(t))


def letra(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Hoja(Xlsx):
    """Una hoja del libro (comparte las partes con las otras hojas)."""

    def __init__(self, libro: "Libro", ruta: str):
        self.libro, self.parts, self.order, self.ruta = libro, libro.parts, libro.order, ruta
        self.root = etree.fromstring(libro.parts[ruta])
        self.sheet_data = self.root.find(M + "sheetData")

    def volcar(self) -> None:
        self.parts[self.ruta] = etree.tostring(self.root, **SALIDA)

    # -- escritura
    def poner(self, ref: str, valor=None, estilo: int | None = None, formula: str | None = None) -> None:
        """Escribe una celda: numero, texto, fecha (serial) o formula con su valor guardado. Sin estilo, conserva el que tenia."""
        c = self._cell(ref)
        self._wipe(c)
        if estilo is not None:
            c.set("s", str(estilo))
        if isinstance(valor, (date, datetime)):
            valor = excel_serial(valor if isinstance(valor, date) and not isinstance(valor, datetime) else valor.date())
        if formula is not None:
            f = etree.SubElement(c, M + "f")
            f.text = formula
            if isinstance(valor, (int, float)):
                etree.SubElement(c, M + "v").text = format(valor, ".15g")
        elif isinstance(valor, bool):
            etree.SubElement(c, M + "v").text = "1" if valor else "0"
        elif isinstance(valor, (int, float)):
            etree.SubElement(c, M + "v").text = format(valor, ".15g")
        elif isinstance(valor, str) and valor != "":
            c.set("t", "inlineStr")
            is_ = etree.SubElement(c, M + "is")
            t = etree.SubElement(is_, M + "t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = limpio(valor)

    def altura(self, n: int, ht: float) -> None:
        row = self._row(n)
        row.set("ht", str(ht))
        row.set("customHeight", "1")

    def fondo(self, fila: int, desde: str, hasta: str) -> None:
        """Pone celda blanca en las columnas que todavia no tengan nada (para que no se vea la cuadricula)."""
        existentes = {_split(c.get("r"))[0] for c in self._row(fila).findall(M + "c")}
        for k in range(_col_idx(desde), _col_idx(hasta) + 1):
            if letra(k) not in existentes:
                self.poner(f"{letra(k)}{fila}", None, FONDO)

    def vaciar_desde(self, fila: int) -> None:
        for row in list(self.sheet_data):
            if int(row.get("r")) >= fila:
                self.sheet_data.remove(row)
        merges = self.root.find(M + "mergeCells")
        if merges is not None:
            for el in list(merges):
                if _split(el.get("ref").split(":")[0])[1] >= fila:
                    merges.remove(el)

    def vaciar_celdas(self, desde: int, hasta: int) -> None:
        """Borra el contenido (no el formato) de las filas indicadas."""
        for row in self.sheet_data.findall(M + "row"):
            if desde <= int(row.get("r")) <= hasta:
                for c in row.findall(M + "c"):
                    self._wipe(c)

    def unir(self, rango: str) -> None:
        merges = self.root.find(M + "mergeCells")
        if merges is None:
            merges = etree.Element(M + "mergeCells")
            self.sheet_data.addnext(merges)
        if any(el.get("ref") == rango for el in merges):
            return
        etree.SubElement(merges, M + "mergeCell").set("ref", rango)
        merges.set("count", str(len(merges)))

    def sin_uniones(self, rango: str) -> None:
        merges = self.root.find(M + "mergeCells")
        if merges is None:
            return
        for el in list(merges):
            if el.get("ref") == rango:
                merges.remove(el)
        if len(merges):
            merges.set("count", str(len(merges)))
        else:
            self.root.remove(merges)

    def columnas(self, anchos: list[tuple[int, int, float]], estilo: int | None = None) -> None:
        viejo = self.root.find(M + "cols")
        if viejo is not None:
            self.root.remove(viejo)
        cols = etree.Element(M + "cols")
        for mn, mx, w in anchos:
            el = etree.SubElement(cols, M + "col", min=str(mn), max=str(mx), width=str(w), customWidth="1")
            if estilo is not None:
                el.set("style", str(estilo))
        self.sheet_data.addprevious(cols)

    def dimension(self, ref: str) -> None:
        d = self.root.find(M + "dimension")
        if d is not None:
            d.set("ref", ref)

    def sin_seleccion(self) -> None:
        """Deja la hoja abierta arriba a la izquierda (la plantilla trae la celda activa donde la dejo quien la guardo)."""
        for sv in self.root.iter(M + "sheetView"):
            sv.attrib.pop("topLeftCell", None)
            for sel in sv.findall(M + "selection"):
                sel.set("activeCell", "A1")
                sel.set("sqref", "A1")


class Libro:
    def __init__(self, ruta: Path = PLANTILLA):
        with zipfile.ZipFile(ruta) as z:
            self.order = z.namelist()
            self.parts: dict[str, bytes] = {n: z.read(n) for n in self.order}
        self.hojas: list[Hoja] = []

    def hoja(self, n: int) -> Hoja:
        h = Hoja(self, f"xl/worksheets/sheet{n}.xml")
        self.hojas.append(h)
        return h

    def renombrar(self, indice: int, nombre: str) -> None:
        wb = etree.fromstring(self.parts["xl/workbook.xml"])
        wb.find(M + "sheets")[indice - 1].set("name", nombre)
        self.parts["xl/workbook.xml"] = etree.tostring(wb, **SALIDA)

    def estilo_con_numfmt(self, base: int, fuente: int) -> int:
        """Un estilo igual a `base` pero con el formato de numero de `fuente` (por ejemplo, el de USD)."""
        import copy

        styles = etree.fromstring(self.parts["xl/styles.xml"])
        xfs = styles.find(M + "cellXfs")
        nuevo = copy.deepcopy(xfs[base])
        nuevo.set("numFmtId", xfs[fuente].get("numFmtId"))
        nuevo.set("applyNumberFormat", "1")
        xfs.append(nuevo)
        xfs.set("count", str(len(xfs)))
        self.parts["xl/styles.xml"] = etree.tostring(styles, **SALIDA)
        return len(xfs) - 1

    def imagen_pie(self, fila0: int) -> None:
        """Baja la imagen del pie (la segunda del membrete) para que quede debajo de lo ultimo que se escribio. fila0 es base 0."""
        ruta = "xl/drawings/drawing1.xml"
        dr = etree.fromstring(self.parts[ruta])
        anclas = dr.findall("{%s}twoCellAnchor" % NS_XDR)
        ancla = anclas[-1]
        desde, hasta = ancla.find("{%s}from" % NS_XDR), ancla.find("{%s}to" % NS_XDR)
        alto = int(hasta.find("{%s}row" % NS_XDR).text) - int(desde.find("{%s}row" % NS_XDR).text)
        desde.find("{%s}row" % NS_XDR).text = str(fila0)
        hasta.find("{%s}row" % NS_XDR).text = str(fila0 + alto)
        self.parts[ruta] = etree.tostring(dr, **SALIDA)

    def agregar_hoja_oculta(self, nombre: str, filas: list[list]) -> None:
        """Hoja oculta con texto/numeros (una lista de filas). Sirve para el estado (releer la proforma) y la foto de los pasos."""
        usados = [int(m.group(1)) for n in self.parts for m in [re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", n)] if m]
        k = max(usados) + 1
        ruta = f"xl/worksheets/sheet{k}.xml"
        ws = etree.Element(M + "worksheet", nsmap={None: NS_MAIN})
        sd = etree.SubElement(ws, M + "sheetData")
        for i, fila in enumerate(filas, start=1):
            row = etree.SubElement(sd, M + "row", r=str(i))
            for j, v in enumerate(fila, start=1):
                if v in (None, ""):
                    continue
                c = etree.SubElement(row, M + "c", r=f"{letra(j)}{i}")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    etree.SubElement(c, M + "v").text = format(v, ".15g")
                else:
                    c.set("t", "inlineStr")
                    t = etree.SubElement(etree.SubElement(c, M + "is"), M + "t")
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    t.text = limpio(v)
        self.parts[ruta] = etree.tostring(ws, **SALIDA)
        self.order.append(ruta)
        ct = etree.fromstring(self.parts["[Content_Types].xml"])
        etree.SubElement(ct, "{%s}Override" % NS_CT, PartName="/" + ruta, ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
        self.parts["[Content_Types].xml"] = etree.tostring(ct, **SALIDA)
        rels = etree.fromstring(self.parts["xl/_rels/workbook.xml.rels"])
        rid = "rId" + str(max([int(re.sub(r"\D", "", r.get("Id")) or 0) for r in rels] + [0]) + 1)
        etree.SubElement(rels, "{%s}Relationship" % NS_PKG_REL, Id=rid, Type=NS_R + "/worksheet", Target=f"worksheets/sheet{k}.xml")
        self.parts["xl/_rels/workbook.xml.rels"] = etree.tostring(rels, **SALIDA)
        wb = etree.fromstring(self.parts["xl/workbook.xml"])
        sheets = wb.find(M + "sheets")
        sid = max(int(s.get("sheetId")) for s in sheets) + 1
        el = etree.SubElement(sheets, M + "sheet", name=nombre, sheetId=str(sid), state="hidden")
        el.set("{%s}id" % NS_R, rid)
        self.parts["xl/workbook.xml"] = etree.tostring(wb, **SALIDA)

    def to_bytes(self) -> bytes:
        for h in self.hojas:
            h.volcar()
        wb = etree.fromstring(self.parts["xl/workbook.xml"])
        calc = wb.find(M + "calcPr")
        if calc is None:
            calc = etree.SubElement(wb, M + "calcPr")
        calc.set("fullCalcOnLoad", "1")  # Excel recalcula al abrir (los valores guardados son para los visores que no lo hacen)
        self.parts["xl/workbook.xml"] = etree.tostring(wb, **SALIDA)
        buf = io.BytesIO()
        nombres = ["[Content_Types].xml"] + [n for n in self.order if n != "[Content_Types].xml"]
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in nombres:
                z.writestr(n, self.parts[n])
        return buf.getvalue()


# ----------------------------------------------------------------------------------------------------------------------- utilidades
def fecha_larga(iso: str) -> str:
    """'2026-09-25T14:12' -> 'FRI 25/09/2026 14:12 HR' (como figura en las proformas)."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return ""
    return f"{DIAS_EN[d.weekday()]} {d.strftime('%d/%m/%Y %H:%M')} HR"


def titulo_buque(nombre: str) -> str:
    n = " ".join((nombre or "").split()).upper()
    return n if re.match(r"^(MV|M/V|M\.V\.)\b", n) else ("MV " + n if n else "")


def nombre_hoja(agencia: str) -> str:
    n = re.sub(r"[\[\]:*?/\\]", " ", " ".join((agencia or "").split()).upper()).strip()[:31]
    return n or "PROFORMA"


def _serial(iso_fecha: str) -> int:
    return excel_serial(date.fromisoformat(iso_fecha))


# ---------------------------------------------------------------------------------------------------------------- hoja de la agencia
def _principal(h: Hoja, s: dict, ch: dict, dias: dict) -> int:
    """Hoja de la agencia: cabecera, renglones numerados en pesos y USD, TOTAL y FOR YOUR ACCOUNT. Devuelve la ultima fila usada."""
    b = s["buque"]
    dolar = s["dolar"]["valor"] or 0.0
    # cabecera (las celdas conservan su formato)
    h.poner("D2", b["trn"] or None)
    h.poner("E2", ("ENTRADA  " + b["sitio"]).strip())
    h.poner("F2", fecha_larga(b["amarre"]))
    h.poner("H2", "CAMBIO")
    h.poner("I2", None)
    h.unir("H2:I2")
    h.poner("H3", dolar or None)
    h.poner("I3", None)
    h.unir("H3:I3")
    h.poner("C3", f"CARGA: {b.get('carga') or ''} SHIPPER: {b.get('shipper') or ''}".rstrip())
    cant = parse_number(b["cantidad"]) if b["cantidad"] else None
    if cant is not None:
        h.poner("D3", cant)
    elif b["cantidad"]:
        h.poner("D3", b["cantidad"])
    h.poner("F3", fecha_larga(b["zarpe"]))
    detalle = dias.get("detalle") or []
    if len(detalle) > 1:
        h.poner("G3", dias["total"], formula="+".join(format(x, "g") for x in detalle))
    else:
        h.poner("G3", dias.get("total") or None)
    h.poner("C4", f"ESLORA: {b['eslora']:g}" if b["eslora"] else "ESLORA: ")
    h.poner("C13", titulo_buque(b["nombre"]))

    h.vaciar_desde(16)
    lineas = ch["lineas"]
    r0 = 16
    ultima_no_fee = max([i for i, l in enumerate(lineas) if l["clave"] not in ("fee", "law")], default=-1)
    ref_dolar = "$H$3"
    sum_d = sum_e = 0.0
    for i, l in enumerate(lineas):
        r = r0 + i
        for col, est in E_LINEA.items():
            h.poner(f"{col}{r}", None, est)
        h.poner(f"A{r}", l["n"])
        h.poner(f"B{r}", "-")
        h.poner(f"C{r}", l["texto"])
        h.altura(r, 15.6)
        ars, usd = l["ars"], l["usd"]
        if l["clave"] == "law" and not ch["law"]["manual"] and ultima_no_fee >= 0:
            rango = lambda col: f"SUM({col}{r0}:{col}{r0 + ultima_no_fee})*{ch['law']['pct']:g}/100"
            ars = sum(x["ars"] for x in lineas[: ultima_no_fee + 1]) * ch["law"]["pct"] / 100
            usd = sum((x["usd"] or 0.0) for x in lineas[: ultima_no_fee + 1]) * ch["law"]["pct"] / 100
            h.poner(f"D{r}", ars, E_LINEA["D"], formula=rango("D"))
            h.poner(f"E{r}", usd, E_LINEA["E"], formula=rango("E"))
        elif l["moneda"] == "USD":
            h.poner(f"E{r}", l["monto"], E_LINEA["E"])
            if dolar:
                h.poner(f"D{r}", ars, E_LINEA["D"], formula=f"E{r}*{ref_dolar}")
        else:
            h.poner(f"D{r}", l["monto"], E_LINEA["D"])
            if dolar:
                h.poner(f"E{r}", usd, E_LINEA["E"], formula=f"D{r}/{ref_dolar}")
        sum_d += ars or 0.0
        sum_e += usd or 0.0
        h.fondo(r, "F", "J")
    ultima = r0 + len(lineas) - 1
    # fila en blanco y TOTAL
    r = ultima + 1
    for col, est in E_VACIA.items():
        h.poner(f"{col}{r}", None, est)
    h.altura(r, 15.6)
    h.fondo(r, "F", "J")
    total = r + 1
    for col, est in E_TOTAL.items():
        h.poner(f"{col}{total}", None, est)
    h.poner(f"C{total}", "TOTAL")
    if lineas:
        h.poner(f"D{total}", sum_d, E_TOTAL["D"], formula=f"SUM(D{r0}:D{ultima})")
        h.poner(f"E{total}", sum_e, E_TOTAL["E"], formula=f"SUM(E{r0}:E{ultima})")
    h.altura(total, 13.8)
    h.fondo(total, "F", "J")
    for k in range(total + 1, total + 7):
        for col, est in (("A", 14), ("B", 53), ("C", 14)):
            h.poner(f"{col}{k}", None, est)
        h.fondo(k, "D", "J")
    # FOR YOUR ACCOUNT: lo que no se factura, con su importe en pesos y en USD
    fya = total + 7
    for col, est in E_PIE_TITULO.items():
        h.poner(f"{col}{fya}", None, est)
    h.poner(f"C{fya}", "FOR YOUR ACCOUNT")
    h.fondo(fya, "D", "J")
    k = fya
    for l in ch["ajenas"]:
        k += 1
        h.poner(f"C{k}", l["texto"], 14)
        h.poner(f"D{k}", l["ars"], E_LINEA["D"])
        h.poner(f"E{k}", l["usd"], E_LINEA["E"])
        nota = "LDS" if "(LDS)" in l["texto"] else ("* sin impuestos" if l["clave"] in ("port_dues", "channel_toll", "anchor") else "")
        h.poner(f"F{k}", nota or None, FONDO)
        h.fondo(k, "A", "J")
    for t in ch["pie"]:
        k += 1
        h.poner(f"C{k}", t, 14)
        h.fondo(k, "A", "J")
    # la imagen del pie va debajo de todo
    fila_img = k + 4
    h.libro.imagen_pie(fila_img)  # base 0 -> queda en la fila (fila_img + 1) de Excel
    fin = fila_img + 9
    for rr in range(total + 7 + 1, fin + 1):
        h.fondo(rr, "A", "J")
    h.dimension(f"A1:K{fin}")
    h.sin_seleccion()
    return fin


# ------------------------------------------------------------------------------------------------------------------------- TALLY
TIER_TALLY = [("H", "BASICO", "h"), ("100", "EXTRA 100%", 100), ("150", "EXTRA 150%", 150), ("F3", "FERIADO x3", 300)]


def _tally(h: Hoja, s: dict, tally: dict, nombre_buque: str, dolar: float) -> None:
    """Hoja TALLY: 'WAGES AT' por escalon (cantidad x valor), cargas sociales, total en pesos y USD, y los turnos a la derecha."""
    h.vaciar_desde(6)
    h.columnas([(1, 1, 14.89), (2, 3, 8.43), (4, 4, 11), (5, 5, 18), (6, 6, 21), (7, 7, 16), (8, 8, 7.78)])  # anchos para importes de millones de pesos
    h.poner("D6", nombre_buque, 96)
    h.poner("E6", None, 96)
    h.poner("F6", None, 96)
    h.unir("D6:F6")
    resumen = {r["nivel"]: r for r in tally["resumen"]}
    r = 8
    primero = r
    for nivel, etiqueta, _cod in TIER_TALLY:
        x = resumen[nivel]
        fila_est = 11 if nivel == "F3" else 8
        h.poner(f"C{r}", x["cantidad"], 4)
        h.poner(f"D{r}", "WAGES AT", 4)
        h.poner(f"E{r}", x["precio"], 7)
        h.poner(f"F{r}", x["cantidad"] * x["precio"], fila_est, formula=f"C{r}*E{r}")
        h.poner(f"G{r}", etiqueta, 4)
        r += 1
    ultimo = r - 1
    pct = s["agencia"]["tally_pct"] / 100
    h.poner(f"E{r}", None, 8)
    suma = sum(x["cantidad"] * x["precio"] for x in resumen.values())
    h.poner(f"F{r}", suma, 8, formula=f"SUM(F{primero}:F{ultimo})")
    fila_suma = r
    r += 1
    h.poner(f"E{r}", pct, 9)
    h.poner(f"F{r}", suma * pct, 12, formula=f"F{fila_suma}*E{r}")
    fila_pct = r
    r += 1
    h.poner(f"F{r}", suma + suma * pct, 6, formula=f"SUM(F{fila_suma}:F{fila_pct})")
    fila_total = r
    # USD, con el dolar unico
    r += 2
    usd_est = h.libro.estilo_con_numfmt(6, 15)
    h.poner(f"D{r}", "CAMBIO", 4)
    h.poner(f"E{r}", dolar or None, 7)
    r += 1
    h.poner(f"D{r}", "TOTAL USD", 4)
    if dolar:
        h.poner(f"F{r}", (suma + suma * pct) / dolar, usd_est, formula=f"F{fila_total}/E{r - 1}")
    # turnos (a la derecha): fecha, horario y escalon
    rr = 6
    ultima_fecha = None
    for f in tally["filas"]:
        rojo = f["nivel"] in ("150", "F3")
        cod = next(c for n, _e, c in TIER_TALLY if n == f["nivel"])
        if f["fecha"] != ultima_fecha:
            h.poner(f"I{rr}", date.fromisoformat(f["fecha"]), 133 if rojo else 86)
            ultima_fecha = f["fecha"]
        h.poner(f"J{rr}", f"{f['turno'][:2]}00-{f['turno'][3:]}00", 134 if rojo else 68)
        h.poner(f"K{rr}", cod, 135 if rojo else 26)
        rr += 1
    h.dimension(f"A1:K{max(r, rr)}")
    h.sin_seleccion()


# ----------------------------------------------------------------------------------------------------------------------- SERENOS
VENT_EST = {"00-06": (119, 120, 121), "06-12": (122, 120, 121), "12-18": (126, 127, 128), "18-24": (119, 120, 121)}


def _serenos(h: Hoja, s: dict, serenos: dict, nombre_buque: str, dolar: float, feriados: set[str]) -> None:
    """Hoja SERENOS: grilla de turnos x dias (en pesos), subtotal, cargas sociales, viaticos y total en pesos y en USD, y el detalle de quien cubrio cada turno."""
    h.vaciar_desde(5)
    filas = serenos["filas"]
    fechas = sorted({f["fecha"] for f in filas})
    ncols = max(4, len(fechas))
    c_dia0 = 5                      # E
    c_total = c_dia0 + ncols         # columna del TOTAL
    c_label = c_total - 1
    L = letra
    # anchos de columna
    h.columnas([(1, 1, 1.66), (2, 2, 7), (3, 3, 20), (4, 4, 12), (c_dia0, c_total, 17)], estilo=4)
    # titulo
    h.poner("F5", nombre_buque, 96)
    h.poner("G5", None, 96)
    h.unir("F5:G5")
    h.altura(8, 18)
    rojos = [date.fromisoformat(f).weekday() >= 5 or f in feriados for f in fechas]
    h.poner("C8", None, 16)
    h.poner("D8", "TURNO", 17)
    for k in range(ncols):
        col = L(c_dia0 + k)
        if k < len(fechas):
            d = date.fromisoformat(fechas[k])
            h.poner(f"{col}8", d, 132 if rojos[k] else 16)
        else:
            h.poner(f"{col}8", None, 16)
    h.poner(f"{L(c_total)}8", "TOTAL", 88)
    # grilla: 4 turnos de 3 filas
    por_celda: dict[tuple[str, str], float] = {}
    nombres: dict[tuple[str, str], list[str]] = {}
    for f in filas:
        k = (f["fecha"], f["ventana"])
        por_celda[k] = por_celda.get(k, 0.0) + f["total"]
        if f.get("nombre"):
            nombres.setdefault(k, []).append(f["nombre"])
    r0 = 9
    for b, v in enumerate(("00-06", "06-12", "12-18", "18-24")):
        ra = r0 + 3 * b
        quienes = []
        for fch in fechas:
            for n in nombres.get((fch, v), []):
                if n not in quienes:
                    quienes.append(n)
        est_n, est_t = (97, 98, 99), VENT_EST[v]
        for i in range(3):
            h.poner(f"C{ra + i}", None, est_n[i])
            h.poner(f"D{ra + i}", None, est_t[i])
        h.poner(f"C{ra}", " / ".join(quienes) if quienes else None)
        h.poner(f"D{ra}", v)
        h.unir(f"C{ra}:C{ra + 2}")
        h.unir(f"D{ra}:D{ra + 2}")
        for k in range(ncols):
            col = L(c_dia0 + k)
            monto = por_celda.get((fechas[k], v)) if k < len(fechas) else None
            est = ((112, 113, 114) if rojos[k] else (106, 107, 108)) if monto else (100, 101, 102)
            for i in range(3):
                h.poner(f"{col}{ra + i}", None, est[i])
            if monto:
                h.poner(f"{col}{ra}", monto)
            h.unir(f"{col}{ra}:{col}{ra + 2}")
        tot = sum(por_celda.get((fch, v), 0.0) for fch in fechas)
        for i in range(3):
            h.poner(f"{L(c_total)}{ra + i}", None, (103, 104, 105)[i])
        h.poner(f"{L(c_total)}{ra}", tot, formula=f"SUM({L(c_dia0)}{ra}:{L(c_label)}{ra + 2})")
        h.unir(f"{L(c_total)}{ra}:{L(c_total)}{ra + 2}")
    # bloques de la derecha: SUBT, cargas sociales, viaticos, TOTAL, y los mismos en USD
    sub = sum(por_celda.values())
    pct = s["agencia"]["serenos_pct"] / 100
    viat = serenos["viatico"]["total"] if serenos["viatico"]["tipo"] else 0.0
    lc, vc = L(c_label), L(c_total)
    usd_blocks = h.libro.estilo_con_numfmt(103, 15), h.libro.estilo_con_numfmt(104, 15), h.libro.estilo_con_numfmt(105, 15)
    num2 = h.libro.estilo_con_numfmt(103, 4), h.libro.estilo_con_numfmt(104, 4), h.libro.estilo_con_numfmt(105, 4)

    def bloque(ini, etiqueta, valor, formula, est_etiqueta=(115, 116, 117), est_valor=(103, 104, 105)):
        for i in range(3):
            h.poner(f"{lc}{ini + i}", None, est_etiqueta[i])
            h.poner(f"{vc}{ini + i}", None, est_valor[i])
        h.poner(f"{lc}{ini}", etiqueta, est_etiqueta[0])
        h.poner(f"{vc}{ini}", valor, est_valor[0], formula=formula)
        h.unir(f"{lc}{ini}:{lc}{ini + 2}")
        h.unir(f"{vc}{ini}:{vc}{ini + 2}")

    ini = r0 + 12  # 21
    bloque(ini, "SUBT", sub, f"SUM({vc}{r0}:{vc}{ini - 1})")
    bloque(ini + 3, pct, sub * pct, f"{vc}{ini}*{lc}{ini + 3}", est_etiqueta=(109, 110, 111))
    conv = serenos["viatico"]["unit"] * serenos["viatico"]["cantidad"] if serenos["viatico"]["tipo"] else 0.0
    cant_txt = f"{serenos['viatico']['cantidad']}*{serenos['viatico']['unit']:.2f}"
    bloque(ini + 6, "CONV.", conv, cant_txt if conv else None)
    total = sub + sub * pct + conv
    bloque(ini + 9, "TOTAL", total, f"SUM({vc}{ini}:{vc}{ini + 8})", est_etiqueta=(109, 110, 111))
    bloque(ini + 12, "CAMBIO", dolar or None, None, est_valor=num2)
    if dolar:
        bloque(ini + 15, "TOTAL USD", total / dolar, f"{vc}{ini + 9}/{vc}{ini + 12}", est_valor=usd_blocks)
    # quien cubrio cada turno, por dia (a la izquierda, debajo de la grilla)
    k = ini + 2
    h.poner(f"D{k}", ": " + nombre_buque.replace("MV ", "", 1), 66)
    k += 1
    h.poner(f"D{k}", "SEA WHITE", 4)
    k += 1
    if s["buque"]["sitio"]:
        h.poner(f"D{k}", s["buque"]["sitio"].upper(), 4)
        k += 1
    for fch in fechas:
        h.poner(f"D{k}", date.fromisoformat(fch), 72)
        k += 1
        for f in filas:
            if f["fecha"] != fch:
                continue
            a, bb = f["ventana"].split("-")
            h.poner(f"D{k}", f"{a} A {bb}" + (f": {f['nombre']}" if f.get("nombre") else ""), 4)
            k += 1
    fin = max(k, ini + 18) + 1
    for rr in range(1, fin + 1):
        h.fondo(rr, "A", L(c_total + 1))
    h.dimension(f"C1:{L(c_total + 1)}{fin}")
    h.sin_seleccion()


# ------------------------------------------------------------------------------------------------------------------------- armado
def generar(s: dict, ch: dict, tally: dict, serenos: dict, dias: dict, feriados: set[str], filas_resumen: list[list], filas_estado: list[list]) -> bytes:
    """El libro completo: hoja de la agencia, SERENOS, TALLY y las dos hojas ocultas (_estado y _resumen)."""
    lib = Libro()
    principal, hoja_ser, hoja_tal = lib.hoja(1), lib.hoja(2), lib.hoja(3)
    lib.renombrar(1, nombre_hoja(s["agencia"]["nombre"]))
    lib.renombrar(2, "SERENOS")
    lib.renombrar(3, "TALLY")
    dolar = s["dolar"]["valor"] or 0.0
    titulo = titulo_buque(s["buque"]["nombre"])
    _principal(principal, s, ch, dias)
    _serenos(hoja_ser, s, serenos, titulo, dolar, feriados)
    _tally(hoja_tal, s, tally, titulo, dolar)
    lib.agregar_hoja_oculta("_resumen", filas_resumen)
    lib.agregar_hoja_oculta("_estado", filas_estado)
    return lib.to_bytes()
