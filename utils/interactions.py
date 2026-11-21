"""Utilità per rispondere alle interazioni degli slash command."""
from __future__ import annotations

import discord


async def send_ephemeral(interaction: discord.Interaction, **kwargs) -> None:
    """Invia una risposta visibile solo all'utente, anche se l'interazione ha già risposto."""
    if interaction.response.is_done():
        await interaction.followup.send(ephemeral=True, **kwargs)
    else:
        await interaction.response.send_message(ephemeral=True, **kwargs)
