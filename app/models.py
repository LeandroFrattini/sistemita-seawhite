from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

VESSEL_TYPES = ["Bulk Carrier", "Tanker"]
REPORT_FORMATS = ["EXCEL", "WBL_TEXT"]
LINEUP_KINDS = ["GRAIN", "FLAMMABLE"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    # permiso especifico (independiente de is_admin) para editar el
    # tarifario del Proformador -- se activa por perfil, no por rol
    is_pda_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # permiso especifico (independiente de is_admin) para entrar a la
    # seccion Administracion (Liquidaciones Aduana, etc.)
    is_administracion: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Segundo factor (TOTP). El secreto va cifrado; mientras totp_enabled sea
    # False y haya secreto, el usuario esta a mitad del alta (escaneo del QR).
    totp_secret_enc: Mapped[str] = mapped_column(Text, default="")
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int] = mapped_column(BigInteger, default=0)  # anti-replay
    totp_recovery: Mapped[str] = mapped_column(Text, default="")  # JSON de hashes

    @property
    def requires_2fa(self) -> bool:
        """Los perfiles con permisos sensibles no pueden trabajar sin segundo factor."""
        return bool(self.is_admin or self.is_administracion or self.is_pda_admin)


class Terminal(Base):
    __tablename__ = "terminals"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="GRAIN")  # GRAIN | FLAMMABLE
    # Texto que va en la primera celda del encabezado de la tabla (ej. "9TBB", "CARGILL")
    code: Mapped[str] = mapped_column(String(60))
    # Nombre largo para mostrar en la app
    name: Mapped[str] = mapped_column(String(120), default="")
    # Rótulo del muelle para el texto del formato WBL (ej. "Pier 9 TBB berth")
    berth_label: Mapped[str] = mapped_column(String(120), default="")
    # Nota de estado del muelle (flammable), ej. "OUT OF SERVICE SINCE ... "
    status_note: Mapped[str] = mapped_column(String(255), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # muelles/ubicaciones que se usan para armar legajos y mandar reportes
    # propios (ej. Otamerica, Boyas) pero no forman parte del line-up
    # "oficial" -- no van en el Excel ni en el line-up finalizado del dia
    exclude_from_excel: Mapped[bool] = mapped_column(Boolean, default=False)

    calls: Mapped[list["VesselCall"]] = relationship(
        back_populates="terminal", order_by="VesselCall.sort_order"
    )


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nombre que se carga en la columna PRINCIPAL / Otras agencias del line-up
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # Texto que aparece luego de "TO " en el mail (si queda vacío se usa name)
    to_name: Mapped[str] = mapped_column(String(120), default="")
    # Mails separados por coma o salto de linea
    emails: Mapped[str] = mapped_column(Text, default="")
    report_format: Mapped[str] = mapped_column(String(20), default="EXCEL")
    # AGENCY (recibe line-up diario + reportes de Barcos) | ESTIBA (solo
    # reportes de Barcos: Berthing/Commenced Loading/Loading Shifts/Sailed)
    client_type: Mapped[str] = mapped_column(String(20), default="AGENCY")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    @property
    def display_to(self) -> str:
        return (self.to_name or self.name).strip()

    @property
    def is_estiba(self) -> bool:
        return self.client_type == "ESTIBA"

    @property
    def email_list(self) -> list[str]:
        raw = (self.emails or "").replace(";", ",").replace("\n", ",")
        return [e.strip() for e in raw.split(",") if e.strip()]


class Lineup(Base):
    __tablename__ = "lineups"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="GRAIN")  # GRAIN | FLAMMABLE
    port_name: Mapped[str] = mapped_column(String(120), default="")
    # Aviso puntual (puerto cerrado por viento, paro, etc.) -- si tiene algo
    # cargado sale al pie de todos los reportes de linea-up de ese dia y al
    # pie de los dos Excel (interno y clientes), asi no hay que copiarlo a
    # mano en cada reporte.
    notice: Mapped[str] = mapped_column(String(255), default="")
    lineup_date: Mapped[str] = mapped_column(String(10), default="")  # dd/mm/yy
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | archived
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str] = mapped_column(String(120), default="")

    calls: Mapped[list["VesselCall"]] = relationship(
        back_populates="lineup", cascade="all, delete-orphan"
    )


