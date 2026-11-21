"""Punto di ingresso del bot Discord."""
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
    "cogs.registry",
    "cogs.welcome",
)


class WebhookBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                roles=False,
                users=True,
                replied_user=False,
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

            log.info(
                "Sincronizzati %d slash command sul server di test.",
                len(synced),
            )
        else:
            synced = await self.tree.sync()
            log.info("Sincronizzati %d slash command globali.", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None

        # Attività personalizzata del bot
        await self.change_presence(
            activity=discord.Game(
                name="🌸 Maple Hospital | The Fifth Crown 🏥"
            ),
            status=discord.Status.online,
        )

        log.info(
            "Connesso come %s (ID %s) in %d server.",
            self.user,
            self.user.id,
            len(self.guilds),
        )

        # Imposta l'immagine del primo server come avatar del bot
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
        log.error("Token Discord mancante o non valido.")
        return 1

    bot = WebhookBot()

    try:
        bot.run(config.TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("Token Discord non valido.")
        return 1
    except discord.PrivilegedIntentsRequired:
        log.error("Attiva gli Intent privilegiati nel Developer Portal.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())