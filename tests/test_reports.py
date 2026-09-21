from types import SimpleNamespace as NS

from app.reports import build_shift_report


def _vf():
    return NS(vessel_name="Lotus", vessel_type="Bulk Carrier", terminal=NS(name="ADM"), terminal_code="ADM")


def _shift(**extra):
    base = {
        "date": "21/09/2026", "time_from": "07:55", "time_to": "13:00",
        "gangs_text": "one line appointed", "greeting": "Good afternoon",
        "holds": [["H6", 2580.0, 1]],
        "cargos": [{"cargo_id": 1, "grade": "Urea in Bulk", "stowage_plan": 25430.0,
                    "shift_qty": 2580.0, "prior_total": 0.0, "prior_holds": {}}],
        "delays": "", "prospect": "", "include_breakdown": False,
    }
    base.update(extra)
    return base


def _cliente(formato):
    return NS(display_to="ADM", report_format=formato, email_list=["adm@example.com"])


def test_loading_shift_no_lleva_remarks():
    for formato in ("EXCEL", "WBL_TEXT"):
        r = build_shift_report(_vf(), _cliente(formato), _shift(delays="1035/1300 hs Not loading."))
        assert "Remarks" not in r.text_body, formato
        assert "Remarks" not in r.html_body, formato


def test_delays_multilinea_cada_demora_debajo_del_titulo():
    delays = ("07:45/08:45 Hrs - Strong winds. Loading operations stopped.\r\n"
              "\r\n"
              "11:10/13:00 Hrs - Strong winds. Loading operations stopped.")
    r = build_shift_report(_vf(), _cliente("EXCEL"), _shift(delays=delays, prospect="ETF : 22/0800 Hrs"))
    assert ("Delays:\n07:45/08:45 Hrs - Strong winds. Loading operations stopped.\n"
            "11:10/13:00 Hrs - Strong winds. Loading operations stopped.") in r.text_body
    # y el prospect sigue detras, separado como en el modelo
    assert "====================\nTentative prospect (AGW WP UCE):\nETF : 22/0800 Hrs" in r.text_body
    assert "Delays:<br>07:45/08:45" in r.html_body


def test_delays_de_un_renglon_va_debajo_del_titulo():
    r = build_shift_report(_vf(), _cliente("EXCEL"), _shift(delays="1035/1300 hs Not loading due to strong winds."))
    assert "Delays:\n1035/1300 hs Not loading due to strong winds." in r.text_body


def test_sin_demoras_queda_delays_vacio_en_una_linea():
    excel = build_shift_report(_vf(), _cliente("EXCEL"), _shift(delays=""))
    wbl = build_shift_report(_vf(), _cliente("WBL_TEXT"), _shift(delays="  "))
    nil = build_shift_report(_vf(), _cliente("EXCEL"), _shift(delays="NIL"))
    assert "Delays: -" in excel.text_body
    assert "Delays: NIL" in wbl.text_body
    assert "Delays: -" in nil.text_body


def test_el_resto_del_reporte_no_cambia():
    r = build_shift_report(_vf(), _cliente("EXCEL"), _shift())
    assert "Shift September 21st / 07:55 - 13:00 hrs (one line appointed):" in r.text_body
    assert "Total shift =\t2,580.000 MT – Urea in Bulk" in r.text_body
    assert "Balance to go =\t22,850.000 MT – Urea in Bulk" in r.text_body
