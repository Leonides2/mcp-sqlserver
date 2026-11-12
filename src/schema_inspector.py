"""Consultas de catálogo (bases de datos / tablas / columnas) para SQL Server.

Usa INFORMATION_SCHEMA (estándar, disponible en todas las versiones) y
sys.databases. Los valores de schema/tabla van como parámetros '?' de ODBC,
nunca concatenados. Se arman dos variantes de SQL (con y sin filtro) en vez
de usar "(? IS NULL OR ...)" porque el driver ODBC infiere mal el tipo de un
parámetro NULL en esa forma.
"""

from .config import Settings
from .query_runner import QueryResult, run_internal_query

_LIST_DATABASES_SQL = """
SELECT name, state_desc, recovery_model_desc, compatibility_level
FROM sys.databases
WHERE HAS_DBACCESS(name) = 1
ORDER BY name
"""

_LIST_TABLES_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
{where}
ORDER BY TABLE_SCHEMA, TABLE_NAME
"""

# Marca columnas de clave primaria con un LEFT JOIN contra las constraints PRIMARY KEY.
_DESCRIBE_TABLE_SQL = """
SELECT
    c.TABLE_SCHEMA,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.CHARACTER_MAXIMUM_LENGTH,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    CASE WHEN pk.COLUMN_NAME IS NULL THEN 0 ELSE 1 END AS IS_PRIMARY_KEY,
    c.ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS c
LEFT JOIN (
    SELECT kcu.TABLE_SCHEMA, kcu.TABLE_NAME, kcu.COLUMN_NAME
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
    JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
      ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
     AND kcu.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
    WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
) pk
  ON pk.TABLE_SCHEMA = c.TABLE_SCHEMA
 AND pk.TABLE_NAME = c.TABLE_NAME
 AND pk.COLUMN_NAME = c.COLUMN_NAME
WHERE c.TABLE_NAME = ?
{schema_filter}
ORDER BY c.TABLE_SCHEMA, c.ORDINAL_POSITION
"""


def list_databases(settings: Settings) -> QueryResult:
    return run_internal_query(settings, _LIST_DATABASES_SQL)


def list_tables(settings: Settings, schema: str | None = None) -> QueryResult:
    if schema:
        sql = _LIST_TABLES_SQL.format(where="WHERE TABLE_SCHEMA = ?")
        return run_internal_query(settings, sql, (schema,))
    return run_internal_query(settings, _LIST_TABLES_SQL.format(where=""))


def describe_table(settings: Settings, table_name: str, schema: str | None = None) -> QueryResult:
    if schema:
        sql = _DESCRIBE_TABLE_SQL.format(schema_filter="AND c.TABLE_SCHEMA = ?")
        return run_internal_query(settings, sql, (table_name, schema))
    return run_internal_query(settings, _DESCRIBE_TABLE_SQL.format(schema_filter=""), (table_name,))
