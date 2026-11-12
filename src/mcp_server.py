"""Servidor MCP de solo lectura para SQL Server.

Expone 4 tools:
  - run_query(sql): ejecuta un SELECT arbitrario (validado por sql_guard).
  - list_databases(): bases de datos accesibles en el servidor.
  - list_tables(schema opcional): tablas y vistas de la base de datos configurada.
  - describe_table(table_name, schema opcional): columnas de una tabla (con PK).

Se apoya en el mismo núcleo (config/db/query_runner/schema_inspector) que
usa el CLI en scripts/query.py, para no duplicar lógica de conexión,
límites ni auditoría.

Uso (stdio, para registrar en un cliente MCP como Claude Desktop/Code):
    python ruta\\completa\\a\\src\\mcp_server.py

Se ejecuta como script (no como "python -m src.mcp_server") a propósito:
un cliente MCP lanza este proceso con un cwd arbitrario, y "-m src.mcp_server"
solo resuelve el paquete "src" si ese cwd lo contiene. Por eso este archivo
agrega la raíz del proyecto a sys.path usando su propia ubicación (__file__)
antes de importar el resto.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyodbc
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from src.config import Settings, load_settings
from src.query_runner import run_query as _run_query
from src.schema_inspector import describe_table as _describe_table
from src.schema_inspector import list_databases as _list_databases
from src.schema_inspector import list_tables as _list_tables
from src.sql_guard import UnsafeSqlError

server = MCPServer(
    "sqlserver",
    instructions=(
        "Herramientas de SOLO LECTURA contra una base SQL Server. "
        "Nunca intentes generar INSERT/UPDATE/DELETE/DDL/EXEC ni SELECT ... INTO: "
        "serán rechazados. Usa list_tables para descubrir tablas, describe_table "
        "para ver sus columnas antes de escribir un SELECT, y run_query para "
        "ejecutarlo. La sintaxis es T-SQL: limita filas con TOP n u "
        "OFFSET/FETCH, y cita identificadores con [corchetes]."
    ),
)

_settings: Settings | None = None


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def _to_dict_safe(fn, *args) -> dict:
    """Ejecuta `fn(settings, *args)` y traduce los fallos esperables a ToolError.

    El SDK de MCP solo deja pasar el texto de un ToolError al modelo; cualquier
    otra excepción llega como un genérico "Error executing tool ..." sin
    motivo. Aquí exponemos justo lo que el modelo necesita para corregirse
    (rechazo del guard, error de SQL Server, .env incompleto), sin trazas.
    """
    try:
        return fn(_get_settings(), *args).to_dict()
    except UnsafeSqlError as exc:
        raise ToolError(f"[RECHAZADO] {exc}") from exc
    except ValueError as exc:  # .env inválido o incompleto
        raise ToolError(f"[ERROR] Configuración inválida: {exc}") from exc
    except pyodbc.Error as exc:
        raise ToolError(f"[ERROR] SQL Server: {exc}") from exc


@server.tool()
def run_query(sql: str) -> dict:
    """Ejecuta una sentencia SELECT (o WITH ... SELECT) de solo lectura contra
    SQL Server y devuelve columnas y filas. Cualquier otra sentencia es
    rechazada (error). El resultado se trunca a MAX_ROWS filas (campo
    `truncated`)."""
    return _to_dict_safe(_run_query, sql)


@server.tool()
def list_databases() -> dict:
    """Lista las bases de datos del servidor a las que el login tiene acceso.
    Para consultar otra base sin cambiar la configuración, usa nombres de
    tres partes en el SELECT: base.esquema.tabla."""
    return _to_dict_safe(_list_databases)


@server.tool()
def list_tables(schema: str | None = None) -> dict:
    """Lista tablas y vistas de la base de datos configurada
    (INFORMATION_SCHEMA.TABLES), opcionalmente filtradas por esquema (ej. 'dbo').
    Si `schema` se omite, lista todos los esquemas (puede truncarse a MAX_ROWS)."""
    return _to_dict_safe(_list_tables, schema)


@server.tool()
def describe_table(table_name: str, schema: str | None = None) -> dict:
    """Describe las columnas de una tabla o vista (esquema, nombre, tipo,
    longitud, precisión, escala, nullable, default, si es clave primaria), en
    orden de columna. Si no se indica `schema` y el nombre existe en varios
    esquemas, devuelve las columnas de todos (revisa TABLE_SCHEMA)."""
    return _to_dict_safe(_describe_table, table_name, schema)


if __name__ == "__main__":
    server.run()
