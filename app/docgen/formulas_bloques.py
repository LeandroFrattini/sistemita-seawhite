"""Armado de la solapa FORMULAS: un bloque por renglon de la proforma (ver formulas_xlsx.py para el estilo y las celdas)."""
from __future__ import annotations

from .fechas import parse_number
from .formulas_xlsx import ANCHOS, Ex, agregar_hoja, es, fecha_dia, fecha_hora, registrar_estilos

TOL_USD, TOL_ARS = 0.05, 5.0
TIPOS_DIA = {"SEMANA": "Día hábil", "HABIL": "Día hábil", "SABADO": "Sábado", "DOMINGO": "Domingo", "FERIADO": "Feriado", "NO_LABORABLE": "Día no laborable"}


def _corto(iso: str) -> str:
    """'2026-08-03' -> 'lun 03/08'."""
    t = fecha_dia(iso)
    return t[:-5] if len(t) > 5 else t


def _suma(filas: list[int]) -> str:
    return "+".join(f"C{f}" for f in filas) if filas else "0"


# ------------------------------------------------------------------------------------------------------------------ bloques
def _practicaje(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    k = "in" if l["clave"] == "pilot_in" else "out"
    pr, m, p = det["pract"], det["pract"].get(k), det["pilot"]
    if not m:
        return None
    b = s["buque"]
    ex.nota("Tarifa de practicaje: se calcula con las medidas del barco y el calado de ESE movimiento (entrada y salida van por separado).")
    f_e = ex.dato("Eslora", b["eslora"], "m", "Paso 3 (datos del buque)")
    f_m = ex.dato("Manga", b["manga"], "m", "Paso 3 (datos del buque)")
    f_p = ex.dato("Puntal", b["puntal"], "m", "Paso 3 (datos del buque)")
    f_uf = ex.cuenta("UF = eslora × manga × puntal ÷ 800", f"C{f_e}*C{f_m}*C{f_p}/800", "", "Valor del barco para la tarifa.", fmt="4")
    f_cal = ex.dato(f"Calado de {'entrada' if k == 'in' else 'salida'}", m["calado_pies"], "pies", "Paso 3 (en pies)")
    f_fac = ex.dato("Coeficiente por calado", m["factor"], "", "Tabla de practicaje (Proformador → Fórmulas), tramo en el que cae el calado.", fmt="4")
    f_cm = ex.dato("Coeficiente de maniobra", p["coef_maniobra"], "", "Parámetro de practicaje (Proformador → Fórmulas)", fmt="4")
    f_cn = ex.dato("Coeficiente de navegación", p["coef_navegacion"], "", "Parámetro de practicaje", fmt="4")
    f_ck = ex.dato("Coeficiente por km", p["coef_km"], "", "Parámetro de practicaje", fmt="4")
    f_km = ex.dato("Km del recorrido", p["km"], "km", "Parámetro de practicaje (recorrido Extranjero I.White–Profertil)", fmt="4")
    f_ds = ex.dato("Descuento", p["descuento"], "", "Parámetro de practicaje (0,2 = 20 %)", fmt="4")
    f_sv = ex.dato("Service fijo", p["service"], "USD", "Parámetro de practicaje (no se duplica con dos prácticos)")
    f_dos = ex.dato("Cantidad de prácticos", 2 if pr["dos_practicos"] else 1, "", ("Manga mayor a 39,9 m: van dos prácticos y se duplica la tarifa de gobierno." if pr["dos_por_manga"] else "Un práctico (con manga hasta 39,9 m)."), fmt="0")
    f_man = ex.cuenta("Maniobra = UF × coef. maniobra × coef. calado", f"C{f_uf}*C{f_cm}*C{f_fac}", "USD")
    f_nav = ex.cuenta("Navegación = (UF × coef. navegación + coef. km × km) × coef. calado", f"(C{f_uf}*C{f_cn}+C{f_ck}*C{f_km})*C{f_fac}", "USD")
    f_gob = ex.cuenta("Tarifa de gobierno = (maniobra + navegación) × (1 − descuento) × prácticos", f"(C{f_man}+C{f_nav})*(1-C{f_ds})*C{f_dos}", "USD")
    _ = f_cal
    return ex.cuenta("Total del movimiento = gobierno + service fijo", f"ROUND(C{f_gob}+C{f_sv},2)", "USD")


def _dias_muelle(ex: Ex, detalle: list[dict], etiqueta_dia: str = "Día") -> tuple[int, int] | None:
    if not detalle:
        return None
    primera = ultima = 0
    for i, x in enumerate(detalle):
        cobra = [f"{bq['desde']}–{bq['hasta']} ({bq['peso']:g})" for bq in x["bloques"] if not bq["beneficio"]]
        libre = [f"{bq['desde']}–{bq['hasta']}" for bq in x["bloques"] if bq["beneficio"]]
        txt = ("Se cobran los bloques " + ", ".join(cobra) if cobra else "No se cobra ningún bloque") + (f". NO se cobra (beneficio): {', '.join(libre)}." if libre else ".")
        f = ex.dato(f"{etiqueta_dia} {fecha_dia(x['fecha'])}", x["subtotal"], "días", txt)
        primera = primera or f
        ultima = f
    return primera, ultima


def _muelle(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    m = det["calc"]["muelle"]
    if not m.get("total"):
        return None
    mu, b = s["muelle"], s["buque"]
    ex.nota("Se cobra por TRN y por día, y el día se parte en tres bloques de 8 horas (00–08 pesa 0,33; 08–16 pesa 0,34; 16–24 pesa 0,33). "
            "Un bloque se cobra entero si el barco estuvo amarrado en cualquier momento de ese bloque.")
    ex.dato("Entrada al muelle", fecha_hora(mu["entrada"] or b["amarre"]), "", "Paso 5 (si está vacío, es el amarre del paso 3)")
    ex.dato("Salida del muelle", fecha_hora(mu["salida"] or b["zarpe"]), "", "Paso 5 (si está vacío, es el zarpe del paso 3)")
    f_trn = ex.dato("TRN del buque", b["trn"], "TRN", "Paso 3 (datos del buque)")
    f_t = ex.dato("Tarifa por TRN y por día (wharfage)", m["tarifa"], "USD", "Tarifa de muelle (Proformador → Fórmulas)", fmt="4")
    ex.encabezados("Día de la estadía", "Días que se cobran", "", "Qué bloques se cobran")
    rango = _dias_muelle(ex, m["detalle"])
    if not rango:
        return None
    f_d = ex.cuenta("Días de estadía a cobrar", f"SUM(C{rango[0]}:C{rango[1]})", "días", "Suma de los días de arriba.")
    ben = m["beneficio"]
    if ben["aplicado"]:
        ex.nota(f"BENEFICIO DE AMARRE FUERA DE DÍA HÁBIL (aplicado): no se cobran {es(ben['dias'])} días. Regla: si amarra un domingo o feriado (o de lunes a sábado entre las 21:00 y las 24:00) "
                "y la operación arranca el día hábil siguiente inmediato, no se cobra lo que corresponde al fin de semana/feriado hasta ese día. Sin el beneficio serían "
                f"{es(m['dias_brutos'])} días.")
    elif ben["detectado"]:
        ex.aviso(f"Correspondía el beneficio de amarre fuera de día hábil ({es(ben['dias'])} días) pero se destildó en el paso 5, así que se cobra la estadía completa ({es(m['dias_brutos'])} días).")
    return ex.cuenta("Importe = tarifa × TRN × días", f"ROUND(C{f_t}*C{f_trn}*C{f_d},2)", "USD")


def _fondeo(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    f = det["calc"].get("fondeo")
    if not f or not f.get("total"):
        return None
    fo, b = s["fondeo"], s["buque"]
    ex.nota("Fondeadero: misma lógica que el muelle (bloques de 8 horas), pero con su tarifa. Los bloques en los que el barco ya estaba amarrado NO se cobran de nuevo como fondeadero.")
    ex.dato("Entrada al fondeadero", fecha_hora(fo["entrada"]), "", "Paso 5")
    ex.dato("Salida del fondeadero", fecha_hora(fo["salida"]), "", "Paso 5")
    f_trn = ex.dato("TRN del buque", b["trn"], "TRN", "Paso 3 (datos del buque)")
    f_t = ex.dato("Tarifa por TRN y por día (fondeadero)", f["tarifa"], "USD", "Tarifa de fondeadero (Proformador → Fórmulas)", fmt="4")
    ex.encabezados("Día de la estadía", "Días que se cobran", "", "Qué bloques se cobran")
    rango = _dias_muelle(ex, f["detalle"])
    if not rango:
        return None
    f_d = ex.cuenta("Días en fondeadero a cobrar", f"SUM(C{rango[0]}:C{rango[1]})", "días", "Suma de los días de arriba.")
    if f.get("solapado"):
        ex.nota(f"Se dejaron de cobrar {es(f['solapado'])} días de fondeadero porque en esos bloques el barco estaba en el muelle.")
    return ex.cuenta("Importe = tarifa × TRN × días", f"ROUND(C{f_t}*C{f_trn}*C{f_d},2)", "USD")


def _vias(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    v = det["calc"]["vias"]
    if not v.get("total"):
        return None
    b = s["buque"]
    ex.nota("Vías navegables (CHANNEL TOLL): tarifa por tonelada × un coeficiente que depende del TRN × toneladas operadas × factor.")
    f_t = ex.dato("Tarifa por tonelada", v["tarifa"], "USD", "Tarifa de vías navegables (Proformador → Fórmulas)", fmt="4")
    f_c = ex.dato("Coeficiente según el TRN", v["coef"], "", "Tabla de coeficientes del channel toll, según el TRN del buque", fmt="4")
    if v["solo_bunker"]:
        f_trn = ex.dato("TRN del buque", b["trn"], "TRN", "Paso 3 (datos del buque)")
        f_b = ex.cuenta("Base = 20 % del TRN (solo bunker)", f"0.2*C{f_trn}", "tn", "Solo bunker: se toma el 20 % del TRN en lugar de las toneladas operadas (paso 5).", fmt="4")
    else:
        f_b = ex.dato("Toneladas operadas", v["base"], "tn", "Paso 3 (cantidad operada)", fmt="4")
    f_f = ex.dato("Factor", v["factor"], "", "Paso 5 (1 = normal)", fmt="4")
    return ex.cuenta("Importe = tarifa × coeficiente × base × factor", f"ROUND(C{f_t}*C{f_c}*C{f_b}*C{f_f},2)", "USD")


def _lds(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    am = l["clave"] == "mooring"
    x = det["lds"].get("amarre" if am else "desamarre")
    if not x:
        return None
    ex.nota("Lanchas del Sur: el importe depende del día y la hora del servicio (recargo 0 / 50 / 100 %). " + ("El amarre lleva el servicio más las lanchas." if am else "El desamarre es solo el servicio: NO lleva lanchas."))
    ex.dato("Momento del servicio", fecha_hora(x["momento"]), "", "Paso 6 (si está vacío, es el " + ("amarre" if am else "zarpe") + " del paso 3)")
    ex.dato("Tipo de día / recargo", f"{TIPOS_DIA.get(x['tipo_dia'], str(x['tipo_dia']).title())} — {x['recargo_pct']} %", "", "Calendario de feriados (Administración) y horario del tarifario LDS")
    f_b = ex.dato("Servicio de " + ("amarre" if am else "desamarre"), x["base_usd"], "USD", "Tarifario LDS, columna del recargo que corresponde")
    if not am:
        return ex.cuenta("Importe = servicio", f"ROUND(C{f_b},2)", "USD")
    f_l = ex.dato("Valor de cada lancha", x["lancha_unit_usd"], "USD", "Tarifario LDS, columna del recargo que corresponde")
    f_n = ex.dato("Cantidad de lanchas", x["lanchas"], "", "Automático: una lancha, o dos si la eslora supera 150 m (se puede cambiar en el paso 6)", fmt="0")
    return ex.cuenta("Importe = servicio + lanchas × valor", f"ROUND(C{f_b}+C{f_l}*C{f_n},2)", "USD")


def _escala(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    e = det["lds"].get("escala")
    if not e or not e.get("total_usd"):
        return None
    ex.nota("Escala de tierra (SHORE GANGWAY): colocación + retiro + alquiler por cada día (no lleva recargo horario).")
    f_c = ex.dato("Colocación", e["colocacion"], "USD", "Tarifario LDS")
    f_r = ex.dato("Retiro", e["retiro"], "USD", "Tarifario LDS")
    f_a = ex.dato("Alquiler por día", e["alquiler_diario"], "USD", "Tarifario LDS")
    f_d = ex.dato("Días", e["dias"], "días", "Paso 6 (si no se escribió, son los días de calendario entre el amarre y el desamarre, ambos inclusive)", fmt="0")
    return ex.cuenta("Importe = colocación + retiro + alquiler × días", f"ROUND(C{f_c}+C{f_r}+C{f_a}*C{f_d},2)", "USD")


def _draft(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    d = det["lds"].get("draft")
    if not d or not d.get("total_usd"):
        return None
    ex.nota("Lancha para el draft survey: una tarifa por uso, con el mismo recargo por día y hora que el amarre.")
    ex.dato("Momento del draft", fecha_hora(d.get("momento", "")), "", "Paso 6 (si está vacío, es el fin de operación del paso 3)")
    f_t = ex.dato("Tarifa de la lancha de draft", d["total_usd"], "USD", f"Tarifario LDS (recargo {d.get('recargo_pct', 0)} %, {TIPOS_DIA.get(d.get('tipo_dia'), str(d.get('tipo_dia', '')).title())})")
    return ex.cuenta("Importe = tarifa", f"ROUND(C{f_t},2)", "USD")


def _tally(ex: Ex, c: dict, l: dict, s: dict, det: dict, tally: dict) -> int | None:
    if not tally.get("resumen"):
        return None
    ex.nota("Head Tally: cada turno va a su escalón (básico, extra 100 %, extra 150 %, feriado ×3 o AT ORDERS) según el día y el horario. Valor × cantidad de turnos por escalón, más las cargas sociales de la agencia.")
    subs = []
    for r in tally["resumen"]:
        if not r["cantidad"]:
            continue
        turnos = [f"{_corto(f['fecha'])} {f['turno']}" for f in tally["filas"] if f["nivel"] == r["nivel"]]
        lista = "; ".join(turnos[:16]) + (f"; … (+{len(turnos) - 16})" if len(turnos) > 16 else "")
        f_c = ex.dato(f"{r['etiqueta']}: cantidad de turnos", r["cantidad"], "turnos", lista, fmt="0")
        origen = ("Escrito a mano en el paso 8" if r["manual"] else
                  ("Monto fijo de AT ORDERS (tarifas de personal)" if r["nivel"] == "AT" else f"Tarifa {tally['categoria']} vigente {tally['vigencia'] or ''}".strip()))
        f_p = ex.dato(f"{r['etiqueta']}: valor por turno", r["precio"], "ARS", origen)
        subs.append(ex.cuenta(f"{r['etiqueta']} = turnos × valor", f"C{f_c}*C{f_p}", "ARS"))
    f_s = ex.cuenta("Subtotal de turnos", _suma(subs), "ARS", "Suma de los escalones de arriba.")
    f_pct = ex.dato("Cargas sociales", s["agencia"]["tally_pct"], "%", "Paso 2 (por agencia). Se suman al costo: sobre 100 con 165 % da 265.", fmt="2")
    f_cg = ex.cuenta("Cargas = subtotal × %", f"C{f_s}*C{f_pct}/100", "ARS")
    return ex.cuenta("Total Head Tally = subtotal + cargas", f"ROUND(C{f_s}+C{f_cg},2)", "ARS")


def _serenos(ex: Ex, c: dict, l: dict, s: dict, det: dict, serenos: dict) -> int | None:
    if not serenos.get("filas"):
        return None
    ex.nota("Serenos: un sereno por turno de 6 horas. El valor depende del día y la ventana (HÁBIL, INHÁBIL o DOMINGO/feriado). Las cargas sociales se calculan sobre los sueldos; el viático se suma aparte y NO lleva cargas.")
    grupos: dict[tuple, list] = {}
    for f in serenos["filas"]:
        grupos.setdefault((f["tier"], f["precio"], f["manual"]), []).append(f)
    subs = []
    for (tier, precio, manual), fs in grupos.items():
        lista = "; ".join(f"{_corto(f['fecha'])} {f['ventana']}" for f in fs[:14]) + (f"; … (+{len(fs) - 14})" if len(fs) > 14 else "")
        f_c = ex.dato(f"Turnos {tier}: cantidad", sum(f["cant"] for f in fs), "turnos", lista, fmt="0")
        f_p = ex.dato(f"Turnos {tier}: valor por turno", precio, "ARS", "Escrito a mano en el paso 9" if manual else f"Tarifa de serenos {serenos['categoria'] or ''} vigente {serenos['vigencia'] or ''}".replace("  ", " ").strip())
        subs.append(ex.cuenta(f"Turnos {tier} = turnos × valor", f"C{f_c}*C{f_p}", "ARS"))
    f_s = ex.cuenta("Subtotal de sueldos", _suma(subs), "ARS", "Suma de los grupos de arriba.")
    f_pct = ex.dato("Cargas sociales", s["agencia"]["serenos_pct"], "%", "Paso 2 (por agencia). Se suman al costo: sobre 100 con 165 % da 265.", fmt="2")
    f_cg = ex.cuenta("Cargas = subtotal × %", f"C{f_s}*C{f_pct}/100", "ARS")
    v = serenos["viatico"]
    partes = [f_s, f_cg]
    if v["total"]:
        f_vc = ex.dato("Viáticos: cantidad de turnos", v["cantidad"], "turnos", "Un viático por turno cubierto", fmt="0")
        f_vu = ex.dato("Viático por turno", v["unit"], "ARS", "Escrito a mano en el paso 9" if v["manual"] else f"Tarifa de viático {v['tipo']}")
        partes.append(ex.cuenta("Viáticos = turnos × viático", f"C{f_vc}*C{f_vu}", "ARS"))
    return ex.cuenta("Total serenos = sueldos + cargas + viáticos", f"ROUND({_suma(partes)},2)", "ARS")


def _migraciones(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    fila = next((f for f in det["mig"]["filas"] if f["key"] == l["clave"]), None)
    if not fila:
        return None
    k = l["clave"]
    if k == "free_pratique":
        p = det["free"]
        ex.nota("Free pratique: depende del TRN. (TRN − resta) ÷ 1000 × coeficiente + base.")
        f_trn = ex.dato("TRN del buque", s["buque"]["trn"], "TRN", "Paso 3 (datos del buque)")
        f_r = ex.dato("Resta del TRN", p["resta"], "", "Parámetro (Proformador → Fórmulas)")
        f_k = ex.dato("Coeficiente por cada 1000", p["coef"], "ARS", "Parámetro (Proformador → Fórmulas)")
        f_bs = ex.dato("Base", p["base"], "ARS", "Parámetro (Proformador → Fórmulas)")
        f_au = ex.cuenta("Importe de la tabla", f"MAX(C{f_trn}-C{f_r},0)/1000*C{f_k}+C{f_bs}", "ARS")
    elif fila["boya"]:
        f_au = ex.dato("Importe de la tabla (en boya)", fila["precio_auto"], fila["moneda"], "Parámetro de migraciones en boya (Proformador → Fórmulas)")
    else:
        f_au = ex.dato("Importe de la tabla", fila["precio_auto"], fila["moneda"], "Conceptos fijos / parámetros (Proformador → Fórmulas)")
    if fila["manual"] and abs(fila["precio"] - fila["precio_auto"]) > 0.005:
        f_m = ex.dato("Importe escrito a mano", fila["precio"], fila["moneda"], "Paso 10: se escribió un importe distinto al de la tabla")
        ex.nota("Se usa el importe escrito a mano, no el de la tabla.")
        return ex.cuenta("Importe usado", f"ROUND(C{f_m},2)", fila["moneda"])
    return ex.cuenta("Importe usado", f"ROUND(C{f_au},2)", fila["moneda"])


def _aduana(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    it = next((i for i in s["aduana"]["items"] if "aduana_" + i["key"] == l["clave"]), None)
    if not it:
        return None
    f_c = ex.dato("Cantidad", it["cant"], "", "Paso 7", fmt="0")
    f_p = ex.dato("Precio de cada habilitación", it["precio"], "USD", "Paso 7")
    return ex.cuenta("Importe = cantidad × precio", f"ROUND(C{f_c}*C{f_p},2)", "USD")


def _fijo(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    manual = s["chequeo"][l["clave"]]["precio"] if l["clave"] in s["chequeo"] else 0
    return ex.dato("Importe", l["monto"], "USD", "Escrito a mano en el paso 11" if manual else "Importe fijo del sistema (Proformador → Fórmulas / parámetros)")


def _extra(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    return ex.dato("Importe", l["monto"], l["moneda"], "Renglón libre escrito en el paso 11")


def _fee(ex: Ex, c: dict, l: dict, s: dict, det: dict) -> int | None:
    return ex.dato("Fee de la agencia", l["monto"], "USD", "Paso 2 (fee de la agencia). No entra en la base del LAW.")


def _law(ex: Ex, c: dict, l: dict, s: dict, ch: dict, det: dict) -> int | None:
    ex.nota("LAW NR 25413 = porcentaje de la suma de los renglones que se facturan, SIN el fee y SIN lo que va FOR YOUR ACCOUNT. Cada renglón se toma en dólares.")
    filas = []
    for x in ch["lineas"]:
        if x["clave"] in ("law",) or not x["base_law"]:
            continue
        r = ex.res.get(x["n"])
        if r and "usd" in r:
            filas.append(ex.cuenta(f"{x['n']}. {x['texto']}", f"C{r['usd']}", "USD", "Importe en dólares del renglón (ver su bloque más arriba)"))
    f_b = ex.cuenta("Base del LAW", _suma(filas), "USD", "Suma de los renglones de arriba (sin fee).")
    f_p = ex.dato("Porcentaje", ch["law"]["pct"], "%", "Parámetro del sistema (Administración): 1,2 %", fmt="2")
    f_a = ex.cuenta("LAW calculado = base × %", f"C{f_b}*C{f_p}/100", "USD")
    if ch["law"]["manual"]:
        ex.aviso("El LAW se escribió A MANO en el paso 11: no es el calculado. Revisalo.")
    return f_a


# ------------------------------------------------------------------------------------------------------------------ armado
def _bloque(ex: Ex, c: dict, l: dict, s: dict, ch: dict, det: dict, tally: dict, serenos: dict) -> int | None:
    k = l["clave"]
    if k in ("pilot_in", "pilot_out"):
        return _practicaje(ex, c, l, s, det)
    if k == "port_dues":
        return _muelle(ex, c, l, s, det)
    if k == "anchor":
        return _fondeo(ex, c, l, s, det)
    if k == "channel_toll":
        return _vias(ex, c, l, s, det)
    if k in ("mooring", "unmooring"):
        return _lds(ex, c, l, s, det)
    if k == "gangway":
        return _escala(ex, c, l, s, det)
    if k == "draft":
        return _draft(ex, c, l, s, det)
    if k == "tally":
        return _tally(ex, c, l, s, det, tally)
    if k == "serenos":
        return _serenos(ex, c, l, s, det, serenos)
    if k in ("mig_in", "mig_out", "taxi_in", "taxi_out", "taxi_sanidad", "free_pratique"):
        return _migraciones(ex, c, l, s, det)
    if k.startswith("aduana_"):
        return _aduana(ex, c, l, s, det)
    if k in ("senasa", "maritime", "misc"):
        return _fijo(ex, c, l, s, det)
    if k.startswith("extra_"):
        return _extra(ex, c, l, s, det)
    if k == "fee":
        return _fee(ex, c, l, s, det)
    if k == "law":
        return _law(ex, c, l, s, ch, det)
    return None


def _renglon(ex: Ex, c: dict, l: dict, s: dict, ch: dict, det: dict, tally: dict, serenos: dict, clave_res, titulo: str, estilo: str) -> None:
    ex.banda(titulo, estilo)
    ex.dato("Cómo se cargó", f"Paso {l['paso']}", "", "Si hay que corregir este renglón, se corrige en ese paso de la proforma final.")
    try:
        fila = _bloque(ex, c, l, s, ch, det, tally, serenos)
    except Exception:  # un detalle que no se pudo explicar no puede romper el resto de la hoja
        fila = None
    if fila is None:
        ex.nota("No se pudo reconstruir la cuenta de este renglón: se muestra el importe que figura en la proforma.")
        fila = ex.dato("Importe cargado", l["monto"], l["moneda"], f"Paso {l['paso']}")
    usado = l["monto"]
    ex.cierre(clave_res, l["moneda"], fila, usado, c["dolar"], c["dolar_fee"] if l.get("dolar_propio") else None)


def _total_fila(ex: Ex, etiqueta: str, f_usd: int | None, f_ars: int | None, v_usd: float, v_ars: float, texto: str = "", estilo: str = "et", num: str = "num_simple") -> int:
    f = ex._avanzar()
    ex._c(f, "B", etiqueta, estilo=estilo)
    ex._c(f, "C", v_usd, f"C{f_usd}" if f_usd else None, num)
    ex._c(f, "D", v_ars, f"C{f_ars}" if f_ars else None, num)
    ex._c(f, "E", texto, estilo="origen")
    return f


def construir(lib, s: dict, ch: dict, tally: dict, serenos: dict, det: dict, hoja_agencia: str) -> None:
    """Arma la solapa FORMULAS y la suma al libro (visible, despues de las hojas de la agencia, SERENOS y TALLY)."""
    ex = Ex(registrar_estilos(lib))
    b = s["buque"]
    dolar = s["dolar"]["valor"] or 0.0
    dolar_fee = s["agencia"]["dolar_fee"] or 0.0
    ex.titulo("FORMULAS — cómo se calculó cada importe")
    ex.sub("Control interno: sirve para que quien revisa la proforma pueda seguir cada número desde el dato hasta el importe final. "
           "AZUL = dato (cargado o de una tabla). GRIS = cuenta (es una fórmula viva: si se cambia un dato azul, se recalcula). VERDE = el importe que va a la proforma. "
           "ROJO = algo que no coincide y hay que revisar. «Paso N» es la pantalla de la proforma final donde se carga o corrige ese dato.")
    ex.espacio()
    ex.banda("DATOS GENERALES DEL BUQUE")
    ex.dato("Buque", b["nombre"] or "—", "", "Paso 3")
    ex.dato("Amarre", fecha_hora(b["amarre"]), "", "Paso 3")
    ex.dato("Inicio de operación", fecha_hora(b["inicio"]), "", "Paso 3")
    ex.dato("Fin de operación", fecha_hora(b["fin"]), "", "Paso 3")
    ex.dato("Zarpe", fecha_hora(b["zarpe"]), "", "Paso 3")
    ex.dato("TRN", b["trn"], "TRN", "Paso 3")
    ex.dato("Eslora / manga / puntal", f"{b['eslora']:g} / {b['manga']:g} / {b['puntal']:g}", "m", "Paso 3")
    ex.dato("Cantidad operada", parse_number(b["cantidad"]) if b["cantidad"] and parse_number(b["cantidad"]) is not None else (b["cantidad"] or "—"), "tn", "Paso 3", fmt="2")
    origen_dolar = f"Paso 1 ({'BNA' if s['dolar']['origen'] == 'BNA' else 'escrito a mano'}{', al ' + s['dolar']['fecha'] if s['dolar']['fecha'] else ''}). Es el único dólar de la proforma, salvo el del fee."
    c = {"dolar": ex.dato("Dólar", dolar, "ARS por USD", origen_dolar), "dolar_fee": None}
    if dolar_fee:
        c["dolar_fee"] = ex.dato("Dólar del fee", dolar_fee, "ARS por USD", "Paso 2: el fee se pasa a pesos con este dólar (CAMBIO FEE en la hoja de la agencia).")
    ex.espacio()
    if not dolar:
        ex.aviso("Falta el dólar (paso 1): sin él no se puede pasar de pesos a dólares ni al revés. Cargalo y volvé a bajar el Excel.")
        agregar_hoja(lib, "FORMULAS", ex.xml(ANCHOS))
        return
    ex.nota(f"La proforma tiene {len(ch['lineas'])} renglones que se facturan" + (f" y {len(ch['ajenas'])} que van FOR YOUR ACCOUNT (por cuenta del armador, no se facturan)" if ch["ajenas"] else "") +
            ". Abajo está cada uno, en el mismo orden que en la hoja de la agencia.")
    ex.espacio()
    for l in ch["lineas"]:
        _renglon(ex, c, l, s, ch, det, tally, serenos, l["n"], f"{l['n']}. {l['texto']}", "banda")
    # --- totales y control contra la hoja de la agencia
    ex.banda("TOTAL DE LA PROFORMA Y CONTROL", "banda_total")
    ex.encabezados("Renglón", "USD", "ARS", "")
    primera = ex.r
    for l in ch["lineas"]:
        r = ex.res[l["n"]]
        _total_fila(ex, f"{l['n']}. {l['texto']}", r["usd"], r["ars"], ex.cache[f"C{r['usd']}"], ex.cache[f"C{r['ars']}"])
    ultima = ex.r - 1
    tu = sum(ex.cache[f"C{ex.res[l['n']]['usd']}"] for l in ch["lineas"])
    ta = sum(ex.cache[f"C{ex.res[l['n']]['ars']}"] for l in ch["lineas"])
    f_tot = ex._avanzar()
    ex._c(f_tot, "B", "TOTAL SEGÚN ESTA HOJA", estilo="tot_et")
    ex._c(f_tot, "C", tu, f"SUM(C{primera}:C{ultima})", "tot2")
    ex._c(f_tot, "D", ta, f"SUM(D{primera}:D{ultima})", "tot2")
    ex._c(f_tot, "E", "Suma de los importes de todos los renglones.", estilo="origen")
    fila_total = 16 + len(ch["lineas"]) + 1  # fila del TOTAL en la hoja de la agencia
    q = hoja_agencia.replace("'", "''")
    f_ag = ex._avanzar()
    ex._c(f_ag, "B", "TOTAL EN LA HOJA DE LA AGENCIA", estilo="tot_et")
    ex._c(f_ag, "C", ch["total_usd"] or 0.0, f"'{q}'!E{fila_total}", "tot2")
    ex._c(f_ag, "D", ch["total_ars"], f"'{q}'!D{fila_total}", "tot2")
    ex._c(f_ag, "E", "Es el número que ve el cliente.", estilo="origen")
    f_df = ex._avanzar()
    dif_u, dif_a = tu - (ch["total_usd"] or 0.0), ta - ch["total_ars"]
    bien = abs(dif_u) <= TOL_USD and abs(dif_a) <= TOL_ARS
    ex._c(f_df, "B", "DIFERENCIA", estilo="tot_et")
    ex._c(f_df, "C", dif_u, f"C{f_tot}-C{f_ag}", "tot2")
    ex._c(f_df, "D", dif_a, f"D{f_tot}-D{f_ag}", "tot2")
    ex._c(f_df, "E", "Tiene que dar cero (o centavos por redondeo).", estilo="origen")
    f_ok = ex._avanzar()
    ex._c(f_ok, "B", "CONTROL", estilo="tot_et")
    ex._c(f_ok, "C", "OK — todo coincide" if bien else "REVISAR — no coincide", f'IF(AND(ABS(C{f_df})<={TOL_USD},ABS(D{f_df})<={TOL_ARS}),"OK — todo coincide","REVISAR — no coincide")',
          "ok" if bien else "mal")
    ex._c(f_ok, "D", None, estilo="ok" if bien else "mal")
    ex.uniones.append(f"C{f_ok}:D{f_ok}")
    ex._c(f_ok, "E", "Si dice REVISAR: algún importe de la hoja de la agencia no sale de las cuentas de arriba (se tocó a mano o cambió un dato).", estilo="origen")
    ex.altos[f_ok] = 22
    ex.espacio()
    # --- lo que va por cuenta del armador
    if ch["ajenas"]:
        ex.banda("FOR YOUR ACCOUNT — por cuenta del armador (no se factura, no suma al total)", "banda_ajena")
        ex.espacio()
        for k, l in enumerate(ch["ajenas"]):
            _renglon(ex, c, l, s, ch, det, tally, serenos, f"ajena{k}", l["texto"], "banda_ajena")
    ex.banda("REGLAS QUE SE APLICAN", "banda_total")
    for t in ("DÓLAR: hay uno solo (paso 1) para toda la proforma. La única excepción es el fee, que puede pasarse a pesos con su propio dólar (paso 2).",
              "LAW NR 25413: 1,2 % de los renglones que se facturan, en dólares. No incluye el fee ni lo que va FOR YOUR ACCOUNT.",
              "MUELLE: se cobra por bloques de 8 horas. Si el barco amarra un domingo o feriado (o de lunes a sábado desde las 21:00) y la operación arranca el día hábil siguiente inmediato, "
              "no se cobra lo que corresponde a ese fin de semana / feriado.",
              "LDS: el amarre lleva servicio + lanchas; el desamarre es solo el servicio. El recargo depende del día y la hora.",
              "HEAD TALLY: cada turno va a su escalón según el día y el horario. AT ORDERS es un monto fijo por turno, cualquiera sea el día.",
              "CARGAS SOCIALES: tally y serenos las llevan según el porcentaje de la agencia (paso 2). El viático de los serenos va aparte y no lleva cargas."):
        ex.nota(t)
    agregar_hoja(lib, "FORMULAS", ex.xml(ANCHOS))
