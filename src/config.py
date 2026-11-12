"""Carga y valida la configuración desde el archivo .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# El .env vive en la raíz del proyecto, sin importar el cwd con el que un
# cliente MCP lance el proceso.
_ROOT = Path(__file__).resolve().parent.parent


def _as_bool(raw: str, default: bool) -> bool:
    raw = raw.strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "si", "sí")


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    instance: str | None
    database: str | None
    user: str
    password: str
    trusted_connection: bool
    odbc_driver: str | None
    encrypt: bool
    trust_server_certificate: bool
    read_only: bool
    max_rows: int
    query_timeout_seconds: int

    @property
    def server(self) -> str:
        """Valor para la clave SERVER= del connection string ODBC."""
        if self.instance:
            return f"{self.host}\\{self.instance}"
        return f"{self.host},{self.port}"

    @property
    def dsn_target(self) -> str:
        """Descripción legible del destino (sin credenciales) para logs."""
        return f"{self.server}/{self.database or '(default)'}"

    @property
    def principal(self) -> str:
        """Identidad usada, para el log de auditoría."""
        return "windows-integrated" if self.trusted_connection else self.user


def load_settings(env_path: str | None = None) -> Settings:
    load_dotenv(dotenv_path=env_path or _ROOT / ".env", override=False)

    host = os.getenv("MSSQL_HOST", "").strip()
    port_raw = os.getenv("MSSQL_PORT", "1433").strip() or "1433"
    instance = os.getenv("MSSQL_INSTANCE", "").strip() or None
    database = os.getenv("MSSQL_DATABASE", "").strip() or None
    user = os.getenv("MSSQL_USER", "").strip()
    password = os.getenv("MSSQL_PASSWORD", "")
    trusted = _as_bool(os.getenv("MSSQL_TRUSTED_CONNECTION", ""), False)
    odbc_driver = os.getenv("MSSQL_ODBC_DRIVER", "").strip() or None
    encrypt = _as_bool(os.getenv("MSSQL_ENCRYPT", ""), True)
    trust_cert = _as_bool(os.getenv("MSSQL_TRUST_SERVER_CERTIFICATE", ""), True)
    # Solo "false" explícito desactiva el modo solo-lectura (igual que el MCP de Oracle).
    read_only = os.getenv("READ_ONLY", "true").strip().lower() != "false"
    max_rows_raw = os.getenv("MAX_ROWS", "200").strip() or "200"
    timeout_raw = os.getenv("QUERY_TIMEOUT_SECONDS", "30").strip() or "30"

    missing = []
    if not host:
        missing.append("MSSQL_HOST")
    if not trusted:
        if not user:
            missing.append("MSSQL_USER")
        if not password:
            missing.append("MSSQL_PASSWORD")
    if missing:
        raise ValueError(
            "Faltan variables de entorno requeridas en .env: "
            + ", ".join(missing)
            + " (o usa MSSQL_TRUSTED_CONNECTION=true)"
        )

    try:
        port = int(port_raw)
        max_rows = int(max_rows_raw)
        query_timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise ValueError(
            "MSSQL_PORT, MAX_ROWS y QUERY_TIMEOUT_SECONDS deben ser números enteros"
        ) from exc

    if max_rows < 1 or query_timeout_seconds < 0:
        raise ValueError("MAX_ROWS debe ser >= 1 y QUERY_TIMEOUT_SECONDS >= 0")

    return Settings(
        host=host,
        port=port,
        instance=instance,
        database=database,
        user=user,
        password=password,
        trusted_connection=trusted,
        odbc_driver=odbc_driver,
        encrypt=encrypt,
        trust_server_certificate=trust_cert,
        read_only=read_only,
        max_rows=max_rows,
        query_timeout_seconds=query_timeout_seconds,
    )
