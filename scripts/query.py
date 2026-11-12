"""CLI: ejecuta una consulta SELECT contra SQL Server.

Uso:
    python scripts/query.py "SELECT TOP 10 * FROM dbo.alguna_tabla"
    python scripts/query.py --file consulta.sql
    python scripts/query.py "SELECT ..." --format json

Requiere un archivo .env en la raíz del proyecto (ver .env.example).
Por política de esta utilidad, solo se permiten sentencias SELECT.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.query_runner import QueryResult, run_query
from src.sql_guard import UnsafeSqlError


def print_table(result: QueryResult) -> None:
    if not result.columns:
        print("(sin columnas devueltas)")
        return

    widths = [len(c) for c in result.columns]
    str_rows = [[("" if v is None else str(v)) for v in row] for row in result.rows]
    for row in str_rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    print(" | ".join(c.ljust(widths[i]) for i, c in enumerate(result.columns)))
    print("-+-".join("-" * w for w in widths))
    for row in str_rows:
        print(" | ".join(val.ljust(widths[i]) for i, val in enumerate(row)))

    print(f"\n({len(result.rows)} fila(s))" + (" [TRUNCADO según MAX_ROWS]" if result.truncated else ""))


def print_json(result: QueryResult) -> None:
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def main() -> int:
    # Evita UnicodeEncodeError en consolas Windows con codepage antigua.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Consulta de solo lectura a SQL Server")
    parser.add_argument("sql", nargs="?", help="Sentencia SELECT a ejecutar")
    parser.add_argument("--file", help="Archivo .sql con la consulta a ejecutar")
    parser.add_argument("--format", choices=["table", "json"], default="table")
    args = parser.parse_args()

    if not args.sql and not args.file:
        parser.error("Debes pasar la consulta como argumento o con --file")

    sql = args.sql
    if args.file:
        sql = Path(args.file).read_text(encoding="utf-8-sig")

    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"[ERROR] Configuración inválida: {exc}")
        return 1

    try:
        result = run_query(settings, sql)
    except UnsafeSqlError as exc:
        print(f"[RECHAZADO] {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Falló al ejecutar la consulta: {exc}")
        return 1

    if args.format == "json":
        print_json(result)
    else:
        print_table(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
