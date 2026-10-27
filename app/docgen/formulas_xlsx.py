"""Solapa FORMULAS del Excel de la proforma final: cada importe de la proforma explicado paso a paso (control interno).

Para cada concepto: de donde salen los datos (con el paso en que se cargaron), la cuenta renglon por renglon y el importe que queda
en la proforma. Los datos van en azul, las cuentas en gris y el resultado en verde. Las cuentas son FORMULAS vivas que apuntan a los datos de
esta misma hoja (con su valor guardado para Vista protegida). Si un importe de la proforma se modifico a mano, la hoja lo marca en rojo con la
diferencia contra el calculo. Al final: todos los renglones, el total y un control contra el total de la hoja de la agencia.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime

from lxml import etree

from .xlsx_fill import M, NS_CT, NS_MAIN, NS_PKG_REL

NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SALIDA = {"xml_declaration": True, "encoding": "UTF-8", "standalone": True}
DIAS_ES = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
ANCHOS = [(1, 2.5), (2, 50), (3, 25), (4, 13), (5, 92)]  # columnas A (margen), B etiqueta, C valor, D unidad, E explicacion


# ------------------------------------------------------------------------------------------------------------------ estilos
# clave: (negrita, cursiva, tamaño, color, relleno, borde_abajo, formato_numero, alineacion_horizontal, vertical, ajustar_texto)
ESTILOS = {
    "titulo": (True, False, 16, "1F3864", None, False, None, "left", "center", False),
    "sub": (False, True, 10, "595959", None, False, None, "left", "top", True),
    "banda": (True, False, 12, "FFFFFF", "1F4E79", False, None, "left", "center", False),
    "banda_ajena": (True, False, 12, "FFFFFF", "7F6000", False, None, "left", "center", False),
    "banda_total": (True, False, 12, "FFFFFF", "375623", False, None, "left", "center", False),
    "et": (False, False, 11, "000000", None, True, None, "left", "center", True),
    "et_b": (True, False, 11, "000000", None, True, None, "left", "center", True),
    "dato2": (False, False, 11, "0000FF", None, True, "#,##0.00", "right", "center", False),
    "dato4": (False, False, 11, "0000FF", None, True, "#,##0.0000", "right", "center", False),
    "dato0": (False, False, 11, "0000FF", None, True, "#,##0", "right", "center", False),
    "datotxt": (False, False, 11, "0000FF", None, True, None, "right", "center", False),
    "cuenta2": (True, False, 11, "404040", "F2F2F2", True, "#,##0.00", "right", "center", False),
    "cuenta4": (True, False, 11, "404040", "F2F2F2", True, "#,##0.0000", "right", "center", False),
    "res_et": (True, False, 12, "1E4620", "E2EFDA", True, None, "left", "center", True),
    "res2": (True, False, 12, "1E4620", "E2EFDA", True, "#,##0.00", "right", "center", False),
    "unidad": (False, False, 10, "7F7F7F", None, True, None, "center", "center", False),
    "unidad_res": (True, False, 10, "1E4620", "E2EFDA", True, None, "center", "center", False),
    "origen": (False, False, 10, "595959", None, True, None, "left", "center", True),
    "origen_res": (False, False, 10, "1E4620", "E2EFDA", True, None, "left", "center", True),
    "nota": (False, True, 10, "7F6000", "FFF8E1", False, None, "left", "top", True),
    "aviso": (True, False, 11, "C00000", "FDE9E7", False, None, "left", "top", True),
    "aviso_num": (True, False, 11, "C00000", "FDE9E7", True, "#,##0.00", "right", "center", False),
    "aviso_et": (True, False, 11, "C00000", "FDE9E7", True, None, "left", "center", True),
    "hdr": (True, False, 10, "404040", "D9D9D9", False, None, "center", "center", True),
    "tot_et": (True, False, 12, "000000", "D9E1F2", True, None, "left", "center", True),
    "tot2": (True, False, 12, "000000", "D9E1F2", True, "#,##0.00", "right", "center", False),
    "ok": (True, False, 12, "1E4620", "E2EFDA", True, None, "left", "center", True),
    "mal": (True, False, 12, "C00000", "FDE9E7", True, None, "left", "center", True),
    "num_simple": (False, False, 11, "000000", None, True, "#,##0.00", "right", "center", False),
}


def registrar_estilos(lib) -> dict[str, int]:
    """Agrega los estilos de esta hoja al styles.xml del libro y devuelve {clave: indice de cellXfs}."""
    st = etree.fromstring(lib.parts["xl/styles.xml"])
    fonts, fills, borders, xfs = (st.find(M + n) for n in ("fonts", "fills", "borders", "cellXfs"))
    numfmts = st.find(M + "numFmts")
    if numfmts is None:
        numfmts = etree.Element(M + "numFmts")
        st.insert(0, numfmts)
    usados = {nf.get("formatCode"): int(nf.get("numFmtId")) for nf in numfmts}
    proximo = max([int(nf.get("numFmtId")) for nf in numfmts] + [199]) + 1
    cache_f, cache_r, cache_b = {}, {}, {}
    out = {}
    for clave, (neg, curs, tam, color, relleno, borde, fmt, h, v, wrap) in ESTILOS.items():
        kf = (neg, curs, tam, color)
        if kf not in cache_f:
            f = etree.SubElement(fonts, M + "font")
            if neg:
                etree.SubElement(f, M + "b")
            if curs:
                etree.SubElement(f, M + "i")
            etree.SubElement(f, M + "sz").set("val", str(tam))
            etree.SubElement(f, M + "color").set("rgb", "FF" + color)
            etree.SubElement(f, M + "name").set("val", "Segoe UI")
            cache_f[kf] = len(fonts) - 1
        if relleno not in cache_r:
            fl = etree.SubElement(fills, M + "fill")
            if relleno:
                pf = etree.SubElement(fl, M + "patternFill", patternType="solid")
                etree.SubElement(pf, M + "fgColor").set("rgb", "FF" + relleno)
                etree.SubElement(pf, M + "bgColor").set("indexed", "64")
            else:
                etree.SubElement(fl, M + "patternFill", patternType="none")
            cache_r[relleno] = len(fills) - 1
        if borde not in cache_b:
            b = etree.SubElement(borders, M + "border")
            for lado in ("left", "right", "top"):
                etree.SubElement(b, M + lado)
            bot = etree.SubElement(b, M + "bottom")
            if borde:
                bot.set("style", "thin")
                etree.SubElement(bot, M + "color").set("rgb", "FFD0D0D0")
            etree.SubElement(b, M + "diagonal")
            cache_b[borde] = len(borders) - 1
        if fmt and fmt not in usados:
            etree.SubElement(numfmts, M + "numFmt", numFmtId=str(proximo), formatCode=fmt)
            usados[fmt] = proximo
            proximo += 1
        xf = etree.SubElement(xfs, M + "xf", numFmtId=str(usados.get(fmt, 0)), fontId=str(cache_f[kf]), fillId=str(cache_r[relleno]),
                              borderId=str(cache_b[borde]), xfId="0", applyFont="1", applyFill="1", applyBorder="1", applyAlignment="1")
        if fmt:
            xf.set("applyNumberFormat", "1")
        al = etree.SubElement(xf, M + "alignment", horizontal=h, vertical=v)
        if wrap:
            al.set("wrapText", "1")
        out[clave] = len(xfs) - 1
    for el in (fonts, fills, borders, xfs, numfmts):
        el.set("count", str(len(el)))
    lib.parts["xl/styles.xml"] = etree.tostring(st, **SALIDA)
    return out


# ------------------------------------------------------------------------------------------------------------------ utilidades
def es(n: float, d: int = 2) -> str:
    """1234567.891 -> '1.234.567,89'."""
    return f"{n:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fecha_hora(iso: str) -> str:
    try:
        d = datetime.strptime(str(iso), "%Y-%m-%dT%H:%M")
        return f"{DIAS_ES[d.weekday()]} {d:%d/%m/%Y %H:%M}"
    except ValueError:
        return str(iso or "—")


def fecha_dia(iso: str) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{DIAS_ES[d.weekday()]} {d:%d/%m/%Y}"
    except ValueError:
        return str(iso or "")


def _redondear(x: float, n: int = 0) -> float:
    """ROUND de Excel (la mitad se va para arriba, en valor absoluto)."""
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(format(float(x), ".15g")).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))  # Excel redondea sobre 15 cifras significativas


def letra(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Ex:
    """Arma las filas de la hoja. Columnas: B etiqueta, C valor, D unidad (o 2do valor), E explicacion."""

    def __init__(self, estilos: dict[str, int]):
        self.st = estilos
        self.filas: dict[int, list] = {}
        self.altos: dict[int, float] = {}
        self.uniones: list[str] = []
        self.r = 1
        self.res: dict[str, dict] = {}   # clave del renglon -> {"usd": fila, "ars": fila, ...}
        self.cache: dict[str, float | str] = {}

    # --- bajo nivel
    def _c(self, fila: int, col: str, valor=None, formula: str | None = None, estilo: str = "et"):
        self.filas.setdefault(fila, []).append((col, valor, formula, self.st[estilo]))

    def _avanzar(self) -> int:
        fila = self.r
        self.r += 1
        return fila

    def _alto_texto(self, fila: int, texto: str, ancho: int = 100, base: float = 15.0) -> None:
        lineas = max(1, math.ceil(len(texto) / ancho) + texto.count("\n"))
        if lineas > 1:
            self.altos[fila] = base * lineas

    # --- bloques de la hoja
    def titulo(self, texto: str) -> int:
        f = self._avanzar()
        self._c(f, "B", texto, estilo="titulo")
        self.altos[f] = 26
        return f

    def sub(self, texto: str) -> int:
        f = self._avanzar()
        self._c(f, "B", texto, estilo="sub")
        for c in "CDE":
            self._c(f, c, None, estilo="sub")
        self.uniones.append(f"B{f}:E{f}")
        self._alto_texto(f, texto, 120, 14)
        return f

    def espacio(self, n: int = 1) -> None:
        self.r += n

    def banda(self, texto: str, estilo: str = "banda") -> int:
        f = self._avanzar()
        for c in "BCDE":
            self._c(f, c, texto if c == "B" else None, estilo=estilo)
        self.uniones.append(f"B{f}:E{f}")
        self.altos[f] = 22
        return f

    def encabezados(self, *textos: str) -> int:
        f = self._avanzar()
        for c, t in zip("BCDE", textos):
            self._c(f, c, t, estilo="hdr")
        return f

    def dato(self, etiqueta: str, valor, unidad: str = "", origen: str = "", fmt: str = "2") -> int:
        f = self._avanzar()
        self._c(f, "B", etiqueta, estilo="et")
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            self._c(f, "C", float(valor), estilo=f"dato{fmt}")
            self.cache[f"C{f}"] = float(valor)
        else:
            self._c(f, "C", str(valor), estilo="datotxt")
        self._c(f, "D", unidad, estilo="unidad")
        self._c(f, "E", origen, estilo="origen")
        self._alto_texto(f, origen, 75)
        return f

    def ev(self, formula: str) -> float:
        """Valor de una formula de esta hoja (referencias a la columna C, + - * / ^, ROUND, SUM, MAX, MIN, ABS) para guardarlo junto a la formula."""
        def celda(m):
            return repr(float(self.cache.get(f"C{m.group(1)}", 0.0)))

        def rango(m):
            a, b = int(m.group(1)), int(m.group(2))
            return "(" + ",".join(repr(float(self.cache.get(f"C{i}", 0.0))) for i in range(a, b + 1)) + ",)"

        expr = re.sub(r"\$?C\$?(\d+):\$?C\$?(\d+)", rango, formula)
        expr = re.sub(r"\$?C\$?(\d+)", celda, expr).replace("^", "**")
        return float(eval(expr, {"__builtins__": {}}, {"ROUND": _redondear, "SUM": lambda *a: sum(sum(x) if isinstance(x, tuple) else x for x in a),
                                                        "MAX": max, "MIN": min, "ABS": abs}))

    def cuenta(self, etiqueta: str, formula: str, unidad: str = "", texto: str = "", fmt: str = "2", valor: float | None = None) -> int:
        f = self._avanzar()
        valor = self.ev(formula) if valor is None else valor
        self._c(f, "B", etiqueta, estilo="et_b")
        self._c(f, "C", valor, formula, f"cuenta{fmt}")
        self.cache[f"C{f}"] = valor
        self._c(f, "D", unidad, estilo="unidad")
        self._c(f, "E", texto, estilo="origen")
        self._alto_texto(f, texto, 75)
        return f

    def resultado(self, etiqueta: str, formula: str, unidad: str = "", texto: str = "") -> int:
        f = self._avanzar()
        valor = self.ev(formula)
        self._c(f, "B", etiqueta, estilo="res_et")
        self._c(f, "C", valor, formula, "res2")
        self.cache[f"C{f}"] = valor
        self._c(f, "D", unidad, estilo="unidad_res")
        self._c(f, "E", texto, estilo="origen_res")
        self._alto_texto(f, texto, 75)
        return f

    def nota(self, texto: str, estilo: str = "nota") -> int:
        f = self._avanzar()
        self._c(f, "B", texto, estilo=estilo)
        for c in "CDE":
            self._c(f, c, None, estilo=estilo)
        self.uniones.append(f"B{f}:E{f}")
        self._alto_texto(f, texto, 125, 15)
        return f

    def aviso(self, texto: str) -> int:
        return self.nota(texto, "aviso")

    def aviso_dato(self, etiqueta: str, valor: float, unidad: str = "", texto: str = "") -> int:
        f = self._avanzar()
        self._c(f, "B", etiqueta, estilo="aviso_et")
        self._c(f, "C", valor, estilo="aviso_num")
        self.cache[f"C{f}"] = valor
        self._c(f, "D", unidad, estilo="unidad")
        self._c(f, "E", texto, estilo="origen")
        self._alto_texto(f, texto, 75)
        return f

    # --- cierre de un renglon de la proforma
    def cierre(self, clave, moneda: str, fila_calc: int, usado: float, fila_dolar: int, fila_dolar_propio: int | None = None) -> None:
        """Importe que queda en la proforma (si fue modificado a mano, lo marca) y su pasaje a la otra moneda."""
        valor_calc = self.cache[f"C{fila_calc}"]
        base_fila = fila_calc
        dif = usado - valor_calc
        if 0.0001 < abs(dif) <= 0.015:
            base_fila = self.dato("Importe que figura en la proforma", usado, moneda, "Difiere en un centavo de la cuenta: es redondeo (el sistema y Excel no redondean igual). Se usa este.")
        elif abs(dif) > 0.015:
            self.aviso(f"ATENCIÓN: el importe que figura en la proforma ({es(usado)}) NO coincide con el que da la cuenta ({es(valor_calc)}). "
                       "Se modificó a mano (o cambió algún dato después). Revisalo.")
            f_us = self.aviso_dato("Importe que figura en la proforma", usado, moneda, "Es el que se usó en la hoja de la agencia y en los totales.")
            self.aviso_dato("Diferencia contra la cuenta", usado - valor_calc, moneda, "Proforma menos cuenta (negativo = la proforma tiene menos).")
            base_fila = f_us
        res = self.resultado("IMPORTE EN LA PROFORMA", f"ROUND(C{base_fila},2)", moneda, "Es el número que figura en la hoja de la agencia.")
        if moneda == "USD":
            tasa_fila = fila_dolar_propio or fila_dolar
            otro = self.cuenta("En pesos", f"C{res}*$C${tasa_fila}", "ARS", f"{es(self.cache[f'C{res}'])} × {es(self.cache[f'C{tasa_fila}'], 2)} (dólar{' del fee' if fila_dolar_propio else ''})")
        else:
            otro = self.cuenta("En dólares", f"C{res}/$C${fila_dolar}", "USD", f"{es(self.cache[f'C{res}'])} ÷ {es(self.cache[f'C{fila_dolar}'], 2)} (dólar)")
        self.res[clave] = {moneda.lower(): res, ("ars" if moneda == "USD" else "usd"): otro}
        self.espacio()

    # --- XML
    def xml(self, anchos: list[tuple[int, float]]) -> bytes:
        ws = etree.Element(M + "worksheet", nsmap={None: NS_MAIN, "r": NS_R})
        ult = max(self.filas) if self.filas else 1
        etree.SubElement(etree.SubElement(ws, M + "sheetPr"), M + "pageSetUpPr", fitToPage="1")  # al imprimir entra a lo ancho de una hoja
        etree.SubElement(ws, M + "dimension", ref=f"B1:E{ult}")
        sv = etree.SubElement(etree.SubElement(ws, M + "sheetViews"), M + "sheetView", showGridLines="0", workbookViewId="0", zoomScale="100")
        etree.SubElement(ws, M + "sheetFormatPr", defaultRowHeight="16")
        cols = etree.SubElement(ws, M + "cols")
        for i, w in anchos:
            etree.SubElement(cols, M + "col", min=str(i), max=str(i), width=str(w), customWidth="1")
        sd = etree.SubElement(ws, M + "sheetData")
        for n in sorted(self.filas):
            row = etree.SubElement(sd, M + "row", r=str(n))
            if n in self.altos:
                row.set("ht", str(self.altos[n]))
                row.set("customHeight", "1")
            for col, valor, formula, estilo in sorted(self.filas[n], key=lambda x: x[0]):
                c = etree.SubElement(row, M + "c", r=f"{col}{n}", s=str(estilo))
                if formula is not None:
                    etree.SubElement(c, M + "f").text = formula
                    if isinstance(valor, str):
                        c.set("t", "str")
                        etree.SubElement(c, M + "v").text = valor
                    elif valor is not None:
                        etree.SubElement(c, M + "v").text = format(float(valor), ".15g")
                elif isinstance(valor, bool):
                    c.set("t", "b")
                    etree.SubElement(c, M + "v").text = "1" if valor else "0"
                elif isinstance(valor, (int, float)):
                    etree.SubElement(c, M + "v").text = format(float(valor), ".15g")
                elif isinstance(valor, str) and valor != "":
                    c.set("t", "inlineStr")
                    t = etree.SubElement(etree.SubElement(c, M + "is"), M + "t")
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    t.text = re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f]", "", valor)
        if self.uniones:
            mc = etree.SubElement(ws, M + "mergeCells", count=str(len(self.uniones)))
            for u in self.uniones:
                etree.SubElement(mc, M + "mergeCell", ref=u)
        etree.SubElement(ws, M + "pageMargins", left="0.4", right="0.4", top="0.5", bottom="0.5", header="0.3", footer="0.3")
        etree.SubElement(ws, M + "pageSetup", paperSize="9", orientation="landscape", fitToWidth="1", fitToHeight="0")
        return etree.tostring(ws, **SALIDA)


def agregar_hoja(lib, nombre: str, xml: bytes) -> None:
    """Suma una hoja VISIBLE al final de las hojas del libro (antes de las ocultas hay que llamarla primero)."""
    usados = [int(m.group(1)) for n in lib.parts for m in [re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", n)] if m]
    k = max(usados) + 1
    ruta = f"xl/worksheets/sheet{k}.xml"
    lib.parts[ruta] = xml
    lib.order.append(ruta)
    ct = etree.fromstring(lib.parts["[Content_Types].xml"])
    etree.SubElement(ct, "{%s}Override" % NS_CT, PartName="/" + ruta, ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    lib.parts["[Content_Types].xml"] = etree.tostring(ct, **SALIDA)
    rels = etree.fromstring(lib.parts["xl/_rels/workbook.xml.rels"])
    rid = "rId" + str(max([int(re.sub(r"\D", "", r.get("Id")) or 0) for r in rels] + [0]) + 1)
    etree.SubElement(rels, "{%s}Relationship" % NS_PKG_REL, Id=rid, Type=NS_R + "/worksheet", Target=f"worksheets/sheet{k}.xml")
    lib.parts["xl/_rels/workbook.xml.rels"] = etree.tostring(rels, **SALIDA)
    wb = etree.fromstring(lib.parts["xl/workbook.xml"])
    sheets = wb.find(M + "sheets")
    sid = max(int(s.get("sheetId")) for s in sheets) + 1
    el = etree.SubElement(sheets, M + "sheet", name=nombre, sheetId=str(sid))
    el.set("{%s}id" % NS_R, rid)
    lib.parts["xl/workbook.xml"] = etree.tostring(wb, **SALIDA)
