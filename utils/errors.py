"""Errori "mostrabili" all'utente e traduzione degli errori HTTP di Discord."""
from __future__ import annotations

from typing import Optional

import discord


class BotUserError(Exception):
    """Errore previsto: titolo e descrizione vengono mostrati così come sono all'utente."""

    def __init__(self, title: str, description: Optional[str] = None) -> None:
        super().__init__(title)
        self.title = title
        self.description = description


def describe_http_error(exc: discord.HTTPException) -> str:
    """Spiega in italiano un errore restituito dall'API di Discord (senza dettagli sensibili)."""
    code = getattr(exc, "code", 0)
    if code == 30007:
        return "Hai raggiunto il limite di 15 webhook per questo canale. Rimuovine uno e riprova."
    if code == 50013 or isinstance(exc, discord.Forbidden):
        return "Non ho i permessi necessari per completare l'operazione."
    if code == 50035:
        return "Discord ha rifiutato i dati inviati (ad esempio un nome o un testo non valido)."
    if code == 40005 or exc.status == 413:
        return "Il contenuto o i file allegati sono troppo grandi."
    if exc.status == 429:
        return "Discord sta limitando le richieste: attendi qualche secondo e riprova."
    return f"Discord ha risposto con un errore (codice {code or exc.status})."
