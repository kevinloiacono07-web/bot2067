"""Lettura e validazione degli allegati immagine passati agli slash command."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import discord

from utils.errors import BotUserError

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB


async def read_image_attachment(attachment: discord.Attachment, label: str) -> Tuple[str, bytes]:
    """Controlla che l'allegato sia un'immagine valida e ne restituisce (estensione, byte)."""
    extension = Path(attachment.filename).suffix.lower()
    content_type = (attachment.content_type or "").lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS or (content_type and not content_type.startswith("image/")):
        raise BotUserError(
            f"Formato non valido per «{label}»",
            "Carica un'immagine in formato PNG, JPG, GIF o WEBP.",
        )
    if attachment.size > MAX_IMAGE_BYTES:
        raise BotUserError(
            f"Immagine «{label}» troppo grande",
            "L'immagine non può superare gli 8 MB.",
        )
    data = await attachment.read()
    return extension, data
