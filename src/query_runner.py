"""Ejecuta consultas SELECT contra SQL Server con límites de seguridad y auditoría."""

import base64
import datetime
import decimal
import uuid
from dataclasses import dataclass

from .audit_log import get_audit_logger, one_line
from .config import Settings
from .db import get_connection
from .sql_guard import UnsafeSqlError, ensure_read_only


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool

    def to_dict(self) -> dict:
        """Representación JSON-safe (fechas, Decimal, bytes, GUID -> str/float)."""
        return {
            "columns": self.columns,
            "rows": [[_jsonable(v) for v in row] for row in self.rows],
            "row_count": len(self.rows),
            "truncated": self.truncated,
        }


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        # Enteros exactos como int; el resto como float para que sea numérico en JSON.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "base64:" + base64.b64encode(bytes(value)).decode("ascii")
    return str(value)


def _execute(settings: Settings, sql: str, params: tuple | None = None) -> QueryResult:
    """Ejecuta cualquier SQL ya validado (o de confianza, generado internamente)
    y registra la ejecución en el log de auditoría."""
    logger = get_audit_logger()
    logged_sql = one_line(sql)
    who = settings.principal

    with get_connection(settings) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
        except Exception as exc:
            logger.info("user=%s status=ERROR error=%s sql=%s", who, one_line(str(exc)), logged_sql)
            raise

        if cursor.description is None:
            logger.info("user=%s status=OK rows=0 sql=%s", who, logged_sql)
            return QueryResult(columns=[], rows=[], truncated=False)

        columns = [col[0] for col in cursor.description]
        # Pedimos una fila extra para saber si el resultado quedó truncado.
        rows = cursor.fetchmany(settings.max_rows + 1)
        truncated = len(rows) > settings.max_rows
        if truncated:
            rows = rows[: settings.max_rows]

        logger.info(
            "user=%s status=OK rows=%d truncated=%s sql=%s",
            who, len(rows), truncated, logged_sql,
        )
        return QueryResult(columns=columns, rows=[tuple(r) for r in rows], truncated=truncated)


def run_query(settings: Settings, sql: str) -> QueryResult:
    """Punto de entrada para SQL arbitrario (CLI / tool MCP run_query).
    Aplica el guard de solo-lectura antes de ejecutar."""
    if settings.read_only:
        try:
            ensure_read_only(sql)
        except UnsafeSqlError as exc:
            get_audit_logger().info(
                "user=%s status=REJECTED error=%s sql=%s",
                settings.principal, exc, one_line(sql),
            )
            raise
    return _execute(settings, sql)


def run_internal_query(settings: Settings, sql: str, params: tuple | None = None) -> QueryResult:
    """Punto de entrada para SQL fijo generado por esta misma utilidad
    (ej. consultas de catálogo en schema_inspector.py). No pasa por el
    guard de solo-lectura porque el texto SQL no viene del usuario final,
    solo sus parámetros (que van como parámetros '?', no concatenados)."""
    return _execute(settings, sql, params)
