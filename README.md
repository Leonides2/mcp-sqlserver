# mcp-sqlserver

Utilidad de **solo lectura** para consultar una base de datos **SQL Server**
desde un servidor MCP (Claude Code / Claude Desktop) y/o desde la terminal
mediante una skill de Claude Code.

Es el equivalente para SQL Server de
[homemade-mcp-oracle-database-10g-claude](https://github.com/Leonides2/homemade-mcp-oracle-database-10g-claude):
misma arquitectura, adaptada a T-SQL y a `pyodbc`.

## Diferencias respecto a la versión Oracle

| Tema | Oracle 10g | SQL Server (este proyecto) |
|---|---|---|
| Driver | `oracledb` en modo *thick* + Instant Client | `pyodbc` + *ODBC Driver 17/18 for SQL Server* (autodetectado) |
| Autenticación | usuario/password | usuario/password **o** autenticación integrada de Windows |
| Catálogo | `all_tables`, `all_tab_columns` | `INFORMATION_SCHEMA` y `sys.databases` |
| Límite de filas en SQL | `ROWNUM` | `TOP n` / `OFFSET … FETCH` |
| Guard de solo lectura | primera palabra + sin `;` | **más estricto** (ver abajo) |
| Tools MCP | `run_query_tool`, `list_tables`, `describe_table` | `run_query`, `list_databases`, `list_tables`, `describe_table` |
| Errores hacia el modelo | genéricos | con motivo (`[RECHAZADO]`, `[ERROR] SQL Server: …`) |

## Arquitectura

```
src/
  config.py           Carga y valida .env (conexión, driver, política)
  db.py               Conexión pyodbc; autodetecta el driver; nunca hace commit (rollback al cerrar)
  sql_guard.py        Guard de solo lectura para T-SQL
  audit_log.py        Auditoría (logs/query_audit.log)
  query_runner.py     Ejecuta SQL con límite de filas, timeout y auditoría; resultado JSON-safe
  schema_inspector.py list_databases / list_tables / describe_table (con marca de PK)
  mcp_server.py       Servidor MCP (stdio)

scripts/
  install.py          Instalador (venv, deps, .env, mcp-config.json, registro en Claude Code)
  test_connection.py  Prueba mínima de conectividad
  query.py            CLI de consultas (lo usa también la skill)

tests/test_sql_guard.py            Tests del guard (no requieren SQL Server)
.claude/skills/sqlserver-query/    Skill de Claude Code
```

## Modelo de seguridad (defensa en profundidad)

1. **Base de datos (barrera real)**: usa un login con permisos de solo lectura
   (`db_datareader`, o `SELECT` sobre lo necesario). Nada de lo siguiente lo
   reemplaza.
2. **Guard de software** (`src/sql_guard.py`): T-SQL permite cosas que otros
   dialectos no, así que el guard enmascara comentarios, literales e
   identificadores y luego busca palabras prohibidas en *todo* el texto:
   - sentencias sin `;` (`SELECT 1 DELETE FROM t` es válido en T-SQL),
   - `SELECT … INTO` (crea tablas), `WITH cte AS (…) DELETE/UPDATE/MERGE`,
   - `EXEC`, `DECLARE`, `SET`, `USE`, `WAITFOR`, `OPENROWSET`/`OPENQUERY`,
     `NEXT VALUE FOR`, `xp_*`, DDL, permisos…
   Un `;` o `DELETE` dentro de un literal (`'a; DELETE'`) no da falso positivo.
   Ante la duda (literal sin cerrar, etc.) rechaza.
3. **Transacción nunca confirmada**: la conexión es sin autocommit y se hace
   `rollback` al cerrar; además se declara `ApplicationIntent=ReadOnly`.
4. **Límites**: `MAX_ROWS` (resultado marcado `truncated`) y
   `QUERY_TIMEOUT_SECONDS`.
5. **Auditoría**: toda ejecución (OK, error o rechazada) en `logs/query_audit.log`.

## Instalación

```
install.bat                      # Windows
python scripts/install.py        # cualquier SO
```

Crea `.venv`, instala dependencias, copia `.env.example` a `.env`, genera
`mcp-config.json` y registra el servidor en Claude Code (`--no-register` para
omitirlo, `--force` para rehacerlo). Luego **edita `.env`**.

Requisito del sistema: un *ODBC Driver for SQL Server* (17 o 18) instalado.
Si no lo tienes: <https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server>.

### Configuración (`.env`)

```
MSSQL_HOST=servidor        MSSQL_PORT=1433        MSSQL_INSTANCE=   # p. ej. SQLEXPRESS
MSSQL_DATABASE=MiBase
MSSQL_USER=lector          MSSQL_PASSWORD=...     # o MSSQL_TRUSTED_CONNECTION=true
```

Con `MSSQL_INSTANCE` se conecta a `HOST\INSTANCIA` (SQL Browser resuelve el puerto).
`MSSQL_TRUST_SERVER_CERTIFICATE=true` (por defecto) cubre certificados
autofirmados, habituales en servidores legacy; ponlo en `false` si tu servidor
tiene un certificado válido. **Nunca subas `.env` a un repositorio.**

## Uso

```
.venv\Scripts\python scripts\test_connection.py
.venv\Scripts\python scripts\query.py "SELECT TOP 10 * FROM dbo.mi_tabla" --format json
.venv\Scripts\python scripts\query.py --file consulta.sql
.venv\Scripts\python -m unittest discover -s tests -v
```

### Servidor MCP

Registro manual en Claude Code:

```
claude mcp add sqlserver -s user -- "<ruta>\.venv\Scripts\python.exe" "<ruta>\src\mcp_server.py"
```

Para otro cliente, usa `mcp-config.json` (lo genera el instalador; ver
`mcp-config.example.json`). Se invoca el archivo directamente y no con
`-m src.mcp_server` porque un cliente MCP lanza el proceso con un `cwd` que no
controlas; `mcp_server.py` ajusta `sys.path` con su propia ubicación y
`config.py` busca `.env` junto al proyecto.

Tools:
- `run_query(sql)` — SELECT / WITH … SELECT, con guard.
- `list_databases()` — bases accesibles (para usar nombres `base.esquema.tabla`).
- `list_tables(schema?)` — tablas y vistas.
- `describe_table(table_name, schema?)` — columnas, tipos, nullable, default y PK.

## Notas de T-SQL

```sql
SELECT TOP 20 col1, col2 FROM dbo.tabla ORDER BY col1;
SELECT col1 FROM dbo.tabla ORDER BY col1 OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY; -- 2012+
```

## Limitaciones conocidas

- Solo se devuelve el primer *result set* de una consulta.
- No se probó contra una instancia real de SQL Server en el desarrollo
  inicial (no había una disponible): el guard está cubierto por tests, y el
  arranque del servidor MCP, la construcción del connection string y el manejo
  de errores de conexión se verificaron, pero conviene correr
  `scripts/test_connection.py` contra tu servidor como primer paso.
