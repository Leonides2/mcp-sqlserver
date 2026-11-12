"""Logging de auditoría: registra cada consulta ejecutada contra SQL Server.

Se guarda en logs/query_audit.log (no se versiona, ver .gitignore).
"""

import logging
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "query_audit.log"
_logger: logging.Logger | None = None


def get_audit_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sqlserver_audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        logger.addHandler(handler)

    _logger = logger
    return logger


def one_line(sql: str, max_len: int = 500) -> str:
    return " ".join(sql.split())[:max_len]
