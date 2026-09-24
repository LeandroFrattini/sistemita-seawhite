"""Coordenadas de referencia de las areas de fondeo (Utilidades). Info
fija, se actualiza editando esta lista -- mismo criterio que
costos_templates.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fondeadero:
    nombre: str
    puntos: list[tuple[str, str]]  # (latitud, longitud) por vertice

    def texto_plano(self) -> str:
        lineas = [self.nombre.upper(), ""]
        for lat, lon in self.puntos:
            lineas.append(f"Latitud {lat} - Longitud {lon}")
        return "\n".join(lineas)


FONDEADEROS: list[Fondeadero] = [
    Fondeadero("Fondeadero Charlie", [
        ("38º59'.10 S", "061º53'.90 W"),
        ("38º59'.50 S", "061º54'.20 W"),
        ("39º00'.30 S", "061º51'.10 W"),
        ("39º00'.55 S", "061º51'.70 W"),
    ]),
    Fondeadero("Fondeadero Delta", [
        ("38º58'.57 S", "061º55'.56 W"),
        ("38º59'.13 S", "061º55'.79 W"),
        ("38º59'.57 S", "061º54'.35 W"),
        ("38º59'.00 S", "061º54'.04 W"),
    ]),
    Fondeadero("Fondeadero Echo", [
        ("38º58'34\" S", "061º55'33\" W"),
        ("38º59'07\" S", "061º55'47\" W"),
        ("38º58'04\" S", "061º57'19\" W"),
        ("38º58'35\" S", "061º57'36\" W"),
    ]),
    Fondeadero("Fondeadero Alpha y Beta", [
        ("39º04'10\" S", "61º48'36\" W"),
        ("39º05'12\" S", "61º46'29\" W"),
        ("39º06'21\" S", "61º46'36\" W"),
        ("39º04'52\" S", "61º49'12\" W"),
    ]),
]
