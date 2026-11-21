
import discord
from discord import app_commands
from discord.ext import commands


class Avatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="imposta_avatar",
        description="Imposta l'icona del server come avatar del bot."
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def imposta_avatar(self, interaction: discord.Interaction):

        guild = interaction.guild

        if guild is None or guild.icon is None:
            await interaction.response.send_message(
                "Questo server non possiede un'immagine personalizzata.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            immagine = await guild.icon.read()

            await self.bot.user.edit(avatar=immagine)

            await interaction.followup.send(
                f"✅ Avatar del bot aggiornato con l'icona di **{guild.name}**!",
                ephemeral=True
            )

        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Non è stato possibile aggiornare l'avatar.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Avatar(bot))
