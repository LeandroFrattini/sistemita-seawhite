"""Coordenadas de referencia de las areas de fondeo (Utilidades). Info
fija, se actualiza editando esta lista -- mismo criterio que
costos_templates.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fondeadero:
    nombre: str
    puntos: list[str]

    def texto_plano(self) -> str:
        return "\n".join([self.nombre.upper(), ""] + self.puntos)


FONDEADEROS: list[Fondeadero] = [
    Fondeadero("Fondeadero Charlie", [
        "38º59',10 S   061º53',90 W",
        "38º59',50 S   061º54',20 W",
        "39º00',30 S   061º51',10 W",
        "39º00',55 S   061º51',70 W",
    ]),
    Fondeadero("Fondeadero Delta", [
        "38º58',57 S   061º55',56 W",
        "38º59',13 S   061º55',79 W",
        "38º59',57 S   061º54',35 W",
        "38º59',00 S   061º54',04 W",
    ]),
    Fondeadero("Fondeadero Echo", [
        "Latitud 38º 58´ 34´´ S - Longitud 061º 55´ 33´´ W",
        "Latitud 38º 59´ 07´´ S - Longitud 061º 55´ 47´´ W",
        "Latitud 38º 58´ 04´´ S - Longitud 061º 57´ 19´´ W",
        "Latitud 38º 58´ 35´´ S - Longitud 061º 57´ 36´´ W",
    ]),
    Fondeadero("Fondeadero Alpha y Beta", [
        "LAT 39 04 10 S - LON 61 48 36 W",
        "LAT 39 05 12 S - LON 61 46 29 W",
        "LAT 39 06 21 S - LON 61 46 36 W",
        "LAT 39 04 52 S - LON 61 49 12 W",
    ]),
]
