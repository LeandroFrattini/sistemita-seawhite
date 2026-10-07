"""Junta varios .xlsx de una sola hoja en un unico libro (una hoja por documento),
tocando el XML: se conservan estilos, imagenes, anchos, areas e impresion de
cada hoja. Sirve para imprimir todo de una vez desde Excel ("Imprimir libro
completo") con el formato exacto de cada documento."""
from __future__ import annotations

import copy
import io
import re
import zipfile

from lxml import etree

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
M = "{%s}" % NS_MAIN
R = "{%s}" % NS_REL
PKG = "{%s}" % NS_PKG_REL

T_SHEET = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
T_STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
T_THEME = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
T_DRAWING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
T_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"

CT_BY_EXT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "emf": "image/x-emf",
             "wmf": "image/x-wmf", "gif": "image/gif"}


def _canon(el) -> str:
    return etree.tostring(el, method="c14n").decode()


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "-", name).strip("'") or "Hoja"
    base = base[:31]
    out, i = base, 2
    while out.lower() in used:
        suffix = f" ({i})"
        out = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(out.lower())
    return out


class _StyleMerger:
    """Une las tablas de estilos de varios libros en una sola y remapea los indices."""

    def __init__(self, first_styles: etree._Element):
        self.first = first_styles
        self.numfmts: dict[str, int] = {}
        self.fonts: dict[str, int] = {}
        self.fills: dict[str, int] = {}
        self.borders: dict[str, int] = {}
        self.xfs: dict[str, int] = {}
        self.font_list: list = []
        self.fill_list: list = []
        self.border_list: list = []
        self.xf_list: list = []
        self.numfmt_list: list = []
        self.next_fmt = 164

    def _add(self, store: dict, items: list, el) -> int:
        key = _canon(el)
        if key not in store:
            store[key] = len(items)
            items.append(copy.deepcopy(el))
        return store[key]

    def add_workbook(self, styles: etree._Element) -> list[int]:
        """Incorpora los estilos de un libro. Devuelve el mapa indice viejo -> indice nuevo de cellXfs."""
        fmt_map: dict[int, int] = {}
        nf = styles.find(M + "numFmts")
        if nf is not None:
            for f in nf:
                code = f.get("formatCode")
                if code not in self.numfmts:
                    self.numfmts[code] = self.next_fmt
                    self.numfmt_list.append((self.next_fmt, code))
                    self.next_fmt += 1
                fmt_map[int(f.get("numFmtId"))] = self.numfmts[code]

        font_map = [self._add(self.fonts, self.font_list, e) for e in styles.find(M + "fonts")]
        fill_map = [self._add(self.fills, self.fill_list, e) for e in styles.find(M + "fills")]
        border_map = [self._add(self.borders, self.border_list, e) for e in styles.find(M + "borders")]

        xf_map: list[int] = []
        for xf in styles.find(M + "cellXfs"):
            new = copy.deepcopy(xf)
            nid = int(new.get("numFmtId", "0"))
            new.set("numFmtId", str(fmt_map.get(nid, nid)))
            new.set("fontId", str(font_map[int(new.get("fontId", "0"))]))
            new.set("fillId", str(fill_map[int(new.get("fillId", "0"))]))
            new.set("borderId", str(border_map[int(new.get("borderId", "0"))]))
            new.set("xfId", "0")
            xf_map.append(self._add(self.xfs, self.xf_list, new))
        return xf_map

    def build(self) -> bytes:
        root = etree.Element(M + "styleSheet", nsmap={None: NS_MAIN})
        if self.numfmt_list:
            nf = etree.SubElement(root, M + "numFmts", count=str(len(self.numfmt_list)))
            for fid, code in self.numfmt_list:
                etree.SubElement(nf, M + "numFmt", numFmtId=str(fid), formatCode=code)
        for tag, items in (("fonts", self.font_list), ("fills", self.fill_list), ("borders", self.border_list)):
            holder = etree.SubElement(root, M + tag, count=str(len(items)))
            for it in items:
                holder.append(it)
        for tag in ("cellStyleXfs",):
            src = self.first.find(M + tag)
            if src is not None:
                root.append(copy.deepcopy(src))
        xfs = etree.SubElement(root, M + "cellXfs", count=str(len(self.xf_list)))
        for it in self.xf_list:
            xfs.append(it)
        for tag in ("cellStyles", "dxfs", "tableStyles"):
            src = self.first.find(M + tag)
            if src is not None:
                root.append(copy.deepcopy(src))
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _sst(parts: dict[str, bytes]) -> list:
    if "xl/sharedStrings.xml" not in parts:
        return []
    return list(etree.fromstring(parts["xl/sharedStrings.xml"]).findall(M + "si"))


