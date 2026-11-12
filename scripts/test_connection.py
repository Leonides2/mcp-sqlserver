"""Prueba mínima de conexión contra SQL Server.

Uso:
    python scripts/test_connection.py

Requiere un archivo .env en la raíz del proyecto (ver .env.example).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_settings
from src.db import build_connection_string, get_connection


def main() -> int:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"[ERROR] Configuración inválida: {exc}")
        return 1

    print(f"Conectando a {settings.dsn_target} como {settings.principal}...")
    try:
        # Sin credenciales: solo driver y destino.
        print("Driver:", build_connection_string(settings).split(";")[0].replace("DRIVER=", "").strip("{}"))
        with get_connection(settings) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION, DB_NAME(), SUSER_SNAME()")
            version, db, login = cursor.fetchone()
            print("[OK] Conexión exitosa.")
            print(f"Versión : {version.splitlines()[0]}")
            print(f"Base    : {db}")
            print(f"Login   : {login}")
    except Exception as exc:  # noqa: BLE001 - queremos ver cualquier error tal cual
        print(f"[ERROR] Falló la conexión o la consulta: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
