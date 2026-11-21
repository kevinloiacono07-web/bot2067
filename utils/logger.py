"""Logging con rimozione automatica di token (bot e webhook) da qualsiasi riga."""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

import config

_WEBHOOK_URL = re.compile(r"(webhooks/\d+/)[A-Za-z0-9._\-]+")
_BOT_TOKEN = re.compile(r"[A-Za-z0-9_\-]{23,28}\.[A-Za-z0-9_\-]{6,7}\.[A-Za-z0-9_\-]{27,}")
_MASK = "[TOKEN-RIMOSSO]"


def redact(text: str) -> str:
    text = _WEBHOOK_URL.sub(lambda m: m.group(1) + _MASK, text)
    return _BOT_TOKEN.sub(_MASK, text)


class RedactingFormatter(logging.Formatter):
    """Applica la rimozione dei token al testo finale, traceback compresi."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging() -> None:
    formatter = RedactingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    handlers: list[logging.Handler] = [stream]

    try:
        config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        pass  # se il file di log non è scrivibile si usa solo la console

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)

    logging.getLogger("discord.http").setLevel(logging.WARNING)
