"""Conexión a SQL Server vía pyodbc."""

import re
from contextlib import contextmanager

import pyodbc

from .config import Settings

_DRIVER_RE = re.compile(r"^ODBC Driver (\d+) for SQL Server$")


def detect_driver() -> str:
    """Devuelve el 'ODBC Driver NN for SQL Server' más nuevo instalado.

    Si no hay ninguno, cae al driver legacy 'SQL Server' (viene con Windows,
    pero no soporta TLS 1.2 moderno ni funciones nuevas).
    """
    versions = []
    for name in pyodbc.drivers():
        match = _DRIVER_RE.match(name)
        if match:
            versions.append((int(match.group(1)), name))
    if versions:
        return max(versions)[1]
    if "SQL Server" in pyodbc.drivers():
        return "SQL Server"
    raise RuntimeError(
        "No se encontró ningún driver ODBC para SQL Server. Instala "
        "'ODBC Driver 17/18 for SQL Server' (Microsoft) o indica "
        "MSSQL_ODBC_DRIVER en .env. Drivers vistos: " + ", ".join(pyodbc.drivers() or ["(ninguno)"])
    )


def _quote(value: str) -> str:
    """Escapa un valor para un connection string ODBC (llaves, '}' se duplica)."""
    return "{" + value.replace("}", "}}") + "}"


def build_connection_string(settings: Settings) -> str:
    driver = settings.odbc_driver or detect_driver()
    parts = [f"DRIVER={{{driver}}}", f"SERVER={settings.server}"]
    if settings.database:
        parts.append(f"DATABASE={_quote(settings.database)}")

    if settings.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_quote(settings.user)}")
        parts.append(f"PWD={_quote(settings.password)}")

    # Las claves Encrypt/TrustServerCertificate no existen en el driver legacy "SQL Server".
    if driver != "SQL Server":
        parts.append(f"Encrypt={'yes' if settings.encrypt else 'no'}")
        parts.append(f"TrustServerCertificate={'yes' if settings.trust_server_certificate else 'no'}")

    # Intención de solo lectura: el servidor la usa para enrutar a réplicas
    # secundarias en Availability Groups; es inocua en servidores sin AG.
    parts.append("ApplicationIntent=ReadOnly")
    return ";".join(parts) + ";"


@contextmanager
def get_connection(settings: Settings):
    """Abre una conexión SIN autocommit y garantiza rollback al cerrar.

    Nunca se hace commit: aunque algo se colara hasta el servidor, la
    transacción implícita se revierte al salir (segunda red de seguridad
    además del guard de sql_guard.py y de los permisos del login).
    """
    connection = pyodbc.connect(
        build_connection_string(settings),
        autocommit=False,
        timeout=min(settings.query_timeout_seconds or 15, 30),  # timeout de login
    )
    # Timeout de ejecución de cada consulta, en segundos (0 = sin límite).
    connection.timeout = settings.query_timeout_seconds
    try:
        yield connection
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()
