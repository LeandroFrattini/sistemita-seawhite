"""Coordenadas de referencia de las areas de fondeo (Utilidades). Info
fija, se actualiza editando esta lista -- mismo criterio que
costos_templates.py.

Fuente: pantalla "Anchorage Areas" del VTS de Bahia Blanca -- reemplaza
cualquier dato suelto que hubiera de otra fuente (coincide exacto con
Charlie/Delta que ya estaban cargados)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fondeadero:
    nombre: str
    puntos: list[tuple[str, str]]  # (latitud, longitud) por vertice
    nota: str = ""

    def texto_plano(self) -> str:
        lineas = [self.nombre.upper(), ""]
        for lat, lon in self.puntos:
            lineas.append(f"Latitud {lat} - Longitud {lon}")
        if self.nota:
            lineas.append("")
            lineas.append(self.nota)
        return "\n".join(lineas)


FONDEADEROS: list[Fondeadero] = [
    Fondeadero(
        "Fondeadero Alpha",
        [
            ("39º04'.17 S", "061º48'.60 W"),
            ("39º05'.20 S", "061º46'.48 W"),
            ("39º06'.35 S", "061º46'.60 W"),
            ("39º04'.87 S", "061º49'.20 W"),
        ],
        nota="The Anchorage Area ALPHA is reserved for inbound vessels with berthing prospect "
             "within 24 hs, under VTS advice.",
    ),
    Fondeadero(
        "Fondeadero Bravo",
        [
            ("39º03'.13 S", "061º50'.58 W"),
            ("39º04'.10 S", "061º48'.70 W"),
            ("39º04'.82 S", "061º49'.28 W"),
            ("39º03'.70 S", "061º51'.08 W"),
        ],
        nota="The Anchorage Area BRAVO will be used solely for outbound vessels with draft "
             "larger than 10 meters.",
    ),
    Fondeadero(
        "Fondeadero Charlie",
        [
            ("38º59'.10 S", "061º53'.90 W"),
            ("38º59'.50 S", "061º54'.20 W"),
            ("39º00'.30 S", "061º51'.10 W"),
            ("39º00'.55 S", "061º51'.70 W"),
        ],
    ),
    Fondeadero(
        "Fondeadero Delta",
        [
            ("38º58'.57 S", "061º55'.56 W"),
            ("38º59'.13 S", "061º55'.79 W"),
            ("38º59'.57 S", "061º54'.35 W"),
            ("38º59'.00 S", "061º54'.04 W"),
        ],
        nota="The Anchorage Area DELTA is reserved for those vessels with draft larger than "
             "10 meters not able to sail through the “Canal del Toro” for tide or "
             "meteorological reasons; bunker supply; or waiting berthing time.",
    ),
    Fondeadero(
        "Fondeadero Echo",
        [
            ("38º58'.57 S", "061º55'.56 W"),
            ("38º59'.13 S", "061º55'.79 W"),
            ("38º58'.07 S", "061º57'.32 W"),
            ("38º58'.60 S", "061º57'.61 W"),
        ],
        nota="The Anchorage Area ECHO is reserved for those vessels with draft larger than "
             "10 meters not able to sail through the “Canal del Toro” for tide or "
             "meteorological reasons and for laden tankers with draft larger than 10 meters or "
             "waiting berthing time at the single mooring buoys, and for LNG Carriers.",
    ),
    Fondeadero(
        "Fondeadero Outer",
        [
            ("39º17'.00 S", "061º36'.83 W"),
            ("39º17'.00 S", "061º30'.00 W"),
            ("39º19'.98 S", "061º32'.93 W"),
        ],
        nota="The Outer Anchorage Area is intended for vessels with no berthing prospect and "
             "should wait for more than one day at anchor or when the vessel should wait the "
             "clearance of the channel by the outbound traffic.",
    ),
]
