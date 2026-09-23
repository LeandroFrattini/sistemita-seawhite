"""Plantillas de costos de referencia (Utilidades) -- info fija que se
consulta cuando alguien pregunta un precio (crew change, estiba de
provisiones, botes, etc). No calculan nada ni se editan desde la app:
cuando cambian los valores, se actualiza esta lista y se pushea.

Para agregar una plantilla nueva, sumar un PlantillaCosto() a PLANTILLAS
-- con `grupos` (listas de items, tipo "On-signer: taxi X = 99 USD") o
con `tabla` (comparacion por columnas, tipo tarifa por terminal), lo que
mejor represente el original."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ItemCosto:
    label: str
    valor: str
    es_alternativa: bool = False  # precedido por "O" (alternativa al item de arriba)


@dataclass
class GrupoItems:
    titulo: str
    items: list[ItemCosto]
    nota: str = ""  # va pegada a este grupo especifico (no al pie de toda la plantilla)


@dataclass
class TablaCosto:
    columnas: list[str]
    filas: list[tuple[str, list[str]]]  # (rotulo de fila, [valor por columna])


@dataclass
class PlantillaCosto:
    slug: str
    titulo: str
    actualizado: str = ""
    grupos: list[GrupoItems] = field(default_factory=list)
    tabla: TablaCosto | None = None
    nota: str = ""

    def texto_plano(self) -> str:
        """Todo el contenido de `grupos` armado como el mensaje de texto
        que se manda tal cual (para el boton "Copiar" de la plantilla)."""
        lineas = [self.titulo.upper()]
        for g in self.grupos:
            lineas.append("")
            if g.titulo:
                lineas.append(g.titulo.upper() + ":")
            for it in g.items:
                prefijo = "O " if it.es_alternativa else ""
                lineas.append(f"{prefijo}{it.label}: {it.valor}")
            if g.nota:
                lineas.append("")
                lineas.append(g.nota)
        if self.nota:
            lineas.append("")
            lineas.append(self.nota)
        return "\n".join(lineas)


PLANTILLAS: list[PlantillaCosto] = [
    PlantillaCosto(
        slug="crew-change-bahia-blanca",
        titulo="Crew Change en Bahía Blanca",
        actualizado="14/08/2026",
        grupos=[
            GrupoItems("On-signer", [
                ItemCosto("1 taxi: Local airport - Hotel", "99 USD"),
                ItemCosto("1 taxi: Hotel - Authorities - Vessel", "176 USD"),
                ItemCosto("1 taxi: Local airport - Authorities - Vessel", "227 USD", es_alternativa=True),
                ItemCosto("Taxi trip to perform embarking procedures", "122 USD"),
            ]),
            GrupoItems("Off-signer", [
                ItemCosto("1 taxi: Vessel - Authorities - Hotel", "176 USD"),
                ItemCosto("1 taxi: Hotel - Local airport", "99 USD"),
                ItemCosto("1 taxi: Vessel - Authorities - Local airport", "227 USD", es_alternativa=True),
                ItemCosto("Taxi trip to perform disembarking procedures", "121 USD"),
            ]),
        ],
    ),
    PlantillaCosto(
        slug="crew-change-rosales",
        titulo="Crew Change en Rosales",
        actualizado="14/08/2026",
        grupos=[
            GrupoItems("On-signer", [
                ItemCosto("1 taxi: Local airport - Hotel", "99 USD"),
                ItemCosto("1 taxi: Hotel - Authorities - Rosales", "245 USD"),
                ItemCosto("1 taxi: Local airport - Authorities - Rosales", "302 USD", es_alternativa=True),
                ItemCosto("Taxi trip to perform embarking procedures", "121 USD"),
            ]),
            GrupoItems("Off-signer", [
                ItemCosto("1 taxi: Rosales - Authorities - Hotel", "245 USD"),
                ItemCosto("1 taxi: Hotel - Local airport", "99 USD"),
                ItemCosto("1 taxi: Rosales - Authorities - Local airport", "302 USD", es_alternativa=True),
                ItemCosto("Taxi trip to perform disembarking procedures", "121 USD"),
            ]),
        ],
    ),
    PlantillaCosto(
        slug="estiba-botes-grua-muelle",
        titulo="Estiba, botes y grúa de muelle",
        grupos=[
            GrupoItems(
                "Stevedore services — charges per shift (6 hours) nwh",
                [
                    ItemCosto("0-45 Kgs", "USD 760"),
                    ItemCosto("45-100 kgs", "USD 1,000"),
                    ItemCosto("100-200 kgs", "USD 1,250"),
                    ItemCosto("200-500 kgs", "USD 2,050"),
                    ItemCosto("500-1000 kgs", "USD 2,500"),
                    ItemCosto("1000-3000 kgs", "USD 3,240"),
                    ItemCosto("3000-5000 kgs", "USD 4,860"),
                    ItemCosto("> 5000 kgs", "USD 5,400"),
                ],
                nota="If in overtime (mon/fri 1900/0700 + sat 1300/2400 + sun & hol 0000/2400): 100% surcharge.",
            ),
            GrupoItems("Boat services expenses", [
                ItemCosto("Boat service (up to 3 tonnes) - flat tariff", "USD 1,950.-"),
                ItemCosto("Waiting time alongside", "USD 150 per hour"),
            ]),
            GrupoItems("Shore crane expenses", [
                ItemCosto("Per shift of 6 hours - flat tariff", "USD 1,200.-"),
            ]),
        ],
    ),
    PlantillaCosto(
        slug="estibas-provistas-repuestos-lubs-materiales",
        titulo="Estibas provistas, repuestos, lubs y materiales",
        tabla=TablaCosto(
            columnas=["Blue Star / Oceanway", "Atlas / Otros", "AMI"],
            filas=[
                ("0-45 kgs", ["USD 570", "USD 760", "USD 800"]),
                ("45-100 kgs", ["USD 750", "USD 1,000", "USD 1,050"]),
                ("100-200 kgs", ["USD 937", "USD 937", "USD 1,320"]),
                ("200-500 kgs", ["USD 1,537", "USD 2,050", "USD 2,160"]),
                ("500-1000 kgs", ["USD 1,875", "USD 2,500", "USD 2,650"]),
                ("1000-3000 kgs", ["USD 2,430", "USD 3,240", "USD 3,450"]),
                ("3000-5000 kgs", ["USD 3,645", "USD 4,860", "USD 5,150"]),
                ("> 5000 kgs", ["USD 4,050", "USD 5,400", "USD 5,700"]),
            ],
        ),
        nota="Tener en cuenta al cotizar: aclarar que para los 4 primeros casos (entre 0 y 500 kilos) "
             "al momento de la operación se ajustarán los valores en función de cantidad de bultos / "
             "lugar de embarque / requerimiento de personal de estiba.",
    ),
]
