"""Gestione centralizzata degli errori (slash command e comandi testuali)."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds
from utils.errors import BotUserError, describe_http_error
from utils.interactions import send_ephemeral

log = logging.getLogger(__name__)

PERMISSION_NAMES = {
    "manage_webhooks": "Gestisci webhook",
    "manage_messages": "Gestisci messaggi",
    "send_messages": "Invia messaggi",
    "administrator": "Amministratore",
}


def _permission_list(names) -> str:
    return ", ".join(f"**{PERMISSION_NAMES.get(n, n)}**" for n in names)


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._previous_tree_handler = bot.tree.on_error
        bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self) -> None:
        self.bot.tree.on_error = self._previous_tree_handler

    # ------------------------------------------------------------ slash command

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = error.original if isinstance(error, app_commands.CommandInvokeError) else error

        if isinstance(original, BotUserError):
            embed = embeds.error(original.title, original.description)
        elif isinstance(error, app_commands.NoPrivateMessage):
            embed = embeds.error("Comando non disponibile", "Questo comando funziona solo all'interno di un server.")
        elif isinstance(error, app_commands.MissingPermissions):
            embed = embeds.error(
                "Permessi insufficienti",
                "Per usare questo comando serve il permesso **Gestisci webhook** oppure essere amministratore.",
            )
        elif isinstance(error, app_commands.CheckFailure):
            embed = embeds.error("Non puoi usare questo comando", "Non soddisfi i requisiti per eseguirlo.")
        elif isinstance(original, discord.HTTPException):
            embed = embeds.error("Operazione non riuscita", describe_http_error(original))
            log.warning(
                "Errore HTTP in /%s: %s",
                interaction.command.qualified_name if interaction.command else "?",
                original,
            )
        else:
            log.error(
                "Errore imprevisto in /%s",
                interaction.command.qualified_name if interaction.command else "?",
                exc_info=original,
            )
            embed = embeds.error(
                "Errore imprevisto",
                "Qualcosa è andato storto durante l'esecuzione del comando. Riprova tra poco.",
            )

        try:
            await send_ephemeral(interaction, embed=embed)
        except discord.HTTPException:
            pass  # interazione scaduta o già chiusa: non c'è altro da fare

    # ------------------------------------------------------------ comandi testuali

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        original = getattr(error, "original", error)

        if isinstance(error, commands.NoPrivateMessage):
            embed = embeds.error("Comando non disponibile", "Questo comando funziona solo all'interno di un server.")
        elif isinstance(error, commands.BotMissingPermissions):
            embed = embeds.error(
                "Mi mancano dei permessi",
                f"In questo canale mi servono i permessi: {_permission_list(error.missing_permissions)}.",
            )
        elif isinstance(error, commands.MissingPermissions):
            embed = embeds.error(
                "Permessi insufficienti",
                f"Ti servono i permessi: {_permission_list(error.missing_permissions)}.",
            )
        elif isinstance(error, commands.CheckFailure):
            embed = embeds.error("Non puoi usare questo comando")
        elif isinstance(original, discord.Forbidden):
            embed = embeds.error("Mi mancano dei permessi", describe_http_error(original))
        elif isinstance(original, discord.HTTPException):
            embed = embeds.error("Operazione non riuscita", describe_http_error(original))
        else:
            log.error("Errore imprevisto nel comando %s", ctx.command, exc_info=original)
            embed = embeds.error("Errore imprevisto", "Qualcosa è andato storto. Riprova tra poco.")

        try:
            await ctx.send(embed=embed, delete_after=10)
        except discord.HTTPException:
            pass  # se non posso scrivere nel canale non c'è modo di avvisare


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
