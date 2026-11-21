"""Configurazione del bot: legge le impostazioni dal file .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PLACEHOLDER_TOKEN = "INSERISCI_QUI_IL_TOKEN_DEL_BOT"

TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!").strip() or "!"


def _resolve_path(raw: str, default: Path) -> Path:
    raw = raw.strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else BASE_DIR / path


DB_PATH: Path = _resolve_path(os.getenv("DATABASE_PATH", ""), BASE_DIR / "data" / "webhooks.db")
LOG_PATH: Path = BASE_DIR / "data" / "bot.log"
DEFAULT_AVATAR_PATH: Path = BASE_DIR / "assets" / "default_avatar.png"

_dev_guild = os.getenv("DEV_GUILD_ID", "").strip()
# Se impostato, gli slash command vengono sincronizzati solo su questo server (aggiornamento istantaneo).
DEV_GUILD_ID: int | None = int(_dev_guild) if _dev_guild.isdigit() else None


def token_is_valid() -> bool:
    """True se nel file .env è stato inserito un token (non il segnaposto)."""
    return bool(TOKEN) and TOKEN != PLACEHOLDER_TOKEN