def merge_workbooks(items: list[tuple[str, bytes]]) -> bytes:
    """items: [(nombre de hoja, bytes de un .xlsx de una hoja)]. Devuelve el libro unido."""
    if not items:
        raise ValueError("No hay hojas para unir")

    loaded = []
    for name, data in items:
        z = zipfile.ZipFile(io.BytesIO(data))
        loaded.append((name, {n: z.read(n) for n in z.namelist()}))

    first_styles = etree.fromstring(loaded[0][1]["xl/styles.xml"])
    styles = _StyleMerger(first_styles)

    out: dict[str, bytes] = {}
    sheet_entries: list[tuple[str, str, str]] = []  # (nombre, ruta de la hoja, area de impresion)
    drawing_overrides: list[str] = []
    media_exts: set[str] = set()
    used_names: set[str] = set()

    for idx, (raw_name, parts) in enumerate(loaded, start=1):
        sheet_name = _safe_sheet_name(raw_name, used_names)
        xf_map = styles.add_workbook(etree.fromstring(parts["xl/styles.xml"]))
        sst = _sst(parts)
        root = etree.fromstring(parts["xl/worksheets/sheet1.xml"])

        # estilos y cadenas compartidas -> indices nuevos / texto en la propia celda
        for c in root.iter(M + "c"):
            if c.get("s") is not None:
                c.set("s", str(xf_map[int(c.get("s"))]))
            if c.get("t") == "s":
                v = c.find(M + "v")
                si = sst[int(v.text)]
                c.remove(v)
                c.set("t", "inlineStr")
                is_ = etree.SubElement(c, M + "is")
                for child in si:
                    if child.tag in (M + "t", M + "r"):
                        is_.append(copy.deepcopy(child))
        for row in root.iter(M + "row"):
            if row.get("s") is not None:
                row.set("s", str(xf_map[int(row.get("s"))]))
        for col in root.iter(M + "col"):
            if col.get("style") is not None:
                col.set("style", str(xf_map[int(col.get("style"))]))

        sheet_pr = root.find(M + "sheetPr")
        if sheet_pr is not None and "codeName" in sheet_pr.attrib:
            del sheet_pr.attrib["codeName"]
        for sv in root.iter(M + "sheetView"):
            if idx == 1:
                sv.set("tabSelected", "1")
            elif "tabSelected" in sv.attrib:
                del sv.attrib["tabSelected"]
        ps = root.find(M + "pageSetup")
        if ps is not None and (R + "id") in ps.attrib:
            del ps.attrib[R + "id"]  # se descarta la config. de impresora del equipo original

        # dibujo (logo, lineas, imagenes) de la hoja
        sheet_rels = etree.Element(PKG + "Relationships", nsmap={None: NS_PKG_REL})
        drawing_el = root.find(M + "drawing")
        if drawing_el is not None:
            old_rid = drawing_el.get(R + "id")
            old_rels = etree.fromstring(parts["xl/worksheets/_rels/sheet1.xml.rels"])
            target = next(r.get("Target") for r in old_rels if r.get("Id") == old_rid)
            old_drawing = "xl/" + target.replace("../", "")
            new_drawing = f"xl/drawings/drawing{idx}.xml"
            out[new_drawing] = parts[old_drawing]
            drawing_overrides.append("/" + new_drawing)

            old_drels_path = old_drawing.replace("drawings/", "drawings/_rels/") + ".rels"
            if old_drels_path in parts:
                drels = etree.fromstring(parts[old_drels_path])
                for r in drels:
                    tgt = r.get("Target")
                    if "media/" in tgt:
                        fname = tgt.split("/")[-1]
                        ext = fname.rsplit(".", 1)[-1].lower()
                        media_exts.add(ext)
                        new_media = f"xl/media/h{idx}_{fname}"
                        out[new_media] = parts["xl/media/" + fname]
                        r.set("Target", f"../media/h{idx}_{fname}")
                out[f"xl/drawings/_rels/drawing{idx}.xml.rels"] = etree.tostring(
                    drels, xml_declaration=True, encoding="UTF-8", standalone=True)

            drawing_el.set(R + "id", "rIdDr1")
            rel = etree.SubElement(sheet_rels, PKG + "Relationship")
            rel.set("Id", "rIdDr1")
            rel.set("Type", T_DRAWING)
            rel.set("Target", f"../drawings/drawing{idx}.xml")
        if len(sheet_rels):
            out[f"xl/worksheets/_rels/sheet{idx}.xml.rels"] = etree.tostring(
                sheet_rels, xml_declaration=True, encoding="UTF-8", standalone=True)

        out[f"xl/worksheets/sheet{idx}.xml"] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True)

        # area de impresion de la hoja
        wb = etree.fromstring(parts["xl/workbook.xml"])
        area = ""
        for dn in wb.iter(M + "definedName"):
            if dn.get("name") == "_xlnm.Print_Area" and dn.get("localSheetId") == "0":
                area = dn.text.rsplit("!", 1)[-1]
                break
        sheet_entries.append((sheet_name, f"sheet{idx}.xml", area))

    out["xl/styles.xml"] = styles.build()
    out["xl/theme/theme1.xml"] = loaded[0][1]["xl/theme/theme1.xml"]

    # workbook.xml
    wb_root = etree.Element(M + "workbook", nsmap={None: NS_MAIN, "r": NS_REL})
    first_wb = etree.fromstring(loaded[0][1]["xl/workbook.xml"])
    wb_pr = first_wb.find(M + "workbookPr")
    wb_root.append(copy.deepcopy(wb_pr) if wb_pr is not None else etree.Element(M + "workbookPr"))
    views = etree.SubElement(wb_root, M + "bookViews")
    etree.SubElement(views, M + "workbookView", activeTab="0")
    sheets_el = etree.SubElement(wb_root, M + "sheets")
    for i, (name, _, _) in enumerate(sheet_entries, start=1):
        s = etree.SubElement(sheets_el, M + "sheet")
        s.set("name", name)
        s.set("sheetId", str(i))
        s.set(R + "id", f"rId{i}")
    names_el = etree.SubElement(wb_root, M + "definedNames")
    for i, (name, _, area) in enumerate(sheet_entries):
        if area:
            dn = etree.SubElement(names_el, M + "definedName")
            dn.set("name", "_xlnm.Print_Area")
            dn.set("localSheetId", str(i))
            dn.text = "'" + name.replace("'", "''") + "'!" + area
    etree.SubElement(wb_root, M + "calcPr", calcId="191029", fullCalcOnLoad="1")
    out["xl/workbook.xml"] = etree.tostring(wb_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # relaciones del libro
    n = len(sheet_entries)
    wrels = etree.Element(PKG + "Relationships", nsmap={None: NS_PKG_REL})
    for i, (_, path, _) in enumerate(sheet_entries, start=1):
        r = etree.SubElement(wrels, PKG + "Relationship")
        r.set("Id", f"rId{i}")
        r.set("Type", T_SHEET)
        r.set("Target", f"worksheets/{path}")
    for rid, typ, target in ((f"rId{n + 1}", T_STYLES, "styles.xml"), (f"rId{n + 2}", T_THEME, "theme/theme1.xml")):
        r = etree.SubElement(wrels, PKG + "Relationship")
        r.set("Id", rid)
        r.set("Type", typ)
        r.set("Target", target)
    out["xl/_rels/workbook.xml.rels"] = etree.tostring(wrels, xml_declaration=True, encoding="UTF-8", standalone=True)

    out["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{NS_PKG_REL}"><Relationship Id="rId1" Type="{T_DOC}" Target="xl/workbook.xml"/></Relationships>'
    ).encode("utf-8")

    # tipos de contenido
    ct = etree.Element("{%s}Types" % NS_CT, nsmap={None: NS_CT})
    for ext, mime in (("rels", "application/vnd.openxmlformats-package.relationships+xml"), ("xml", "application/xml")):
        etree.SubElement(ct, "{%s}Default" % NS_CT, Extension=ext, ContentType=mime)
    for ext in sorted(media_exts):
        etree.SubElement(ct, "{%s}Default" % NS_CT, Extension=ext, ContentType=CT_BY_EXT.get(ext, "application/octet-stream"))
    ovr = [("/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
           ("/xl/styles.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"),
           ("/xl/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml")]
    ovr += [(f"/xl/worksheets/{p}", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
            for _, p, _ in sheet_entries]
    ovr += [(d, "application/vnd.openxmlformats-officedocument.drawing+xml") for d in drawing_overrides]
    for part, mime in ovr:
        etree.SubElement(ct, "{%s}Override" % NS_CT, PartName=part, ContentType=mime)
    out["[Content_Types].xml"] = etree.tostring(ct, xml_declaration=True, encoding="UTF-8", standalone=True)

    buf = io.BytesIO()
    order = ["[Content_Types].xml", "_rels/.rels"] + [k for k in out if k not in ("[Content_Types].xml", "_rels/.rels")]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k in order:
            z.writestr(k, out[k])
    return buf.getvalue()
