"""Controlli sui permessi.

Regola unica del bot: chi ha il permesso "Gestisci webhook" (o è amministratore) può creare,
usare e rimuovere i webhook. Gli altri utenti non vedono nemmeno i comandi di gestione.
"""
from __future__ import annotations

import discord
from discord import app_commands


def has_webhook_rights(perms: discord.Permissions) -> bool:
    return perms.administrator or perms.manage_webhooks


def webhook_manager_check():
    """Check per gli slash command: richiede Gestisci webhook o Amministratore."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.NoPrivateMessage()
        if has_webhook_rights(interaction.permissions):
            return True
        raise app_commands.MissingPermissions(["manage_webhooks"])

    return app_commands.check(predicate)


def allowed_mentions_for(perms: discord.Permissions) -> discord.AllowedMentions:
    """Menzioni consentite in un messaggio inviato dal bot per conto di un utente.

    @everyone, @here e i ruoli sono permessi solo a chi avrebbe il permesso di menzionarli
    di persona; le menzioni ai singoli utenti sono sempre consentite.
    """
    can_mass_mention = perms.administrator or perms.mention_everyone
    return discord.AllowedMentions(
        everyone=can_mass_mention,
        roles=can_mass_mention,
        users=True,
        replied_user=False,
    )
