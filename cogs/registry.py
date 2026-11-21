"""Registro automatico delle attività Discord."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("bot.registry")


REGISTRY_LABELS = {
    "members": "👋 Entrate e uscite",
    "nicknames": "✏️ Modifiche nickname",
    "roles": "🎭 Ruoli aggiunti e rimossi",
    "messages_deleted": "🗑️ Messaggi eliminati",
    "messages_edited": "✏️ Messaggi modificati",
    "channels": "🏷️ Modifiche ai canali",
    "moderation": "🔨 Ban e unban",
}


class RegistryConfigView(discord.ui.View):
    def __init__(
        self,
        cog: "Registry",
        guild_id: int,
        preferences: dict,
    ) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.preferences = preferences
        self.buttons: dict[str, discord.ui.Button] = {}

        for index, (key, label) in enumerate(REGISTRY_LABELS.items()):
            button = discord.ui.Button(
                label=self.button_label(key),
                style=self.button_style(key),
                row=index // 4,
            )

            async def callback(
                interaction: discord.Interaction,
                option: str = key,
            ) -> None:
                await self.toggle(interaction, option)

            button.callback = callback
            self.buttons[key] = button
            self.add_item(button)

    def button_label(self, key: str) -> str:
        status = "ON 🟢" if self.preferences[key] else "OFF 🔴"
        return f"{REGISTRY_LABELS[key]}: {status}"

    def button_style(self, key: str) -> discord.ButtonStyle:
        return (
            discord.ButtonStyle.success
            if self.preferences[key]
            else discord.ButtonStyle.danger
        )

    def refresh_buttons(self) -> None:
        for key, button in self.buttons.items():
            button.label = self.button_label(key)
            button.style = self.button_style(key)

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📋 Configurazione registri",
            description=(
                "Usa i pulsanti per attivare o disattivare "
                "le categorie di registrazione.\n\n"
                "🟢 **ON:** registrazione attiva\n"
                "🔴 **OFF:** registrazione disattivata"
            ),
            color=discord.Color.blurple(),
        )

        for key, label in REGISTRY_LABELS.items():
            status = "🟢 Attivo" if self.preferences[key] else "🔴 Disattivo"
            embed.add_field(
                name=label,
                value=status,
                inline=True,
            )

        embed.set_footer(
            text="Le modifiche vengono salvate automaticamente."
        )
        return embed

    async def toggle(
        self,
        interaction: discord.Interaction,
        option: str,
    ) -> None:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "Questo pannello appartiene a un altro server.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Non puoi modificare questa configurazione.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ Non hai il permesso Gestire server.",
                ephemeral=True,
            )
            return

        new_value = not self.preferences[option]

        await self.cog.bot.db.update_registry_preference(
            self.guild_id,
            option,
            new_value,
        )

        self.preferences[option] = new_value
        self.refresh_buttons()

        await interaction.response.edit_message(
            embed=self.create_embed(),
            view=self,
        )

    async def on_timeout(self) -> None:
        for button in self.children:
            button.disabled = True


class Registry(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -------------------- INVIO REGISTRI --------------------

    async def send_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        color: discord.Color = discord.Color.blurple(),
        option: str | None = None,
    ) -> None:
        if option is not None:
            preferences = await self.bot.db.get_registry_preferences(
                guild.id
            )

            if not preferences.get(option, True):
                return

        settings = await self.bot.db.get_guild_settings(guild.id)
        channel_id = settings.get("log_channel")

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title=title,
            description=description[:4000],
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{guild.name} • Registro attività")

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception(
                "Impossibile inviare il registro nel server %s",
                guild.id,
            )

    # -------------------- CONFIGURAZIONE CANALE --------------------

    @app_commands.command(
        name="setup_registri",
        description="Crea automaticamente il canale del registro attività.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_registri(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                "Usa questo comando in un server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            category = discord.utils.get(
                guild.categories,
                name="꒰ 📋 ꒱ REGISTRI",
            )

            if category is None:
                category = await guild.create_category(
                    "꒰ 📋 ꒱ REGISTRI",
                    reason="Configurazione registro attività",
                )

            channel = discord.utils.get(
                category.text_channels,
                name="【📑】・registro-attività",
            )

            if channel is None:
                channel = await guild.create_text_channel(
                    "【📑】・registro-attività",
                    category=category,
                    reason="Configurazione registro attività",
                )

            await self.bot.db.update_log_channel(
                guild.id,
                channel.id,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Mi serve il permesso Gestire canali.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:
            log.exception("Errore nella configurazione dei registri.")
            await interaction.followup.send(
                "❌ Errore durante la configurazione.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Registro configurato!\nCanale: {channel.mention}",
            ephemeral=True,
        )

        await self.send_log(
            guild,
            "📋 Registro attività attivato",
            f"Configurato da {interaction.user.mention}.",
            discord.Color.green(),
        )

    # -------------------- PANNELLO ON/OFF --------------------

    @app_commands.command(
        name="configura_registri",
        description="Apri il pannello per scegliere quali registri attivare.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configura_registri(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Usa questo comando in un server.",
                ephemeral=True,
            )
            return

        settings = await self.bot.db.get_guild_settings(
            interaction.guild.id
        )

        if not settings.get("log_channel"):
            await interaction.response.send_message(
                "❌ Prima configura il canale con `/setup_registri`.",
                ephemeral=True,
            )
            return

        preferences = await self.bot.db.get_registry_preferences(
            interaction.guild.id
        )

        view = RegistryConfigView(
            self,
            interaction.guild.id,
            preferences,
        )

        await interaction.response.send_message(
            embed=view.create_embed(),
            view=view,
            ephemeral=True,
        )

    # -------------------- ENTRATE E USCITE --------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.send_log(
            member.guild,
            "👋 Nuovo membro",
            f"**Utente:** {member.mention}\n"
            f"**Nome:** {member}\n"
            f"**ID:** `{member.id}`\n"
            f"**Account creato:** "
            f"<t:{int(member.created_at.timestamp())}:R>",
            discord.Color.green(),
            option="members",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.send_log(
            member.guild,
            "🚪 Membro uscito o rimosso",
            f"**Utente:** {member}\n"
            f"**ID:** `{member.id}`",
            discord.Color.red(),
            option="members",
        )

    # -------------------- MODIFICHE MEMBRI --------------------

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        if before.nick != after.nick:
            old_nick = before.nick or before.name
            new_nick = after.nick or after.name

            await self.send_log(
                after.guild,
                "✏️ Nickname modificato",
                f"**Utente:** {after.mention}\n"
                f"**Prima:** `{old_nick}`\n"
                f"**Dopo:** `{new_nick}`",
                discord.Color.orange(),
                option="nicknames",
            )

        old_roles = set(before.roles)
        new_roles = set(after.roles)

        added_roles = new_roles - old_roles
        removed_roles = old_roles - new_roles

        added_roles.discard(after.guild.default_role)
        removed_roles.discard(after.guild.default_role)

        if added_roles or removed_roles:
            changes = []

            if added_roles:
                changes.append(
                    "**Ruoli aggiunti:** "
                    + ", ".join(role.mention for role in added_roles)
                )

            if removed_roles:
                changes.append(
                    "**Ruoli rimossi:** "
                    + ", ".join(role.mention for role in removed_roles)
                )

            await self.send_log(
                after.guild,
                "🎭 Ruoli modificati",
                f"**Utente:** {after.mention}\n"
                f"**ID:** `{after.id}`\n\n"
                + "\n".join(changes),
                discord.Color.orange(),
                option="roles",
            )

    # -------------------- MESSAGGI DEL BOT --------------------

    @commands.Cog.listener()
    async def on_message_edit(
        self,
        before: discord.Message,
        after: discord.Message,
    ) -> None:
        if self.bot.user is None:
            return

        if before.author.id != self.bot.user.id:
            return

        if before.guild is None or before.content == after.content:
            return

        await self.send_log(
            before.guild,
            "✏️ Messaggio del bot modificato",
            f"**Canale:** {before.channel.mention}\n"
            f"**Prima:**\n{before.content[:700] or '*Vuoto*'}\n\n"
            f"**Dopo:**\n{after.content[:700] or '*Vuoto*'}",
            discord.Color.orange(),
            option="messages_edited",
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self,
        payload: discord.RawMessageDeleteEvent,
    ) -> None:
        message = payload.cached_message

        if message is None or self.bot.user is None:
            return

        if message.author.id != self.bot.user.id or message.guild is None:
            return

        await self.send_log(
            message.guild,
            "🗑️ Messaggio del bot eliminato",
            f"**Canale:** {message.channel.mention}\n"
            f"**Contenuto:** "
            f"{message.content[:1500] or '*Nessun testo*'}",
            discord.Color.orange(),
            option="messages_deleted",
        )

    # -------------------- CANALI --------------------

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel: discord.abc.GuildChannel,
    ) -> None:
        await self.send_log(
            channel.guild,
            "➕ Canale creato",
            f"**Nome:** {channel.name}\n"
            f"**ID:** `{channel.id}`",
            discord.Color.green(),
            option="channels",
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel: discord.abc.GuildChannel,
    ) -> None:
        await self.send_log(
            channel.guild,
            "🗑️ Canale eliminato",
            f"**Nome:** {channel.name}\n"
            f"**ID:** `{channel.id}`",
            discord.Color.red(),
            option="channels",
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes = []

        if before.name != after.name:
            changes.append(
                f"**Nome:** `{before.name}` → `{after.name}`"
            )

        if before.category_id != after.category_id:
            old_category = before.category.name if before.category else "Nessuna"
            new_category = after.category.name if after.category else "Nessuna"
            changes.append(
                f"**Categoria:** `{old_category}` → `{new_category}`"
            )

        for attribute, label in (
            ("topic", "Descrizione"),
            ("slowmode_delay", "Modalità lenta"),
            ("nsfw", "Contenuti NSFW"),
            ("bitrate", "Bitrate"),
            ("user_limit", "Limite utenti"),
        ):
            old_value = getattr(before, attribute, None)
            new_value = getattr(after, attribute, None)

            if old_value != new_value:
                changes.append(
                    f"**{label}:** `{old_value}` → `{new_value}`"
                )

        if before.overwrites != after.overwrites:
            changes.append("**Permessi del canale:** modificati")

        if not changes:
            return

        await self.send_log(
            after.guild,
            "⚙️ Canale modificato",
            f"**Canale:** {after.name}\n\n" + "\n".join(changes),
            discord.Color.orange(),
            option="channels",
        )

    # -------------------- BAN E UNBAN --------------------

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: discord.User,
    ) -> None:
        await self.send_log(
            guild,
            "🔨 Utente bannato",
            f"**Utente:** {user}\n**ID:** `{user.id}`",
            discord.Color.red(),
            option="moderation",
        )

    @commands.Cog.listener()
    async def on_member_unban(
        self,
        guild: discord.Guild,
        user: discord.User,
    ) -> None:
        await self.send_log(
            guild,
            "🔓 Utente sbannato",
            f"**Utente:** {user}\n**ID:** `{user.id}`",
            discord.Color.green(),
            option="moderation",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Registry(bot))
