"""Sistema di benvenuto e uscita personalizzabile."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("bot.welcome")


def format_message(text: str, member: discord.Member) -> str:
    """Sostituisce le variabili personalizzate."""
    variables = {
        "{user}": member.mention,
        "{username}": member.display_name,
        "{server}": member.guild.name,
        "{userid}": str(member.id),
        "{membercount}": str(member.guild.member_count or 0),
        "{created_at}": f"<t:{int(member.created_at.timestamp())}:D>",
    }

    for key, value in variables.items():
        text = text.replace(key, value)

    return text


def valid_image_url(value: str) -> bool:
    if not value:
        return True

    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class WelcomeEditorModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "Welcome",
        message_type: str,
        settings: dict,
    ) -> None:
        self.cog = cog
        self.message_type = message_type
        is_welcome = message_type == "welcome"

        if is_welcome:
            title = settings["welcome_title"]
            description = settings["welcome_description"]
            color = settings["welcome_color"]
            image = settings["welcome_image"]
            footer = settings["welcome_footer"]
            modal_title = "Modifica benvenuto"
        else:
            title = settings["leave_title"]
            description = settings["leave_description"]
            color = settings["leave_color"]
            image = settings["leave_image"]
            footer = settings["leave_footer"]
            modal_title = "Modifica uscita"

        super().__init__(title=modal_title)

        self.title_input = discord.ui.TextInput(
            label="Titolo",
            placeholder="Inserisci il titolo dell'embed",
            default=title or "",
            max_length=256,
        )

        self.description_input = discord.ui.TextInput(
            label="Messaggio",
            placeholder="Scrivi il tuo messaggio personalizzato",
            default=description or "",
            style=discord.TextStyle.paragraph,
            max_length=4000,
        )

        self.color_input = discord.ui.TextInput(
            label="Colore HEX",
            placeholder="#9966FF",
            default=color or "#9966FF",
            max_length=7,
        )

        self.image_input = discord.ui.TextInput(
            label="Immagine (URL facoltativo)",
            placeholder="https://esempio.it/immagine.png",
            default=image or "",
            required=False,
            max_length=500,
        )

        self.footer_input = discord.ui.TextInput(
            label="Footer",
            placeholder="Testo in fondo all'embed",
            default=footer or "",
            required=False,
            max_length=2048,
        )

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.image_input)
        self.add_item(self.footer_input)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        title = self.title_input.value.strip()
        description = self.description_input.value.strip()
        color = self.color_input.value.strip()
        image = self.image_input.value.strip()
        footer = self.footer_input.value.strip()

        if not title or not description:
            await interaction.response.send_message(
                "❌ Titolo e messaggio non possono essere vuoti.",
                ephemeral=True,
            )
            return

        if (
            len(color) != 7
            or not color.startswith("#")
        ):
            await interaction.response.send_message(
                "❌ Il colore deve essere nel formato HEX, ad esempio #9966FF.",
                ephemeral=True,
            )
            return

        try:
            int(color[1:], 16)
        except ValueError:
            await interaction.response.send_message(
                "❌ Il colore inserito non è valido.",
                ephemeral=True,
            )
            return

        if not valid_image_url(image):
            await interaction.response.send_message(
                "❌ Inserisci un URL immagine valido che inizi con http:// o https://.",
                ephemeral=True,
            )
            return

        await self.cog.bot.db.update_welcome_message(
            interaction.guild_id,
            self.message_type,
            title=title,
            description=description,
            color=color.upper(),
            image=image,
            footer=footer,
        )

        await interaction.response.send_message(
            "✅ Messaggio personalizzato e salvato correttamente!",
            ephemeral=True,
        )


class WelcomePanelView(discord.ui.View):
    def __init__(self, cog: "Welcome") -> None:
        super().__init__(timeout=300)
        self.cog = cog

    async def check_permissions(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ Non hai il permesso di gestire il server.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="Modifica benvenuto",
        emoji="👋",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def edit_welcome(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_permissions(interaction):
            return

        settings = await self.cog.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        await interaction.response.send_modal(
            WelcomeEditorModal(
                self.cog,
                "welcome",
                settings,
            )
        )

    @discord.ui.button(
        label="Modifica uscita",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def edit_leave(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_permissions(interaction):
            return

        settings = await self.cog.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        await interaction.response.send_modal(
            WelcomeEditorModal(
                self.cog,
                "leave",
                settings,
            )
        )

    @discord.ui.button(
        label="Anteprima benvenuto",
        emoji="👁️",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def preview_welcome(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_permissions(interaction):
            return

        if not isinstance(interaction.user, discord.Member):
            return

        settings = await self.cog.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        embed = self.cog.create_embed(
            interaction.user,
            settings,
            leaving=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Anteprima uscita",
        emoji="👁️",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def preview_leave(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not await self.check_permissions(interaction):
            return

        if not isinstance(interaction.user, discord.Member):
            return

        settings = await self.cog.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        embed = self.cog.create_embed(
            interaction.user,
            settings,
            leaving=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -------------------- CREAZIONE EMBED --------------------

    def create_embed(
        self,
        member: discord.Member,
        settings: dict,
        leaving: bool = False,
    ) -> discord.Embed:
        if leaving:
            prefix = "leave"
        else:
            prefix = "welcome"

        title = settings[f"{prefix}_title"]
        description = settings[f"{prefix}_description"]
        color_value = settings[f"{prefix}_color"]
        image = settings[f"{prefix}_image"]
        footer = settings[f"{prefix}_footer"]

        try:
            color = discord.Color(int(color_value.lstrip("#"), 16))
        except (ValueError, AttributeError):
            color = (
                discord.Color.from_rgb(237, 85, 101)
                if leaving
                else discord.Color.from_rgb(153, 102, 255)
            )

        embed = discord.Embed(
            title=format_message(title, member),
            description=format_message(description, member),
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        if member.guild.icon:
            embed.set_author(
                name=member.guild.name,
                icon_url=member.guild.icon.url,
            )
        else:
            embed.set_author(name=member.guild.name)

        embed.set_thumbnail(url=member.display_avatar.url)

        if image and valid_image_url(image):
            embed.set_image(url=image)

        if footer:
            embed.set_footer(
                text=format_message(footer, member)
            )

        return embed

    # -------------------- INVIO AUTOMATICO --------------------

    async def send_welcome(
        self,
        member: discord.Member,
        leaving: bool = False,
    ) -> bool:
        settings = await self.bot.db.get_welcome_settings(
            member.guild.id
        )

        channel_id = (
            settings["leave_channel"]
            if leaving
            else settings["welcome_channel"]
        )

        if not channel_id:
            return False

        channel = member.guild.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return False

        try:
            await channel.send(
                embed=self.create_embed(
                    member,
                    settings,
                    leaving,
                )
            )
            return True

        except discord.HTTPException:
            log.exception(
                "Impossibile inviare il messaggio nel server %s",
                member.guild.id,
            )
            return False

    # -------------------- PANNELLO --------------------

    @app_commands.command(
        name="configura_benvenuto",
        description="Apri il pannello per personalizzare entrate e uscite.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configura_benvenuto(
        self,
        interaction: discord.Interaction,
    ) -> None:
        embed = discord.Embed(
            title="✨ Configurazione messaggi",
            description=(
                "Personalizza i messaggi automatici del server.\n\n"
                "👋 **Benvenuto:** modifica il messaggio inviato "
                "quando un utente entra.\n\n"
                "🚪 **Uscita:** modifica il messaggio inviato "
                "quando un utente lascia il server.\n\n"
                "👁️ **Anteprima:** controlla il risultato prima "
                "di utilizzarlo."
            ),
            color=discord.Color.from_rgb(153, 102, 255),
        )

        embed.set_footer(
            text="Le modifiche vengono salvate automaticamente."
        )

        await interaction.response.send_message(
            embed=embed,
            view=WelcomePanelView(self),
            ephemeral=True,
        )

    # -------------------- CONFIGURAZIONE CANALI --------------------

    @app_commands.command(
        name="imposta_benvenuto",
        description="Imposta il canale dei messaggi di entrata.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def imposta_benvenuto(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Questo comando può essere usato solo in un server.",
                ephemeral=True,
            )
            return

        await self.bot.db.update_welcome_channel(
            interaction.guild_id,
            "welcome",
            canale.id,
        )

        await interaction.response.send_message(
            f"✅ Canale di benvenuto impostato su {canale.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="imposta_uscite",
        description="Imposta il canale dei messaggi di uscita.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def imposta_uscite(
        self,
        interaction: discord.Interaction,
        canale: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Questo comando può essere usato solo in un server.",
                ephemeral=True,
            )
            return

        await self.bot.db.update_welcome_channel(
            interaction.guild_id,
            "leave",
            canale.id,
        )

        await interaction.response.send_message(
            f"✅ Canale delle uscite impostato su {canale.mention}.",
            ephemeral=True,
        )

    # -------------------- COMANDI TEST --------------------

    @app_commands.command(
        name="test_benvenuto",
        description="Visualizza un'anteprima del messaggio di benvenuto.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test_benvenuto(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        settings = await self.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        await interaction.response.send_message(
            embed=self.create_embed(
                interaction.user,
                settings,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="test_uscita",
        description="Visualizza un'anteprima del messaggio di uscita.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test_uscita(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        settings = await self.bot.db.get_welcome_settings(
            interaction.guild_id
        )

        await interaction.response.send_message(
            embed=self.create_embed(
                interaction.user,
                settings,
                leaving=True,
            ),
            ephemeral=True,
        )

    # -------------------- EVENTI AUTOMATICI --------------------

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ) -> None:
        await self.send_welcome(member)

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member: discord.Member,
    ) -> None:
        await self.send_welcome(member, leaving=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))