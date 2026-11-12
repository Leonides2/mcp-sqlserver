---
name: sqlserver-query
description: Ejecuta consultas SELECT de solo lectura contra la base de datos SQL Server de este proyecto (o revisa la estructura de sus tablas) directamente desde la terminal. Usar cuando el usuario pida consultar, verificar, revisar o explorar datos/tablas de la base de datos SQL Server, cuando pida "correr una query", o cuando se necesite confirmar el valor real de algo en la BD antes de responder.
---

# Consultas a SQL Server (solo lectura)

Esta skill envuelve el CLI de este proyecto (`scripts/query.py`) para consultar
la base SQL Server desde la terminal, sin necesidad de un cliente MCP. Usa el
mismo núcleo de conexión/seguridad que el servidor MCP (`src/mcp_server.py`).
Si el MCP `sqlserver` ya está registrado en la sesión, prefiere sus tools
(`run_query`, `list_tables`, `describe_table`, `list_databases`).

## Regla no negociable: SOLO LECTURA

La utilidad **solo permite `SELECT` (o `WITH ... SELECT`)**. Se rechazan
`INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL, `GRANT`/`REVOKE`/`DENY`, `EXEC`,
`DECLARE`/`SET`, `SELECT ... INTO`, `OPENROWSET`/`OPENQUERY`, `NEXT VALUE FOR`,
`WAITFOR`, `USE`, y cualquier sentencia apilada (con o sin `;`) antes de tocar
la base (ver `src/sql_guard.py`). No intentes rodear la restricción: si el
usuario necesita escribir datos, dile que esta utilidad no lo soporta y que
haría falta un cambio explícito de alcance.

## Requisito previo

Debe existir `.env` en la raíz del proyecto (ver `.env.example`). Si falta o
está incompleto, el CLI lo dice claramente: no adivines ni inventes valores.

## Cómo ejecutar una consulta

Desde la raíz del proyecto, con el intérprete del venv:

```
.venv\Scripts\python scripts\query.py "SELECT TOP 10 * FROM dbo.tabla WHERE ..."
.venv\Scripts\python scripts\query.py "SELECT ..." --format json
.venv\Scripts\python scripts\query.py --file ruta\consulta.sql --format json
```

## Antes de escribir un SELECT contra una tabla que no conoces

1. Ver qué tablas existen:
   ```
   .venv\Scripts\python scripts\query.py "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY 1, 2" --format json
   ```
2. Ver las columnas de una tabla puntual:
   ```
   .venv\Scripts\python scripts\query.py "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'tabla' ORDER BY ORDINAL_POSITION" --format json
   ```

No inventes nombres de columnas: si falla con `Invalid column name` o
`Invalid object name`, describe la tabla primero.

## Particularidades de T-SQL

- Limitar filas: `SELECT TOP 20 ...` o `ORDER BY x OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY`
  (esta última requiere SQL Server 2012+). `LIMIT` y `ROWNUM` no existen.
- Citar identificadores con `[corchetes]`: `[dbo].[Mi Tabla]`.
- Otra base del mismo servidor: nombre de tres partes `OtraBase.dbo.tabla`
  (`USE` está bloqueado). `list_databases` (MCP) muestra las accesibles.
- Fechas: `GETDATE()`, `DATEADD`, `DATEDIFF`; texto: `+` o `CONCAT`.
- El CLI limita las filas según `MAX_ROWS` y aplica `QUERY_TIMEOUT_SECONDS`.
  Si el resultado trae `truncated: true`, avisa al usuario que hay más filas
  y ofrece acotar (WHERE/TOP) en vez de asumir que es todo.
- Usa `NOLOCK` solo si el usuario lo pide: puede devolver lecturas sucias.

## Interpretando errores

- `[RECHAZADO] ...` (exit code 2): no pasó el guard. No reformules para
  evadirlo; explica la restricción.
- `[ERROR] Configuración inválida: ...`: falta/está mal el `.env`. Pídele al
  usuario que lo revise.
- `[ERROR] Falló al ejecutar la consulta: ...`: error de SQL Server o de
  conexión. Lee el mensaje, corrige (nombre, sintaxis T-SQL) y reintenta una
  vez; si persiste, muestra el error tal cual en vez de especular.

## Auditoría

Toda consulta (exitosa, con error o rechazada) queda en `logs/query_audit.log`.
