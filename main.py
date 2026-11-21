"""Punto di ingresso del bot: avvia con `python main.py`."""
from __future__ import annotations

import logging
import sys

import discord
from discord.ext import commands

import config
from database import Database
from utils.logger import setup_logging

log = logging.getLogger("bot")

EXTENSIONS = (
    "cogs.errors",
    "cogs.say",
    "cogs.webhooks",
    "cogs.avatar",
)


class WebhookBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # necessario per il comando testuale !dici

        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            help_command=None,
            # Impostazione prudente di base: nessun @everyone/@here/ruolo se non esplicitamente consentito.
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=False
            ),
        )
        self.db = Database(config.DB_PATH)

    async def setup_hook(self) -> None:
        await self.db.initialize()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        await self._sync_commands()

    async def _sync_commands(self) -> None:
        if config.DEV_GUILD_ID is not None:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Sincronizzati %d slash command sul server di test %s.", len(synced), config.DEV_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Sincronizzati %d slash command globali.", len(synced))

async def on_ready(self) -> None:
    assert self.user is not None

    log.info(
        "Connesso come %s (ID %s) in %d server.",
        self.user,
        self.user.id,
        len(self.guilds),
    )

    # Imposta l'icona del primo server come immagine profilo del bot
    for guild in self.guilds:
        if guild.icon:
            try:
                immagine = await guild.icon.read()
                await self.user.edit(avatar=immagine)

                log.info(
                    "Immagine profilo aggiornata usando il server: %s",
                    guild.name,
                )
            except discord.HTTPException:
                log.exception("Impossibile aggiornare l'immagine profilo.")

            break

    async def close(self) -> None:
        await super().close()
        await self.db.close()


def main() -> int:
    setup_logging()

    if not config.token_is_valid():
        log.error(
            "Token mancante: apri il file .env e sostituisci INSERISCI_QUI_IL_TOKEN_DEL_BOT "
            "con il token del tuo bot."
        )
        return 1

    bot = WebhookBot()
    try:
        bot.run(config.TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("Token non valido: controlla il valore di DISCORD_TOKEN nel file .env.")
        return 1
    except discord.PrivilegedIntentsRequired:
        log.error(
            "Message Content Intent non attivo: abilitalo nel Developer Portal "
            "(Bot -> Privileged Gateway Intents -> Message Content Intent)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
