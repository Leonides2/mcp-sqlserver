"""Tests del guard de solo lectura. No requieren SQL Server.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sql_guard import UnsafeSqlError, ensure_read_only

ALLOWED = [
    "SELECT 1",
    "select * from dbo.t;",
    "SELECT TOP 10 [update], [delete] FROM [dbo].[into]",
    "WITH c AS (SELECT 1 AS x) SELECT * FROM c",
    "SELECT * FROM t WITH (NOLOCK) WHERE a = 'x; DELETE FROM t'",
    "SELECT 'it''s; DROP TABLE x' AS s",
    "SELECT * FROM t -- DROP TABLE t",
    "/* UPDATE t SET a=1 */ SELECT 1",
    "SELECT a FROM t ORDER BY a OFFSET 10 ROWS FETCH NEXT 5 ROWS ONLY",
    "SELECT a, UPDATE_DATE, inserted_at FROM t",  # prefijos/sufijos no cuentan
    'SELECT "delete" FROM t',
    "SELECT REPLACE(a, 'x', 'y'), IIF(a > 1, 1, 0) FROM t",
    "SELECT * FROM sys.databases;;",
]

REJECTED = [
    "",
    "   ",
    ";",
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET a = 1",
    "DELETE FROM t",
    "DROP TABLE t",
    "EXEC sp_who",
    "EXECUTE('SELECT 1')",
    "SELECT 1; DELETE FROM t",
    "SELECT 1 DELETE FROM t",                    # sin ';', válido en T-SQL
    "SELECT * INTO nueva FROM t",                # crea tabla
    "SELECT * INTO #tmp FROM t",
    "WITH c AS (SELECT 1 AS x) DELETE FROM t",   # CTE + DML
    "WITH c AS (SELECT 1 AS x) UPDATE t SET a=1",
    "SELECT 1 /* x */ ; /* y */ DROP TABLE t",
    "SELECT * FROM OPENROWSET('SQLNCLI', 'x', 'SELECT 1')",
    "SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')",
    "SELECT NEXT VALUE FOR dbo.seq",
    "SELECT * FROM t WAITFOR DELAY '00:01'",
    "SELECT 1 USE master",
    "SELECT 1 DECLARE @x int",
    "SELECT xp_cmdshell('dir')",
    "SELECT 'sin cerrar",
    "SELECT /* sin cerrar",
    "SELECT [sin cerrar",
    "DECLARE @x INT = 1; SELECT @x",
    "BEGIN TRAN; SELECT 1",
    "GRANT SELECT ON t TO u",
    "(SELECT 1)",  # conservador: debe empezar con SELECT/WITH
]


class GuardTests(unittest.TestCase):
    def test_allowed(self):
        for sql in ALLOWED:
            with self.subTest(sql=sql):
                ensure_read_only(sql)

    def test_rejected(self):
        for sql in REJECTED:
            with self.subTest(sql=sql):
                with self.assertRaises(UnsafeSqlError):
                    ensure_read_only(sql)


if __name__ == "__main__":
    unittest.main()
