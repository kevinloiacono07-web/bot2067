"""Avatar dei webhook: icona del server, con immagine predefinita come ripiego."""
from __future__ import annotations

import asyncio
import logging
from typing import Tuple

import discord

import config

log = logging.getLogger(__name__)


async def get_server_avatar(guild: discord.Guild) -> Tuple[bytes, str]:
    """Restituisce (byte dell'immagine, origine).

    L'origine è "server" se è stata usata l'icona del server, "default" se si è usata
    l'immagine predefinita (server senza icona oppure icona non scaricabile).
    """
    if guild.icon is not None:
        try:
            data = await guild.icon.with_size(512).with_format("png").read()
            return data, "server"
        except discord.DiscordException:
            log.warning("Impossibile scaricare l'icona del server %s: uso l'immagine predefinita.", guild.id)
    data = await asyncio.to_thread(config.DEFAULT_AVATAR_PATH.read_bytes)
    return data, "default"
