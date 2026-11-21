"""Gestione dei webhook tramite slash command.

Comandi: /crea_webhook, /messaggio, /embed_messaggio, /rimuovi_webhook.

Sicurezza:
- tutti i comandi richiedono "Gestisci webhook" o "Amministratore" e funzionano solo nei server;
- il token dei webhook non viene mai salvato né mostrato: il bot lo ottiene da Discord
  solo al momento dell'uso (fetch_webhook) e lo tiene in memoria;
- ogni ricerca nel database è filtrata per server, e il webhook recuperato da Discord
  viene ricontrollato (guild_id) prima dell'uso.
"""
import io
import logging
import re
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from database import WebhookRecord
from utils import embeds
from utils.attachments import read_image_attachment
from utils.avatars import get_server_avatar
from utils.errors import BotUserError, describe_http_error
from utils.permissions import allowed_mentions_for, has_webhook_rights, webhook_manager_check

log = logging.getLogger(__name__)

FORBIDDEN_NAME_PARTS = ("clyde", "discord")  # Discord vieta queste parole nei nomi dei webhook
EMBED_TOTAL_LIMIT = 6000

COLOUR_NAMES = {
    "rosso": 0xED4245,
    "verde": 0x57F287,
    "blu": 0x3498DB,
    "giallo": 0xFEE75C,
    "arancione": 0xE67E22,
    "viola": 0x9B59B6,
    "rosa": 0xEB459E,
    "nero": 0x23272A,
    "bianco": 0xFFFFFF,
    "grigio": 0x99AAB5,
    "blurple": 0x5865F2,
}
DEFAULT_EMBED_COLOUR = 0x5865F2


# ---------------------------------------------------------------------- helper


def normalize_text(value: str) -> str:
    """Nei campi degli slash command non si può andare a capo: la sequenza \\n diventa un a capo."""
    return value.replace("\\n", "\n").strip()


def clean_field(value: Optional[str], max_length: int, label: str) -> Optional[str]:
    if value is None:
        return None
    text = normalize_text(value)
    if not text:
        return None
    if len(text) > max_length:
        raise BotUserError(f"«{label}» troppo lungo", f"Il limite è di {max_length} caratteri.")
    return text


def parse_colour(value: Optional[str]) -> discord.Colour:
    if value is None or not value.strip():
        return discord.Colour(DEFAULT_EMBED_COLOUR)
    raw = value.strip().lower()
    if raw in COLOUR_NAMES:
        return discord.Colour(COLOUR_NAMES[raw])
    if raw.startswith("#"):
        raw = raw[1:]
    elif raw.startswith("0x"):
        raw = raw[2:]
    if re.fullmatch(r"[0-9a-f]{3}", raw):
        raw = "".join(ch * 2 for ch in raw)
    if re.fullmatch(r"[0-9a-f]{6}", raw):
        return discord.Colour(int(raw, 16))
    raise BotUserError(
        "Colore non valido",
        "Usa un codice esadecimale come `#5865F2` oppure un nome: rosso, verde, blu, giallo, "
        "arancione, viola, rosa, nero, bianco, grigio.",
    )


def validate_webhook_name(raw: str) -> str:
    name = raw.strip()
    if not 1 <= len(name) <= 80:
        raise BotUserError("Nome non valido", "Il nome del webhook deve avere tra 1 e 80 caratteri.")
    lowered = name.lower()
    for forbidden in FORBIDDEN_NAME_PARTS:
        if forbidden in lowered:
            raise BotUserError(
                "Nome non consentito",
                f"Discord non permette di usare «{forbidden}» nel nome di un webhook.",
            )
    return name


def avatar_kwargs(record: WebhookRecord, guild: discord.Guild) -> dict:
    """Se il webhook non ha un'immagine personalizzata, a ogni invio usa l'icona attuale del server."""
    if not record.custom_avatar and guild.icon is not None:
        return {"avatar_url": guild.icon.url}
    return {}


# ---------------------------------------------------------------------- view


