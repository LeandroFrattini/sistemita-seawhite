from datetime import datetime

from sqlalchemy import (
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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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

    terminal: Mapped["Terminal | None"] = relationship()
    principal_client: Mapped["Client | None"] = relationship()
    agencies: Mapped[list["VesselFileAgency"]] = relationship(cascade="all, delete-orphan")
    cargos: Mapped[list["VesselCargo"]] = relationship(
        cascade="all, delete-orphan", order_by="VesselCargo.sort_order, VesselCargo.id"
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
