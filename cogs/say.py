"""Comando testuale !dici: il bot ripete il messaggio al posto dell'utente."""
import discord
from discord.ext import commands

from utils import embeds
from utils.permissions import allowed_mentions_for

MAX_LENGTH = 2000


class Say(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    async def _delete_quietly(message: discord.Message) -> None:
        try:
            await message.delete()
        except discord.NotFound:
            pass  # già eliminato

    @commands.command(name="dici", help="Il bot ripete il testo e cancella il comando (solo amministratori).")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(send_messages=True, manage_messages=True)
    async def dici(self, ctx: commands.Context, *, testo: str = "") -> None:
        testo = testo.strip()

        if not testo:
            await self._delete_quietly(ctx.message)
            await ctx.send(
                content=ctx.author.mention,
                embed=embeds.warning(
                    "Messaggio vuoto",
                    f"Scrivi qualcosa dopo il comando, ad esempio `{ctx.prefix}dici Ciao a tutti!`",
                ),
                delete_after=10,
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )
            return

        if len(testo) > MAX_LENGTH:
            await self._delete_quietly(ctx.message)
            await ctx.send(
                content=ctx.author.mention,
                embed=embeds.warning(
                    "Messaggio troppo lungo",
                    f"Il testo supera il limite di {MAX_LENGTH} caratteri consentito ai bot.",
                ),
                delete_after=10,
                allowed_mentions=discord.AllowedMentions(users=[ctx.author]),
            )
            return

        perms = ctx.channel.permissions_for(ctx.author)
        await self._delete_quietly(ctx.message)
        await ctx.channel.send(testo, allowed_mentions=allowed_mentions_for(perms))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Say(bot))