class ConfirmDeleteView(discord.ui.View):
    """Conferma prima di eliminare definitivamente un webhook."""

    def __init__(
        self,
        cog: "WebhookManager",
        owner_id: int,
        record: WebhookRecord,
        source_interaction: discord.Interaction,
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.owner_id = owner_id
        self.record = record
        self.source_interaction = source_interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error("Non puoi usare questi pulsanti", "Solo chi ha eseguito il comando può confermare."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Elimina definitivamente", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            result = await self.cog.delete_webhook(interaction, self.record)
        except BotUserError as exc:
            result = embeds.error(exc.title, exc.description)
        except discord.HTTPException as exc:
            log.warning("Eliminazione webhook non riuscita: %s", exc)
            result = embeds.error("Eliminazione non riuscita", describe_http_error(exc))
        await interaction.edit_original_response(embed=result, view=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            embed=embeds.info("Operazione annullata", "Il webhook non è stato eliminato."),
            view=None,
        )

    async def on_timeout(self) -> None:
        try:
            await self.source_interaction.edit_original_response(
                embed=embeds.info("Richiesta scaduta", "Non hai confermato in tempo: il webhook non è stato eliminato."),
                view=None,
            )
        except discord.HTTPException:
            pass


class EmbedPreviewView(discord.ui.View):
    """Anteprima dell'embed con pulsanti Invia / Annulla."""

    def __init__(
        self,
        cog: "WebhookManager",
        owner_id: int,
        record: WebhookRecord,
        embed: discord.Embed,
        files_data: List[Tuple[str, bytes]],
        source_interaction: discord.Interaction,
    ) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.record = record
        self.embed = embed
        self.files_data = files_data
        self.source_interaction = source_interaction

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=embeds.error("Non puoi usare questi pulsanti", "Solo chi ha eseguito il comando può inviare."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Invia", style=discord.ButtonStyle.success, emoji="📨")
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.stop()
        try:
            await self.cog.send_embed(interaction, self.record, self.embed, self.files_data)
            result = embeds.success(
                "Embed inviato",
                f"Messaggio pubblicato in <#{self.record.channel_id}> tramite **{self.record.name}**.",
            )
        except BotUserError as exc:
            result = embeds.error(exc.title, exc.description)
        except discord.HTTPException as exc:
            log.warning("Invio embed non riuscito: %s", exc)
            result = embeds.error("Invio non riuscito", describe_http_error(exc))
        await interaction.edit_original_response(content=None, embed=result, view=None, attachments=[])

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(
            content=None,
            embed=embeds.info("Invio annullato", "Nessun messaggio è stato inviato."),
            view=None,
            attachments=[],
        )

    async def on_timeout(self) -> None:
        try:
            await self.source_interaction.edit_original_response(
                content=None,
                embed=embeds.info("Anteprima scaduta", "Non hai confermato in tempo: nessun messaggio è stato inviato."),
                view=None,
                attachments=[],
            )
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------- cog


class WebhookManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------ logica condivisa

    async def lookup_record(self, guild: discord.Guild, identifier: str) -> WebhookRecord:
        """Trova un webhook salvato nel database, solo tra quelli del server indicato."""
        db = self.bot.db
        identifier = identifier.strip()
        record: Optional[WebhookRecord] = None

        if identifier.isdigit() and len(identifier) <= 19 and int(identifier) < 2**63:
            record = await db.get_webhook(guild.id, int(identifier))

        if record is None and identifier:
            matches = await db.find_by_name(guild.id, identifier)
            if len(matches) == 1:
                record = matches[0]
            elif len(matches) > 1:
                raise BotUserError(
                    "Più webhook con lo stesso nome",
                    "Seleziona il webhook dai suggerimenti che compaiono mentre scrivi nel campo **webhook**.",
                )

        if record is None:
            raise BotUserError(
                "Webhook non trovato",
                "Non esiste nessun webhook con questo nome in questo server. "
                "Sceglilo dai suggerimenti oppure creane uno con `/crea_webhook`.",
            )
        return record

    async def fetch_usable_webhook(self, guild: discord.Guild, record: WebhookRecord) -> discord.Webhook:
        """Recupera il webhook da Discord (con token, solo in memoria) e verifica che sia di questo server."""
        if record.guild_id != guild.id:
            raise BotUserError("Webhook non valido", "Questo webhook non appartiene al server corrente.")
        try:
            webhook = await self.bot.fetch_webhook(record.webhook_id)
        except discord.NotFound:
            await self.bot.db.remove_webhook(record.webhook_id)
            raise BotUserError(
                "Webhook non più esistente",
                "Questo webhook è stato eliminato direttamente da Discord, quindi l'ho tolto dall'elenco. "
                "Creane uno nuovo con `/crea_webhook`.",
            ) from None
        except discord.Forbidden:
            raise BotUserError(
                "Permessi mancanti",
                "Non riesco a leggere questo webhook: mi serve il permesso **Gestisci webhook**.",
            ) from None

        if webhook.guild_id != guild.id:
            raise BotUserError("Webhook non valido", "Questo webhook non appartiene al server corrente.")
        if webhook.token is None:
            raise BotUserError(
                "Webhook non utilizzabile",
                "Discord non mi ha fornito le credenziali per usare questo webhook.",
            )
        return webhook

    async def deliver(
        self,
        webhook: discord.Webhook,
        record: WebhookRecord,
        guild: discord.Guild,
        permissions: discord.Permissions,
        **content,
    ) -> None:
        """Invia un messaggio tramite il webhook (non tramite l'account del bot)."""
        kwargs = dict(content)
        kwargs["allowed_mentions"] = allowed_mentions_for(permissions)
        kwargs.update(avatar_kwargs(record, guild))
        try:
            await webhook.send(**kwargs)
        except discord.NotFound:
            await self.bot.db.remove_webhook(record.webhook_id)
            raise BotUserError(
                "Webhook non più esistente",
                "Il webhook è stato eliminato da Discord mentre stavo inviando, quindi l'ho tolto dall'elenco.",
            ) from None

    async def send_embed(
        self,
        interaction: discord.Interaction,
        record: WebhookRecord,
        embed: discord.Embed,
        files_data: List[Tuple[str, bytes]],
    ) -> None:
        guild = interaction.guild
        fresh = await self.bot.db.get_webhook(guild.id, record.webhook_id)
        if fresh is None:
            raise BotUserError("Webhook non trovato", "Questo webhook è stato rimosso nel frattempo.")
        webhook = await self.fetch_usable_webhook(guild, fresh)

        extra = {}
        if files_data:
            extra["files"] = [discord.File(io.BytesIO(data), filename=name) for name, data in files_data]
        await self.deliver(webhook, fresh, guild, interaction.permissions, embed=embed, **extra)

    async def delete_webhook(self, interaction: discord.Interaction, record: WebhookRecord) -> discord.Embed:
        guild = interaction.guild
        if record.guild_id != guild.id:
            raise BotUserError("Webhook non valido", "Questo webhook non appartiene al server corrente.")

        already_gone = False
        try:
            webhook = await self.bot.fetch_webhook(record.webhook_id)
        except discord.NotFound:
            already_gone = True
        else:
            if webhook.guild_id != guild.id:
                raise BotUserError("Webhook non valido", "Questo webhook non appartiene al server corrente.")
            try:
                await webhook.delete(reason=f"Rimosso da {interaction.user} (ID {interaction.user.id}) con /rimuovi_webhook")
            except discord.NotFound:
                already_gone = True

        await self.bot.db.remove_webhook(record.webhook_id)

        if already_gone:
            return embeds.success(
                "Webhook rimosso dall'elenco",
                f"**{record.name}** non esisteva più su Discord: ho eliminato solo il riferimento salvato.",
            )
        return embeds.success("Webhook eliminato", f"**{record.name}** è stato eliminato da Discord e dal database.")

    # ------------------------------------------------------------ autocompletamento

    async def webhook_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        if interaction.guild is None or not has_webhook_rights(interaction.permissions):
            return []
        records = await self.bot.db.list_webhooks(interaction.guild.id)
        needle = current.strip().lower()
        choices: List[app_commands.Choice[str]] = []
        for record in records:
            channel = interaction.guild.get_channel(record.channel_id)
            channel_name = f"#{channel.name}" if channel is not None else "canale sconosciuto"
            label = f"{record.name} • {channel_name}"[:100]
            if needle and needle not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label, value=str(record.webhook_id)))
            if len(choices) >= 25:
                break
        return choices

    # ------------------------------------------------------------ /crea_webhook

    @app_commands.command(name="crea_webhook", description="Crea un webhook nel canale in cui esegui il comando")
    @app_commands.describe(
        nome="Nome del webhook (da 1 a 80 caratteri)",
        immagine="Immagine personalizzata (facoltativa). Se omessa uso l'icona del server",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_webhooks=True)
    @webhook_manager_check()
    async def crea_webhook(
        self,
        interaction: discord.Interaction,
        nome: str,
        immagine: Optional[discord.Attachment] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

        channel = guild.get_channel(interaction.channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise BotUserError(
                "Canale non supportato",
                "Puoi creare un webhook solo in un canale testuale o di annunci (non in thread o canali vocali).",
            )
        if not has_webhook_rights(interaction.app_permissions):
            raise BotUserError(
                "Permessi del bot insufficienti",
                "In questo canale mi serve il permesso **Gestisci webhook** per poter creare il webhook.",
            )

        name = validate_webhook_name(nome)

        if immagine is not None:
            _, avatar_bytes = await read_image_attachment(immagine, "immagine")
            custom_avatar = True
            avatar_label = "Immagine personalizzata"
        else:
            avatar_bytes, source = await get_server_avatar(guild)
            custom_avatar = False
            avatar_label = "Icona del server" if source == "server" else "Immagine predefinita (il server non ha un'icona)"

        webhook = await channel.create_webhook(
            name=name,
            avatar=avatar_bytes,
            reason=f"Creato da {interaction.user} (ID {interaction.user.id}) con /crea_webhook",
        )

        try:
            await self.bot.db.add_webhook(
                webhook_id=webhook.id,
                guild_id=guild.id,
                channel_id=channel.id,
                name=name,
                custom_avatar=custom_avatar,
                created_by=interaction.user.id,
            )
        except Exception:
            log.exception("Salvataggio del webhook %s nel database non riuscito", webhook.id)
            try:
                await webhook.delete(reason="Salvataggio nel database non riuscito")
            except discord.HTTPException:
                pass
            raise BotUserError(
                "Errore interno",
                "Non sono riuscito a salvare il webhook nel database, quindi ho annullato la creazione. Riprova.",
            ) from None

        embed = embeds.success("Webhook creato", f"Il webhook **{name}** è pronto all'uso.")
        embed.add_field(name="Canale", value=channel.mention, inline=True)
        embed.add_field(name="Immagine", value=avatar_label, inline=True)
        embed.add_field(name="ID", value=f"`{webhook.id}`", inline=True)
        embed.set_footer(text="Usa /messaggio o /embed_messaggio per scrivere tramite questo webhook.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------ /messaggio

    @app_commands.command(name="messaggio", description="Invia un messaggio tramite uno dei webhook del server")
    @app_commands.describe(
        webhook="Il webhook da usare (scegli dai suggerimenti)",
        testo="Testo del messaggio. Scrivi \\n per andare a capo",
    )
    @app_commands.autocomplete(webhook=webhook_autocomplete)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_webhooks=True)
    @webhook_manager_check()
    async def messaggio(self, interaction: discord.Interaction, webhook: str, testo: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

        text = normalize_text(testo)
        if not text:
            raise BotUserError("Messaggio vuoto", "Scrivi il testo da inviare.")
        if len(text) > 2000:
            raise BotUserError("Messaggio troppo lungo", "Il limite è di 2000 caratteri.")

        record = await self.lookup_record(guild, webhook)
        hook = await self.fetch_usable_webhook(guild, record)
        await self.deliver(hook, record, guild, interaction.permissions, content=text)

        await interaction.followup.send(
            embed=embeds.success(
                "Messaggio inviato",
                f"Pubblicato in <#{record.channel_id}> tramite **{record.name}**.",
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------ /embed_messaggio

    @app_commands.command(name="embed_messaggio", description="Invia un embed personalizzato tramite un webhook")
    @app_commands.describe(
        webhook="Il webhook da usare (scegli dai suggerimenti)",
        titolo="Titolo dell'embed (facoltativo)",
        descrizione="Descrizione dell'embed. Scrivi \\n per andare a capo (facoltativo)",
        colore="Colore: codice come #5865F2 oppure nome (rosso, verde, blu...) (facoltativo)",
        autore="Nome dell'autore mostrato in alto (facoltativo)",
        immagine="Immagine grande mostrata sotto il testo (facoltativo)",
        miniatura="Piccola immagine in alto a destra (facoltativo)",
        footer="Testo in fondo all'embed (facoltativo)",
        timestamp="Mostra data e ora attuali nel footer (facoltativo)",
    )
    @app_commands.autocomplete(webhook=webhook_autocomplete)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_webhooks=True)
    @webhook_manager_check()
    async def embed_messaggio(
        self,
        interaction: discord.Interaction,
        webhook: str,
        titolo: Optional[str] = None,
        descrizione: Optional[str] = None,
        colore: Optional[str] = None,
        autore: Optional[str] = None,
        immagine: Optional[discord.Attachment] = None,
        miniatura: Optional[discord.Attachment] = None,
        footer: Optional[str] = None,
        timestamp: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild

        title_text = clean_field(titolo, 256, "titolo")
        description_text = clean_field(descrizione, 4096, "descrizione")
        author_text = clean_field(autore, 256, "autore")
        footer_text = clean_field(footer, 2048, "footer")
        colour = parse_colour(colore)

        if not any((title_text, description_text, author_text, footer_text, immagine, miniatura)):
            raise BotUserError(
                "Embed vuoto",
                "Compila almeno uno tra titolo, descrizione, autore, immagine, miniatura o footer.",
            )

        record = await self.lookup_record(guild, webhook)

        files_data: List[Tuple[str, bytes]] = []
        embed = discord.Embed(title=title_text, description=description_text, colour=colour)
        if timestamp:
            embed.timestamp = discord.utils.utcnow()
        if author_text:
            embed.set_author(name=author_text)
        if footer_text:
            embed.set_footer(text=footer_text)
        if immagine is not None:
            extension, data = await read_image_attachment(immagine, "immagine")
            files_data.append((f"immagine{extension}", data))
            embed.set_image(url=f"attachment://immagine{extension}")
        if miniatura is not None:
            extension, data = await read_image_attachment(miniatura, "miniatura")
            files_data.append((f"miniatura{extension}", data))
            embed.set_thumbnail(url=f"attachment://miniatura{extension}")

        if len(embed) > EMBED_TOTAL_LIMIT:
            raise BotUserError(
                "Embed troppo lungo",
                f"Il testo complessivo dell'embed non può superare {EMBED_TOTAL_LIMIT} caratteri.",
            )

        view = EmbedPreviewView(self, interaction.user.id, record, embed, files_data, interaction)
        await interaction.followup.send(
            content=(
                f"**Anteprima.** Verrà inviato in <#{record.channel_id}> tramite **{record.name}**. "
                "Se è tutto a posto premi **Invia**."
            ),
            embed=embed,
            files=[discord.File(io.BytesIO(data), filename=name) for name, data in files_data],
            view=view,
            ephemeral=True,
        )

    # ------------------------------------------------------------ /rimuovi_webhook

    @app_commands.command(name="rimuovi_webhook", description="Elimina un webhook da Discord e dal database")
    @app_commands.describe(webhook="Il webhook da eliminare (scegli dai suggerimenti)")
    @app_commands.autocomplete(webhook=webhook_autocomplete)
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_webhooks=True)
    @webhook_manager_check()
    async def rimuovi_webhook(self, interaction: discord.Interaction, webhook: str) -> None:
        record = await self.lookup_record(interaction.guild, webhook)

        embed = embeds.warning(
            "Eliminare questo webhook?",
            "L'operazione è definitiva: il webhook verrà cancellato da Discord e dal database.",
        )
        embed.add_field(name="Nome", value=record.name, inline=True)
        embed.add_field(name="Canale", value=f"<#{record.channel_id}>", inline=True)
        embed.add_field(name="ID", value=f"`{record.webhook_id}`", inline=True)

        view = ConfirmDeleteView(self, interaction.user.id, record, interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ------------------------------------------------------------ sincronizzazione automatica

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """Se un webhook viene eliminato a mano da Discord, toglie il riferimento dal database."""
        records = await self.bot.db.list_by_channel(channel.id)
        if not records or not hasattr(channel, "webhooks"):
            return
        try:
            existing = {hook.id for hook in await channel.webhooks()}
        except (discord.Forbidden, discord.HTTPException):
            return
        for record in records:
            if record.webhook_id not in existing:
                await self.bot.db.remove_webhook(record.webhook_id)
                log.info("Webhook %s eliminato manualmente da Discord: rimosso dal database.", record.webhook_id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        removed = await self.bot.db.remove_by_channel(channel.id)
        if removed:
            log.info("Canale %s eliminato: rimossi %d webhook dal database.", channel.id, removed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        removed = await self.bot.db.remove_guild(guild.id)
        if removed:
            log.info("Bot rimosso dal server %s: eliminati %d webhook dal database.", guild.id, removed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebhookManager(bot))
