from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    secret_key: str = "cambia-esto-en-produccion-por-favor-1234567890"
    database_url: str = f"sqlite:///{(DATA_DIR / 'lineup.db').as_posix()}"

    # Cabecera del Excel / puerto
    port_name: str = "BAHIA BLANCA PORT"
    windguru_label: str = "Windguru - Bahia Blanca"
    windguru_url: str = "https://www.windguru.cz/220832"

    # Nombre base de archivo. El export interno usa el nombre completo,
    # el export para clientes le quita la primera palabra.
    internal_filename_prefix: str = "HEINLEIN GRAIN TERMINALS LINE UP"
    client_filename_prefix: str = "GRAIN TERMINALS LINE UP"

    # Remitente que figura en los mails ("FM SEA WHITE")
    mail_from_name: str = "SEA WHITE"
    mail_from_address: str = ""  # opcional, se usa en el .eml si se completa

    # Pie de los reportes
    report_footer: str = (
        "PROSPECTS AS INFORMED BY TERMINAL, SUBJECT SHIPPER LOGISTICS, "
        "O/TIME ARRANGEMENTS, FAVOURABLE TIDES, AGW WP UCE WOG TBC."
    )

    # Primer usuario administrador que se crea al iniciar por primera vez
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str = "admin"

    # Verificacion en dos pasos (TOTP). Apagada por defecto: para encenderla,
    # definir la variable de entorno MFA_ENABLED=true. Apagada, nadie esta
    # obligado a activarla, el login no pide codigo y no se muestran las pantallas.
    mfa_enabled: bool = False


settings = Settings()