class VesselCall(Base):
    __tablename__ = "vessel_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    lineup_id: Mapped[int] = mapped_column(ForeignKey("lineups.id"), index=True)
    terminal_id: Mapped[int] = mapped_column(ForeignKey("terminals.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    vessel_name: Mapped[str] = mapped_column(String(120), default="")
    vessel_type: Mapped[str] = mapped_column(String(40), default="Bulk Carrier")
    imo: Mapped[str] = mapped_column(String(20), default="")

    # Se guardan tal cual se tipean: pueden ser fecha (dd/mm/yy) o texto
    # ("At roads", "Alongside", ""). El recalculo reescribe etb/etc como fecha.
    eta: Mapped[str] = mapped_column(String(40), default="")
    etb: Mapped[str] = mapped_column(String(40), default="")
    etc: Mapped[str] = mapped_column(String(40), default="")

    operation: Mapped[str] = mapped_column(String(30), default="Load")
    quantity: Mapped[str] = mapped_column(String(40), default="")
    grade: Mapped[str] = mapped_column(String(60), default="")
    shipper: Mapped[str] = mapped_column(String(60), default="")
    destination: Mapped[str] = mapped_column(String(60), default="")

    local_agent: Mapped[str] = mapped_column(String(80), default="")
    principal_text: Mapped[str] = mapped_column(String(120), default="")
    principal_client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True
    )

    is_ours: Mapped[bool] = mapped_column(Boolean, default=False)
    second_call: Mapped[bool] = mapped_column(Boolean, default=False)  # flammable "2ND CALL"
    # False para barcos que solo cuentan para el recuento (ej. bunker en
    # Boya 11) y no necesitan legajo/reportes en Barcos (ID)
    needs_report: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    lineup: Mapped["Lineup"] = relationship(back_populates="calls")
    terminal: Mapped["Terminal"] = relationship(back_populates="calls")
    principal_client: Mapped["Client | None"] = relationship()
    extra_agencies: Mapped[list["VesselExtraAgency"]] = relationship(
        back_populates="vessel_call", cascade="all, delete-orphan"
    )

    @property
    def principal_name(self) -> str:
        if self.principal_client:
            return self.principal_client.name
        return self.principal_text or ""

    @property
    def extra_agency_ids(self) -> set[int]:
        return {link.client_id for link in self.extra_agencies}

    @property
    def display_client_count(self) -> int:
        """Cantidad a mostrar en el chip "N clientes" -- si el barco es
        nuestro, el principal ya recibe el mail solo (ver recipient_clients),
        asi que cuenta como uno mas aunque no este en extra_agencies."""
        ids = self.extra_agency_ids
        if self.is_ours and self.principal_client_id and self.principal_client_id not in ids:
            return len(ids) + 1
        return len(ids)

    def recipient_clients(self) -> list["Client"]:
        out: list[Client] = []
        seen: set[int] = set()
        if self.principal_client and self.principal_client.active:
            out.append(self.principal_client)
            seen.add(self.principal_client.id)
        for link in self.extra_agencies:
            c = link.client
            if c and c.active and c.id not in seen:
                out.append(c)
                seen.add(c.id)
        return out


class VesselExtraAgency(Base):
    __tablename__ = "vessel_extra_agencies"
    __table_args__ = (UniqueConstraint("vessel_call_id", "client_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_call_id: Mapped[int] = mapped_column(
        ForeignKey("vessel_calls.id"), index=True
    )
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)

    vessel_call: Mapped["VesselCall"] = relationship(back_populates="extra_agencies")
    client: Mapped["Client"] = relationship()


class ArchivedLineup(Base):
    __tablename__ = "archived_lineups"

    id: Mapped[int] = mapped_column(primary_key=True)
    lineup_date: Mapped[str] = mapped_column(String(10), default="")
    archived_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    archived_by: Mapped[str] = mapped_column(String(120), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class OperatedVessel(Base):
    """Snapshot de un barco propio cuando se lo saca del line-up (la X).
    Queda como historico en la pantalla "Nuestros barcos" -> Operados."""

    __tablename__ = "operated_vessels"

    id: Mapped[int] = mapped_column(primary_key=True)
    operated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    removed_by: Mapped[str] = mapped_column(String(120), default="")
    lineup_date: Mapped[str] = mapped_column(String(10), default="")
    period: Mapped[str] = mapped_column(String(7), default="")  # YYYY-MM para el recuento

    terminal_code: Mapped[str] = mapped_column(String(40), default="")
    berth_label: Mapped[str] = mapped_column(String(120), default="")

    vessel_name: Mapped[str] = mapped_column(String(120), default="")
    vessel_type: Mapped[str] = mapped_column(String(40), default="")
    imo: Mapped[str] = mapped_column(String(20), default="")
    eta: Mapped[str] = mapped_column(String(40), default="")
    etb: Mapped[str] = mapped_column(String(40), default="")
    etc: Mapped[str] = mapped_column(String(40), default="")
    operation: Mapped[str] = mapped_column(String(30), default="")
    quantity: Mapped[str] = mapped_column(String(40), default="")
    grade: Mapped[str] = mapped_column(String(60), default="")
    shipper: Mapped[str] = mapped_column(String(60), default="")
    destination: Mapped[str] = mapped_column(String(60), default="")
    local_agent: Mapped[str] = mapped_column(String(80), default="")
    principal: Mapped[str] = mapped_column(String(120), default="")
    extras: Mapped[str] = mapped_column(String(255), default="")


VESSEL_REPORT_TYPES = [
    ("BERTHING", "Berthing"),
    ("COMMENCED_LOADING", "Commenced Loading/Discharging"),
    ("LOADING_SHIFTS", "Loading/Discharging Shift"),
    ("SAILED", "Sailed"),
]


class VesselFile(Base):
    """Legajo de un barco propio: se crea al marcarlo "Nuestro" y persiste
    aunque el line-up se reimporte a diario. Se cierra al mandar el reporte
    Sailed (o a mano); si el barco vuelve mas adelante, le toca un ID nuevo."""

    __tablename__ = "vessel_files"

    id: Mapped[int] = mapped_column(primary_key=True)  # el Nº 1, 2, 3... que ve el usuario
    kind: Mapped[str] = mapped_column(String(20), default="GRAIN")
    vessel_name: Mapped[str] = mapped_column(String(120), default="")
    vessel_type: Mapped[str] = mapped_column(String(40), default="")

    terminal_id: Mapped[int | None] = mapped_column(ForeignKey("terminals.id"), nullable=True)
    terminal_code: Mapped[str] = mapped_column(String(60), default="")

    principal_client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    principal_text: Mapped[str] = mapped_column(String(120), default="")

    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opened_by: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    # historial acumulado (clientes WBL): se reimprime completo al pie de
    # cada reporte que lo tilde -- se edita/completa a mano en el legajo
    statement_of_facts: Mapped[str] = mapped_column(Text, default="")

    terminal: Mapped["Terminal | None"] = relationship()
    principal_client: Mapped["Client | None"] = relationship()
    agencies: Mapped[list["VesselFileAgency"]] = relationship(cascade="all, delete-orphan")
    cargos: Mapped[list["VesselCargo"]] = relationship(
        cascade="all, delete-orphan", order_by="VesselCargo.sort_order, VesselCargo.id"
    )
    sof_entries: Mapped[list["SofEntry"]] = relationship(
        cascade="all, delete-orphan", order_by="SofEntry.event_date, SofEntry.time_from, SofEntry.id"
    )
    reports: Mapped[list["VesselReport"]] = relationship(
        back_populates="vessel_file", cascade="all, delete-orphan",
        order_by="VesselReport.sent_at.desc()",
    )

    @property
    def principal_name(self) -> str:
        return self.principal_client.name if self.principal_client else (self.principal_text or "")

    def recipient_clients(self) -> list["Client"]:
        out: list[Client] = []
        seen: set[int] = set()
        if self.principal_client and self.principal_client.active:
            out.append(self.principal_client)
            seen.add(self.principal_client.id)
        for link in self.agencies:
            c = link.client
            if c and c.active and c.id not in seen:
                out.append(c)
                seen.add(c.id)
        return out


class VesselCargo(Base):
    """Mercaderia de un legajo (grado + Stowage Plan declarado por el
    master). Se carga una vez y se reusa en todos los Loading Shifts de
    ese barco; algunos barcos llevan mas de una (multi-grado)."""

    __tablename__ = "vessel_cargos"

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_file_id: Mapped[int] = mapped_column(ForeignKey("vessel_files.id"), index=True)
    grade: Mapped[str] = mapped_column(String(80), default="")  # ej. "CORN in Bulk"
    stowage_plan: Mapped[float] = mapped_column(Float, default=0)  # MT, "as per declared by master"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class SofEntry(Base):
    """Un evento del Statement of Facts (clientes WBL), cargado uno por uno
    desde el popup del legajo -- fecha, horario y texto. Se van acumulando
    solos y se reimprimen completos al pie del reporte cuando se tilda
    "Incluir Statement of Facts"."""

    __tablename__ = "sof_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_file_id: Mapped[int] = mapped_column(ForeignKey("vessel_files.id"), index=True)
    event_date: Mapped[str] = mapped_column(String(10), default="")  # dd/mm/yy
    time_from: Mapped[str] = mapped_column(String(10), default="")
    time_to: Mapped[str] = mapped_column(String(10), default="")
    category: Mapped[str] = mapped_column(String(40), default="")
    location: Mapped[str] = mapped_column(String(80), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VesselFileAgency(Base):
    __tablename__ = "vessel_file_agencies"
    __table_args__ = (UniqueConstraint("vessel_file_id", "client_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_file_id: Mapped[int] = mapped_column(ForeignKey("vessel_files.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)

    client: Mapped["Client"] = relationship()


class VesselReport(Base):
    """Un reporte operativo mandado para un legajo (Berthing / Commenced
    Loading / Loading Shifts / Sailed, combinables)."""

    __tablename__ = "vessel_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    vessel_file_id: Mapped[int] = mapped_column(ForeignKey("vessel_files.id"), index=True)
    # un mismo "Generar reporte" arma un mail por cliente -- todos comparten
    # este id para poder borrarlos/identificarlos juntos (son el mismo evento)
    batch_id: Mapped[str] = mapped_column(String(40), default="", index=True)
    report_types: Mapped[str] = mapped_column(String(120), default="")  # coma-separados
    event_at: Mapped[str] = mapped_column(String(40), default="")
    figure: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    # datos estructurados del turno (Loading Shifts): cargo, horario, bodegas
    # cargadas en ESTE turno, etc. -- JSON, ver reports.py:_ShiftInput
    shift_data: Mapped[str] = mapped_column(Text, default="")

    subject: Mapped[str] = mapped_column(String(200), default="")
    text_body: Mapped[str] = mapped_column(Text, default="")
    html_body: Mapped[str] = mapped_column(Text, default="")
    to_emails: Mapped[str] = mapped_column(Text, default="")
    cc_emails: Mapped[str] = mapped_column(Text, default="")

    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_by: Mapped[str] = mapped_column(String(120), default="")

    vessel_file: Mapped["VesselFile"] = relationship(back_populates="reports")

    @property
    def type_list(self) -> list[str]:
        return [t for t in self.report_types.split(",") if t]

    @property
    def to_list(self) -> list[str]:
        return [e.strip() for e in self.to_emails.split(",") if e.strip()]

    @property
    def cc_list(self) -> list[str]:
        return [e.strip() for e in self.cc_emails.split(",") if e.strip()]


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class EventTemplate(Base):
    """Frase reutilizable para armar Statement of Facts / reportes de
    Barcos (ID) (ej. "Awaiting shore readiness." - categoria DELAYS). Se
    busca desde el legajo del barco y se inserta en el cuadro de texto,
    despues se edita a mano lo que haga falta (fechas, nombres, etc)."""

    __tablename__ = "event_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(40), default="")  # DELAYS | OPERATION | BUNKERS | STATUS | ...
    text: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Proforma(Base):
    """Un PDA armado con el Proformador (wizard de 5 pasos). No depende de
    una Escala/VesselCall -- se puede armar para un barco TBN antes de que
    exista un call real en el line-up."""

    __tablename__ = "proformas"

    id: Mapped[int] = mapped_column(primary_key=True)
    dolar_venta: Mapped[float] = mapped_column(Float, default=0)
    cliente: Mapped[str] = mapped_column(String(200), default="")
    tipo_buque: Mapped[str] = mapped_column(String(30), default="Bulk Carrier")
    tipo_operacion: Mapped[str] = mapped_column(String(20), default="Carga")
    nombre_buque: Mapped[str] = mapped_column(String(150), default="MV TBN")
    eslora: Mapped[float] = mapped_column(Float, default=0)
    manga: Mapped[float] = mapped_column(Float, default=0)
    puntal: Mapped[float] = mapped_column(Float, default=0)
    fc: Mapped[float | None] = mapped_column(Float, nullable=True)
    trn: Mapped[float] = mapped_column(Float, default=0)
    calado: Mapped[float] = mapped_column(Float, default=0)  # legacy, ver calado_entrada/salida
    calado_entrada: Mapped[float] = mapped_column(Float, default=0)  # pies, pilotaje de entrada
    calado_salida: Mapped[float] = mapped_column(Float, default=0)  # pies, pilotaje de salida
    cantidad: Mapped[float] = mapped_column(Float, default=0)
    dias_muelle: Mapped[float] = mapped_column(Float, default=0)
    dias_fondeo: Mapped[float] = mapped_column(Float, default=0)
    cantidad_remolques: Mapped[int] = mapped_column(Integer, default=0)  # legacy, ver remolques_in/out
    remolques_in: Mapped[int] = mapped_column(Integer, default=0)
    remolques_out: Mapped[int] = mapped_column(Integer, default=0)
    turnos: Mapped[float] = mapped_column(Float, default=0)
    tipo_carga: Mapped[str] = mapped_column(String(30), default="ACEITE")
    categoria_watchmen: Mapped[str] = mapped_column(String(30), default="NORMAL")
    dia_tipo: Mapped[str] = mapped_column(String(20), default="SEMANA")
    procede_exterior: Mapped[bool] = mapped_column(Boolean, default=True)
    destino_exterior: Mapped[bool] = mapped_column(Boolean, default=True)
    immigration_in_boya: Mapped[bool] = mapped_column(Boolean, default=False)
    immigration_out_boya: Mapped[bool] = mapped_column(Boolean, default=False)
    total_usd: Mapped[float] = mapped_column(Float, default=0)
    creado_por: Mapped[str] = mapped_column(String(120), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["ProformaLinea"]] = relationship(
        back_populates="proforma", cascade="all, delete-orphan", order_by="ProformaLinea.orden"
    )


class ProformaLinea(Base):
    __tablename__ = "proforma_lineas"

    id: Mapped[int] = mapped_column(primary_key=True)
    proforma_id: Mapped[int] = mapped_column(ForeignKey("proformas.id"), index=True)
    concepto: Mapped[str] = mapped_column(String(200), default="")
    monto_usd: Mapped[float] = mapped_column(Float, default=0)
    observacion: Mapped[str] = mapped_column(String(300), default="")
    informativo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    proforma: Mapped["Proforma"] = relationship(back_populates="items")


# --- formulas del Proformador: visibles a todos, editables solo admin o
# usuarios con is_pda_admin (ver /proformador/formulas) --------------------
class ProformaParametro(Base):
    __tablename__ = "proforma_parametros"

    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(80), unique=True)
    etiqueta: Mapped[str] = mapped_column(String(200), default="")
    valor: Mapped[float] = mapped_column(Float, default=0)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ProformaCoefTramo(Base):
    __tablename__ = "proforma_coef_tramos"

    id: Mapped[int] = mapped_column(primary_key=True)
    hasta_toneladas: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = ultimo tramo
    coeficiente: Mapped[float] = mapped_column(Float, default=1)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ProformaTugTarifa(Base):
    __tablename__ = "proforma_tug_tarifas"

    id: Mapped[int] = mapped_column(primary_key=True)
    hasta_loa: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = ultimo tramo
    valor_usd: Mapped[float] = mapped_column(Float, default=0)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ProformaPilotageTramo(Base):
    """Tarifa de pilotaje/practicaje por tramo de calado (pies). Cargada
    solo para el recorrido mas comun (Extranjero, I.White-Profertil, 1
    practico) -- tarifario ESEM, sacado de la columna TOTAL. Otros
    recorridos/banderas/2 practicos quedan afuera por ahora."""

    __tablename__ = "proforma_pilotage_tramos"

    id: Mapped[int] = mapped_column(primary_key=True)
    hasta_pies: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = ultimo tramo
    valor_usd: Mapped[float] = mapped_column(Float, default=0)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ProformaTarifaTurno(Base):
    __tablename__ = "proforma_tarifas_turno"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio: Mapped[str] = mapped_column(String(20), default="")  # SERENO | TALLY
    categoria: Mapped[str] = mapped_column(String(30), default="")
    dia_tipo: Mapped[str] = mapped_column(String(20), default="")  # SEMANA | SABADO | DOMINGO_FERIADO
    valor_ars_dia: Mapped[float] = mapped_column(Float, default=0)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ProformaConceptoFijo(Base):
    __tablename__ = "proforma_conceptos_fijos"

    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str | None] = mapped_column(String(60), nullable=True)  # ej "immigration_in"
    nombre: Mapped[str] = mapped_column(String(200), default="")
    valor_usd: Mapped[float] = mapped_column(Float, default=0)
    condicion: Mapped[str] = mapped_column(String(200), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class ReportLog(Base):
    __tablename__ = "report_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    generated_by: Mapped[str] = mapped_column(String(120), default="")
    lineup_date: Mapped[str] = mapped_column(String(10), default="")
    vessel_name: Mapped[str] = mapped_column(String(120), default="")
    client_name: Mapped[str] = mapped_column(String(120), default="")
    to_emails: Mapped[str] = mapped_column(Text, default="")
    report_format: Mapped[str] = mapped_column(String(20), default="EXCEL")
    status: Mapped[str] = mapped_column(String(30), default="generated")


# --- PROFORMADOR DE BUNKER (Boya 3 / Boya 11 / Boya 17) -------------------
class ProformaBunker(Base):
    __tablename__ = "proforma_bunkers"

    id: Mapped[int] = mapped_column(primary_key=True)
    dolar_venta: Mapped[float] = mapped_column(Float, default=0)
    cliente: Mapped[str] = mapped_column(String(200), default="")
    nombre_buque: Mapped[str] = mapped_column(String(150), default="MV TBN")
    boya: Mapped[str] = mapped_column(String(10), default="BOYA_11")  # BOYA_3 | BOYA_11 | BOYA_17

    eslora: Mapped[float] = mapped_column(Float, default=0)
    manga: Mapped[float] = mapped_column(Float, default=0)
    puntal: Mapped[float] = mapped_column(Float, default=0)
    fc: Mapped[float | None] = mapped_column(Float, nullable=True)
    trn: Mapped[float] = mapped_column(Float, default=0)
    calado_entrada: Mapped[float] = mapped_column(Float, default=0)
    calado_salida: Mapped[float] = mapped_column(Float, default=0)

    dias_estadia: Mapped[float] = mapped_column(Float, default=1)  # para Anchor Dues (Boya 11/17)
    cantidad_barcazas: Mapped[int] = mapped_column(Integer, default=1)  # para OSRO
    turnos_customs_clearance: Mapped[float] = mapped_column(Float, default=2)
    turnos_customs_bunker_control: Mapped[float] = mapped_column(Float, default=4)
    usa_boat_surveyor: Mapped[bool] = mapped_column(Boolean, default=False)
    horas_boat_surveyor: Mapped[float] = mapped_column(Float, default=0)
    turnos_sipa: Mapped[float] = mapped_column(Float, default=6)  # solo Boya 3, turnos de 4hs

    procede_exterior: Mapped[bool] = mapped_column(Boolean, default=True)
    destino_exterior: Mapped[bool] = mapped_column(Boolean, default=True)

    total_usd: Mapped[float] = mapped_column(Float, default=0)
    creado_por: Mapped[str] = mapped_column(String(120), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["ProformaBunkerLinea"]] = relationship(
        back_populates="proforma", cascade="all, delete-orphan", order_by="ProformaBunkerLinea.orden"
    )


class ProformaBunkerLinea(Base):
    __tablename__ = "proforma_bunker_lineas"

    id: Mapped[int] = mapped_column(primary_key=True)
    proforma_id: Mapped[int] = mapped_column(ForeignKey("proforma_bunkers.id"), index=True)
    concepto: Mapped[str] = mapped_column(String(200), default="")
    monto_usd: Mapped[float] = mapped_column(Float, default=0)
    observacion: Mapped[str] = mapped_column(String(300), default="")
    informativo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    proforma: Mapped["ProformaBunker"] = relationship(back_populates="items")


class ProformaBunkerBoya(Base):
    """Configuracion propia de cada boya (visible/editable en Formulas)."""

    __tablename__ = "proforma_bunker_boyas"

    id: Mapped[int] = mapped_column(primary_key=True)
    boya: Mapped[str] = mapped_column(String(10), unique=True)  # BOYA_3 | BOYA_11 | BOYA_17
    etiqueta: Mapped[str] = mapped_column(String(40), default="")
    osro_usd: Mapped[float] = mapped_column(Float, default=0)
    boat_trip_usd: Mapped[float] = mapped_column(Float, default=0)  # boat/s for BQS surveyor, por viaje
    boat_hora_usd: Mapped[float] = mapped_column(Float, default=0)  # si queda al costado
    cobra_channel_anchor: Mapped[bool] = mapped_column(Boolean, default=False)
    cobra_pilotage: Mapped[bool] = mapped_column(Boolean, default=False)
    cobra_sipa: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)


# --- PROFORMADOR DE OTAMERICA (Sitio 1 / Sitio 2, carga de crudo) ---------
class ProformaOtamerica(Base):
    """PDA para Otamerica (terminal de crudo, Sitio 1/2). Reutiliza casi
    todas las formulas de la proforma de Carga/Descarga (pilotaje monoboya,
    channel toll, free pratique, watchmen, conceptos fijos) salvo Head
    Tally Clerk, mas los conceptos propios de la terminal: Wharfage con
    tarifa propia (0.07 x TRN en vez de 0.46), ISPS, Amarre/Desamarre,
    Barreras de contencion y Remolcadores (tarifa propia por LOA)."""

    __tablename__ = "proforma_otamericas"

    id: Mapped[int] = mapped_column(primary_key=True)
    dolar_venta: Mapped[float] = mapped_column(Float, default=0)
    cliente: Mapped[str] = mapped_column(String(200), default="")
    sitio: Mapped[str] = mapped_column(String(10), default="SITIO_1")  # SITIO_1 | SITIO_2
    nombre_buque: Mapped[str] = mapped_column(String(150), default="MV TBN")

    eslora: Mapped[float] = mapped_column(Float, default=0)
    manga: Mapped[float] = mapped_column(Float, default=0)
    puntal: Mapped[float] = mapped_column(Float, default=0)
    fc: Mapped[float | None] = mapped_column(Float, nullable=True)
    trn: Mapped[float] = mapped_column(Float, default=0)
    desplazamiento: Mapped[float] = mapped_column(Float, default=0)  # tns, clasifica Panamax/Aframax/Suezmax
    calado_entrada: Mapped[float] = mapped_column(Float, default=0)
    calado_salida: Mapped[float] = mapped_column(Float, default=0)
    cantidad: Mapped[float] = mapped_column(Float, default=0)  # cantidad cargada (tn), para Channel Toll e ISPS

    dias_muelle: Mapped[float] = mapped_column(Float, default=0)  # Wharfage, Watchmen, Barreras
    categoria_watchmen: Mapped[str] = mapped_column(String(30), default="NORMAL")
    dia_tipo: Mapped[str] = mapped_column(String(20), default="SEMANA")
    procede_exterior: Mapped[bool] = mapped_column(Boolean, default=True)
    destino_exterior: Mapped[bool] = mapped_column(Boolean, default=True)

    total_usd: Mapped[float] = mapped_column(Float, default=0)
    creado_por: Mapped[str] = mapped_column(String(120), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["ProformaOtamericaLinea"]] = relationship(
        back_populates="proforma", cascade="all, delete-orphan", order_by="ProformaOtamericaLinea.orden"
    )


class ProformaOtamericaLinea(Base):
    __tablename__ = "proforma_otamerica_lineas"

    id: Mapped[int] = mapped_column(primary_key=True)
    proforma_id: Mapped[int] = mapped_column(ForeignKey("proforma_otamericas.id"), index=True)
    concepto: Mapped[str] = mapped_column(String(200), default="")
    monto_usd: Mapped[float] = mapped_column(Float, default=0)
    observacion: Mapped[str] = mapped_column(String(300), default="")
    informativo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    proforma: Mapped["ProformaOtamerica"] = relationship(back_populates="items")


class ProformaOtaRemolcadorTarifa(Base):
    """Tarifa de remolcadores propia de Otamerica, por tramo de LOA (m)."""

    __tablename__ = "proforma_ota_remolcador_tarifas"

    id: Mapped[int] = mapped_column(primary_key=True)
    hasta_loa: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = ultimo tramo
    valor_usd: Mapped[float] = mapped_column(Float, default=0)
    orden: Mapped[int] = mapped_column(Integer, default=0)
