"""Completa plantillas .xlsx editando solo el XML de la hoja.

No se usa openpyxl a proposito: al reabrir y guardar pierde lineas, grupos
e imagenes EMF de las plantillas. Aca solo se tocan las celdas indicadas, y
todo lo demas (formato, imagenes, impresion) queda byte a byte como estaba.
"""
from __future__ import annotations

import copy
import io
import re
import zipfile
from datetime import date
from pathlib import Path

from lxml import etree
from PIL import Image

from .fechas import excel_serial

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
M = "{%s}" % NS_MAIN
EMU_PER_PT = 12700

SHEET = "xl/worksheets/sheet1.xml"


def _col_idx(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def _split(ref: str) -> tuple[str, int]:
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"celda invalida: {ref}")
    return m.group(1), int(m.group(2))


class Xlsx:
    def __init__(self, path: Path):
        with zipfile.ZipFile(path) as z:
            self.order = z.namelist()
            self.parts: dict[str, bytes] = {n: z.read(n) for n in self.order}
        self.root = etree.fromstring(self.parts[SHEET])
        self.sheet_data = self.root.find(M + "sheetData")

    # ------------------------------------------------------------ celdas --
    def _row(self, n: int):
        prev = None
        for row in self.sheet_data.findall(M + "row"):
            r = int(row.get("r"))
            if r == n:
                return row
            if r > n:
                break
            prev = row
        new = etree.Element(M + "row", r=str(n))
        if prev is None:
            self.sheet_data.insert(0, new)
        else:
            prev.addnext(new)
        return new

    def _cell(self, ref: str):
        col, rown = _split(ref)
        row = self._row(rown)
        idx = _col_idx(col)
        prev = None
        for c in row.findall(M + "c"):
            ccol, _ = _split(c.get("r"))
            ci = _col_idx(ccol)
            if ci == idx:
                return c
            if ci > idx:
                break
            prev = c
        new = etree.Element(M + "c", r=ref)
        if prev is None:
            row.insert(0, new)
        else:
            prev.addnext(new)
        return new

    @staticmethod
    def _wipe(c, keep_formula: bool = False) -> None:
        for child in list(c):
            if keep_formula and child.tag == M + "f":
                continue
            c.remove(child)
        if "t" in c.attrib:
            del c.attrib["t"]

    def set_text(self, ref: str, text: str | None) -> None:
        c = self._cell(ref)
        self._wipe(c)
        text = "" if text is None else str(text)
        if text == "":
            return
        c.set("t", "inlineStr")
        is_ = etree.SubElement(c, M + "is")
        t = etree.SubElement(is_, M + "t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text

    def set_number(self, ref: str, value: int | float) -> None:
        c = self._cell(ref)
        self._wipe(c)
        v = etree.SubElement(c, M + "v")
        v.text = repr(value) if isinstance(value, float) else str(value)

    def set_value(self, ref: str, value) -> None:
        """Numero si se puede leer como numero, si no texto (buque sin TRN, etc.)."""
        from .fechas import parse_number

        if isinstance(value, (int, float)):
            self.set_number(ref, value)
            return
        n = parse_number(value or "")
        if n is None:
            self.set_text(ref, value)
        else:
            self.set_number(ref, n)

    def set_date(self, ref: str, d: date | None) -> None:
        if d is None:
            self.set_text(ref, "")
        else:
            self.set_number(ref, excel_serial(d))

    def set_numfmt(self, ref: str, num_fmt_id: int) -> None:
        """Le cambia a una celda el formato de numero (por ejemplo 3 = #,##0) sin tocar el resto de su formato."""
        styles = etree.fromstring(self.parts["xl/styles.xml"])
        xfs = styles.find(M + "cellXfs")
        c = self._cell(ref)
        new = copy.deepcopy(xfs[int(c.get("s", "0"))])
        new.set("numFmtId", str(num_fmt_id))
        new.set("applyNumberFormat", "1")
        xfs.append(new)
        xfs.set("count", str(len(xfs)))
        self.parts["xl/styles.xml"] = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
        c.set("s", str(len(xfs) - 1))

    def shrink(self, ref: str) -> None:
        """Si el texto no entra en la celda, se achica solo (en lugar de pasarse del recuadro)."""
        styles = etree.fromstring(self.parts["xl/styles.xml"])
        xfs = styles.find(M + "cellXfs")
        c = self._cell(ref)
        new = copy.deepcopy(xfs[int(c.get("s", "0"))])
        al = new.find(M + "alignment")
        if al is None:
            al = etree.SubElement(new, M + "alignment")
        al.set("shrinkToFit", "1")
        if "wrapText" in al.attrib:
            del al.attrib["wrapText"]
        new.set("applyAlignment", "1")
        xfs.append(new)
        xfs.set("count", str(len(xfs)))
        self.parts["xl/styles.xml"] = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
        c.set("s", str(len(xfs) - 1))

    def merge(self, rng: str) -> None:
        """Une celdas (la hoja ya debe tener otras combinadas)."""
        merges = self.root.find(M + "mergeCells")
        if merges is None:
            raise RuntimeError("la plantilla no tiene celdas combinadas")
        el = etree.SubElement(merges, M + "mergeCell")
        el.set("ref", rng)
        merges.set("count", str(len(merges)))

    def unmerge(self, rng: str) -> None:
        merges = self.root.find(M + "mergeCells")
        if merges is None:
            return
        for el in list(merges):
            if el.get("ref") == rng:
                merges.remove(el)
        if len(merges):
            merges.set("count", str(len(merges)))
        else:
            self.root.remove(merges)

    def blank_row(self, n: int) -> None:
        for c in self._row(n).findall(M + "c"):
            self._wipe(c)

    def show_row(self, n: int, height: float | None = None) -> None:
        """Muestra una fila oculta (y le puede fijar la altura)."""
        row = self._row(n)
        row.attrib.pop("hidden", None)
        if height is not None:
            row.set("ht", str(height))
            row.set("customHeight", "1")

    def set_bottom_border(self, ref: str) -> None:
        """Le agrega una linea fina abajo a la celda, conservando el resto de su formato."""
        styles = etree.fromstring(self.parts["xl/styles.xml"])
        borders = styles.find(M + "borders")
        xfs = styles.find(M + "cellXfs")
        c = self._cell(ref)
        new_xf = copy.deepcopy(xfs[int(c.get("s", "0"))])
        border = copy.deepcopy(borders[int(new_xf.get("borderId", "0"))])
        bottom = border.find(M + "bottom")
        if bottom is None:
            bottom = etree.SubElement(border, M + "bottom")
        bottom.set("style", "thin")
        for ch in list(bottom):
            bottom.remove(ch)
        etree.SubElement(bottom, M + "color", auto="1")
        borders.append(border)
        borders.set("count", str(len(borders)))
        new_xf.set("borderId", str(len(borders) - 1))
        new_xf.set("applyBorder", "1")
        xfs.append(new_xf)
        xfs.set("count", str(len(xfs)))
        self.parts["xl/styles.xml"] = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
        c.set("s", str(len(xfs) - 1))

    def insert_rows(self, at: int, count: int) -> None:
        """Baja `count` filas todo lo que esta desde la fila `at` (celdas, combinadas, imagenes y area de impresion)."""
        for row in self.sheet_data.findall(M + "row"):
            r = int(row.get("r"))
            if r >= at:
                row.set("r", str(r + count))
                for c in row.findall(M + "c"):
                    col, _ = _split(c.get("r"))
                    c.set("r", f"{col}{r + count}")
        merges = self.root.find(M + "mergeCells")
        if merges is not None:
            for el in merges:
                a, b = el.get("ref").split(":")
                (ca, ra), (cb, rb) = _split(a), _split(b)
                if ra >= at:
                    ra += count
                if rb >= at:
                    rb += count
                el.set("ref", f"{ca}{ra}:{cb}{rb}")
        dim = self.root.find(M + "dimension")
        if dim is not None and ":" in dim.get("ref", ""):
            a, b = dim.get("ref").split(":")
            cb, rb = _split(b)
            dim.set("ref", f"{a}:{cb}{rb + count}")
        # imagenes y formas ancladas a celdas
        for name in [n for n in self.parts if n.startswith("xl/drawings/drawing") and n.endswith(".xml")]:
            dr = etree.fromstring(self.parts[name])
            for el in dr.iter("{%s}row" % NS_XDR):
                if int(el.text) >= at - 1:
                    el.text = str(int(el.text) + count)
            self.parts[name] = etree.tostring(dr, xml_declaration=True, encoding="UTF-8", standalone=True)
        # area de impresion
        wbx = self.parts["xl/workbook.xml"].decode("utf-8")

        def bump(m):
            col1, r1, col2, r2 = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            return f"${col1}${r1}:${col2}${r2 + count if r2 >= at else r2}"

        wbx = re.sub(r"\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)", bump, wbx)
        self.parts["xl/workbook.xml"] = wbx.encode("utf-8")

    def copy_style(self, src: str, dst: str) -> None:
        """Le pone a una celda el mismo formato (fecha, alineacion, fuente) que a otra."""
        s = self._cell(src).get("s")
        c = self._cell(dst)
        if s is None:
            c.attrib.pop("s", None)
        else:
            c.set("s", s)

    def set_formula_result(self, ref: str, text: str) -> None:
        """Deja la formula y actualiza su valor guardado (para visores que no recalculan)."""
        c = self._cell(ref)
        for child in list(c):
            if child.tag == M + "v":
                c.remove(child)
        c.set("t", "str")
        v = etree.SubElement(c, M + "v")
        v.text = text

    # ------------------------------------------------------------- logo ---
    def _col_widths_pt(self, c1: int, c2: int) -> list[float]:
        default = 8.43
        fmt = self.root.find(M + "sheetFormatPr")
        if fmt is not None and fmt.get("defaultColWidth"):
            default = float(fmt.get("defaultColWidth"))
        specs = []
        cols = self.root.find(M + "cols")
        if cols is not None:
            for col in cols.findall(M + "col"):
                specs.append((int(col.get("min")), int(col.get("max")), float(col.get("width"))))
        out = []
        for i in range(c1, c2 + 1):
            w = default
            for lo, hi, width in specs:
                if lo <= i <= hi:
                    w = width
                    break
            out.append((w * 7 + 5) * 0.75)
        return out

    def _row_heights_pt(self, r1: int, r2: int) -> list[float]:
        default = 15.0
        fmt = self.root.find(M + "sheetFormatPr")
        if fmt is not None and fmt.get("defaultRowHeight"):
            default = float(fmt.get("defaultRowHeight"))
        heights = {int(r.get("r")): float(r.get("ht")) for r in self.sheet_data.findall(M + "row") if r.get("ht")}
        return [heights.get(i, default) for i in range(r1, r2 + 1)]

    def add_logo(self, data: bytes, mime: str, box: tuple[int, int, int, int],
                 box_w_pt: float, box_h_pt: float, pad_pt: float = 10.0, *,
                 tag: str = "logo_agencia", name: str = "Logo agencia", shape_id: int = 9001,
                 align_x: str = "center", max_h_pt: float | None = None) -> None:
        """Logo centrado dentro de la caja del encabezado (columnas c1..c2, filas r1..r2).

        box_w_pt/box_h_pt son las medidas reales de esa caja (se midieron en Excel);
        con ellas se calibran los anchos calculados del XML.
        """
        c1, r1, c2, r2 = box
        img = Image.open(io.BytesIO(data))
        iw, ih = img.size
        scale = min((box_w_pt - 2 * pad_pt) / iw, (box_h_pt - 2 * pad_pt) / ih)
        if max_h_pt:
            scale = min(scale, max_h_pt / ih)
        w_pt, h_pt = iw * scale, ih * scale
        x_pt = {"left": pad_pt, "right": box_w_pt - w_pt - pad_pt}.get(align_x, (box_w_pt - w_pt) / 2)
        y_pt = (box_h_pt - h_pt) / 2
        rid = "rId" + "".join(ch for ch in tag.title() if ch.isalnum()) + "Img"

        cw = self._col_widths_pt(c1, c2)
        kx = box_w_pt / sum(cw)
        cw = [w * kx for w in cw]
        rh = self._row_heights_pt(r1, r2)
        ky = box_h_pt / sum(rh)
        rh = [h * ky for h in rh]

        def locate(pos: float, sizes: list[float]) -> tuple[int, float]:
            acc = 0.0
            for i, s in enumerate(sizes):
                if pos < acc + s or i == len(sizes) - 1:
                    return i, pos - acc
                acc += s
            return 0, pos

        ci, cx = locate(x_pt, cw)
        ri, ry = locate(y_pt, rh)
        ext = "png" if mime == "image/png" else "jpeg"
        media_name = f"xl/media/{tag}.{ext}"
        self.parts[media_name] = data

        anchor_xml = (
            "<xdr:oneCellAnchor>"
            f"<xdr:from><xdr:col>{c1 - 1 + ci}</xdr:col><xdr:colOff>{int(cx * EMU_PER_PT)}</xdr:colOff>"
            f"<xdr:row>{r1 - 1 + ri}</xdr:row><xdr:rowOff>{int(ry * EMU_PER_PT)}</xdr:rowOff></xdr:from>"
            f'<xdr:ext cx="{int(w_pt * EMU_PER_PT)}" cy="{int(h_pt * EMU_PER_PT)}"/>'
            f'<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="{shape_id}" name="{name}"/>'
            '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
            f'<xdr:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
            f'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{int(w_pt * EMU_PER_PT)}" cy="{int(h_pt * EMU_PER_PT)}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>'
            "<xdr:clientData/></xdr:oneCellAnchor>"
        )
        wrapper = (
            f'<xdr:wsDr xmlns:xdr="{NS_XDR}" xmlns:a="{NS_A}" xmlns:r="{NS_REL}">{anchor_xml}</xdr:wsDr>'
        )
        img_rel = (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
        )
        drawing_path = "xl/drawings/drawing1.xml"
        drawing_rels_path = "xl/drawings/_rels/drawing1.xml.rels"

        if drawing_path in self.parts:
            # la plantilla ya trae un dibujo (por ejemplo una linea): se le suma el logo
            dr = etree.fromstring(self.parts[drawing_path])
            for child in etree.fromstring(wrapper):
                dr.append(child)
            self.parts[drawing_path] = etree.tostring(dr, xml_declaration=True, encoding="UTF-8", standalone=True)
            if drawing_rels_path in self.parts:
                drels = etree.fromstring(self.parts[drawing_rels_path])
            else:
                drels = etree.Element("{%s}Relationships" % NS_PKG_REL, nsmap={None: NS_PKG_REL})
            rel = etree.SubElement(drels, "{%s}Relationship" % NS_PKG_REL)
            rel.set("Id", rid)
            rel.set("Type", img_rel)
            rel.set("Target", f"../media/{tag}.{ext}")
            self.parts[drawing_rels_path] = etree.tostring(drels, xml_declaration=True, encoding="UTF-8", standalone=True)
            self._register_image_type(ext)
            return

        self.parts[drawing_path] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + wrapper).encode("utf-8")
        self.parts[drawing_rels_path] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{NS_PKG_REL}"><Relationship Id="{rid}" '
            f'Type="{img_rel}" Target="../media/{tag}.{ext}"/></Relationships>'
        ).encode("utf-8")

        # relacion hoja -> dibujo
        rels_path = "xl/worksheets/_rels/sheet1.xml.rels"
        if rels_path in self.parts:
            rels = etree.fromstring(self.parts[rels_path])
        else:
            rels = etree.Element("{%s}Relationships" % NS_PKG_REL, nsmap={None: NS_PKG_REL})
        rel = etree.SubElement(rels, "{%s}Relationship" % NS_PKG_REL)
        rel.set("Id", "rIdLogo1")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing")
        rel.set("Target", "../drawings/drawing1.xml")
        self.parts[rels_path] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)

        # <drawing r:id> en la hoja, en el lugar que exige el esquema
        drawing_el = etree.Element(M + "drawing", nsmap={"r": NS_REL})
        drawing_el.set("{%s}id" % NS_REL, "rIdLogo1")
        anchor = None
        for tag in ("pageMargins", "pageSetup", "headerFooter", "rowBreaks", "colBreaks",
                    "customProperties", "cellWatches", "ignoredErrors", "smartTags"):
            found = self.root.find(M + tag)
            if found is not None:
                anchor = found
        if anchor is not None:
            anchor.addnext(drawing_el)
        else:
            self.root.append(drawing_el)

        self._register_image_type(ext)
        ct = etree.fromstring(self.parts["[Content_Types].xml"])
        d = etree.SubElement(ct, "{%s}Override" % NS_CT)
        d.set("PartName", "/xl/drawings/drawing1.xml")
        d.set("ContentType", "application/vnd.openxmlformats-officedocument.drawing+xml")
        self.parts["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)

    def _register_image_type(self, ext: str) -> None:
        ct = etree.fromstring(self.parts["[Content_Types].xml"])
        have_ext = {d.get("Extension") for d in ct.findall("{%s}Default" % NS_CT)}
        if ext not in have_ext:
            d = etree.SubElement(ct, "{%s}Default" % NS_CT)
            d.set("Extension", ext)
            d.set("ContentType", "image/png" if ext == "png" else "image/jpeg")
            self.parts["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)

    # ------------------------------------------------------------ salida --
    def to_bytes(self) -> bytes:
        self.parts[SHEET] = etree.tostring(self.root, xml_declaration=True, encoding="UTF-8", standalone=True)

        # calcChain obsoleto: Excel lo reconstruye solo; dejarlo desactualizado da error al abrir
        if "xl/calcChain.xml" in self.parts:
            del self.parts["xl/calcChain.xml"]
            ct = etree.fromstring(self.parts["[Content_Types].xml"])
            for o in ct.findall("{%s}Override" % NS_CT):
                if o.get("PartName") == "/xl/calcChain.xml":
                    ct.remove(o)
            self.parts["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)
            rels = etree.fromstring(self.parts["xl/_rels/workbook.xml.rels"])
            for r in rels.findall("{%s}Relationship" % NS_PKG_REL):
                if (r.get("Target") or "").endswith("calcChain.xml"):
                    rels.remove(r)
            self.parts["xl/_rels/workbook.xml.rels"] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)

        wb = etree.fromstring(self.parts["xl/workbook.xml"])
        calc = wb.find(M + "calcPr")
        if calc is None:
            calc = etree.SubElement(wb, M + "calcPr")
        calc.set("fullCalcOnLoad", "1")
        self.parts["xl/workbook.xml"] = etree.tostring(wb, xml_declaration=True, encoding="UTF-8", standalone=True)

        buf = io.BytesIO()
        names = ["[Content_Types].xml"] + [n for n in self.parts if n != "[Content_Types].xml"]
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                z.writestr(n, self.parts[n])
        return buf.getvalue()
