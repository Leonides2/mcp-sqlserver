"""Validador de solo-lectura para T-SQL: segunda capa de seguridad además de
los permisos de solo lectura que el DBA debe haber otorgado al login.

Esto NO reemplaza los permisos de la base de datos (esa es la barrera real),
es una barrera adicional para que la utilidad nunca intente mandar algo
distinto de un SELECT.

Diferencias con T-SQL que obligan a ir más allá de "mirar la primera palabra":
  * T-SQL no exige ';' entre sentencias: ``SELECT 1 DELETE FROM t`` es válido.
  * ``SELECT ... INTO nueva_tabla`` crea una tabla.
  * ``WITH cte AS (...) DELETE ...`` / ``UPDATE ...`` / ``MERGE ...`` son válidos.
  * ``NEXT VALUE FOR seq`` modifica una secuencia; ``OPENROWSET``/``OPENQUERY``
    pueden ejecutar texto contra otros servidores.

Por eso primero se "enmascaran" comentarios, literales de texto e
identificadores entre corchetes/comillas (para que un ';' o una palabra
clave dentro de ellos no cause falsos positivos ni se use para esconder
código), y luego se buscan palabras prohibidas en TODO el texto restante.
"""

import re


class UnsafeSqlError(ValueError):
    """La sentencia SQL no paso la validación de solo lectura."""


# Palabras que nunca deben aparecer fuera de un literal/identificador/comentario.
_FORBIDDEN_WORDS = (
    # DML / DDL
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "DROP", "ALTER", "CREATE",
    "INTO",  # SELECT ... INTO crea una tabla
    # Permisos
    "GRANT", "REVOKE", "DENY",
    # Ejecución de código / flujo
    "EXEC", "EXECUTE", "DECLARE", "SET", "BEGIN", "IF", "WHILE", "GOTO", "USE",
    # Administración / operaciones peligrosas
    "DBCC", "BACKUP", "RESTORE", "SHUTDOWN", "RECONFIGURE", "KILL", "CHECKPOINT",
    "BULK", "WAITFOR",
    # Acceso a orígenes externos / texto
    "OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "READTEXT", "WRITETEXT", "UPDATETEXT",
    # Transacciones
    "COMMIT", "ROLLBACK", "SAVE",
)

# \b no basta: no queremos casar "@update" ni "#delete" como falso positivo
# silencioso, pero tampoco dejarlos pasar; al ser conservadores, se rechazan.
_FORBIDDEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(_FORBIDDEN_WORDS) + r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_NEXT_VALUE_RE = re.compile(r"\bNEXT\s+VALUE\s+FOR\b", re.IGNORECASE)
_XP_RE = re.compile(r"(?<![A-Za-z0-9_])xp_\w*", re.IGNORECASE)
_FIRST_WORD_RE = re.compile(r"[A-Za-z]+")


def _mask(sql: str) -> str:
    """Devuelve `sql` sin comentarios y con literales/identificadores vaciados.

    - ``-- ...`` y ``/* ... */`` (anidables en T-SQL) -> espacio.
    - ``'texto'`` (con ``''`` como escape) -> ``''``.
    - ``[ident]`` (con ``]]`` como escape) y ``"ident"`` -> ``[]`` / ``""``.
    Lanza UnsafeSqlError si algo queda sin cerrar (ambiguo = rechazar).
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if ch == "-" and nxt == "-":
            end = sql.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
        elif ch == "/" and nxt == "*":
            depth, i = 1, i + 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                raise UnsafeSqlError("Comentario de bloque sin cerrar.")
            out.append(" ")
        elif ch in ("'", "[", '"'):
            closer = {"'": "'", "[": "]", '"': '"'}[ch]
            i += 1
            while True:
                if i >= n:
                    raise UnsafeSqlError("Literal o identificador sin cerrar.")
                if sql[i] == closer:
                    if i + 1 < n and sql[i + 1] == closer:  # escape duplicado
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            out.append({"'": "''", "[": "[]", '"': '""'}[ch])
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def ensure_read_only(sql: str) -> None:
    """Lanza UnsafeSqlError si `sql` no es una única sentencia SELECT/WITH."""
    if not sql or not sql.strip():
        raise UnsafeSqlError("La consulta está vacía.")

    masked = _mask(sql).strip()

    # Permitir uno o más ';' solo al final, pero no sentencias apiladas.
    body = masked.rstrip("; \t\r\n")
    if ";" in body:
        raise UnsafeSqlError("No se permiten múltiples sentencias separadas por ';'.")
    if not body:
        raise UnsafeSqlError("La consulta está vacía.")

    first = _FIRST_WORD_RE.match(body)
    first_word = first.group(0).upper() if first else ""
    if first_word not in ("SELECT", "WITH"):
        raise UnsafeSqlError(
            "Solo se permiten sentencias SELECT (o WITH ... SELECT); "
            f"la consulta empieza con '{first_word or body[:20]}'."
        )

    forbidden = _FORBIDDEN_RE.search(body)
    if forbidden:
        raise UnsafeSqlError(
            f"Palabra clave '{forbidden.group(1).upper()}' no permitida: "
            "esta utilidad es de solo lectura."
        )
    if _NEXT_VALUE_RE.search(body):
        raise UnsafeSqlError("NEXT VALUE FOR modifica una secuencia: no permitido.")
    if _XP_RE.search(body):
        raise UnsafeSqlError("Procedimientos extendidos (xp_*) no permitidos.")
