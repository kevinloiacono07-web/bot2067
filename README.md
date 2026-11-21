# Bot Discord – Gestione Webhook e comando !dici

Bot in Python (`discord.py` 2.x) con:

- comando testuale `!dici` (il bot ripete il messaggio e cancella il comando);
- gestione completa dei webhook da Discord tramite slash command;
- avatar dei webhook = icona del server in cui si trovano;
- database SQLite persistente.

## Requisiti

- Python **3.10 o superiore**
- Un'applicazione bot creata nel [Discord Developer Portal](https://discord.com/developers/applications)

## Installazione

```bash
cd discord-webhook-bot
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

## Configurazione

1. **Token**: nel Developer Portal vai su *Bot → Reset Token*, copia il token e incollalo nel file `.env`
   al posto di `INSERISCI_QUI_IL_TOKEN_DEL_BOT`.
2. **Intent**: sempre in *Bot → Privileged Gateway Intents* attiva **Message Content Intent**
   (serve al comando `!dici`).
3. **Invito del bot**: in *OAuth2 → URL Generator* seleziona gli scope `bot` e `applications.commands`,
   oppure usa questo link sostituendo `ID_APPLICAZIONE`:

   ```
   https://discord.com/oauth2/authorize?client_id=ID_APPLICAZIONE&scope=bot%20applications.commands&permissions=536996864
   ```

   I permessi inclusi sono: Visualizza canali, Invia messaggi, Gestisci messaggi, Incorpora link,
   Allega file, Leggi cronologia messaggi, **Gestisci webhook**.

Opzioni facoltative nel `.env`:

| Variabile | Significato |
|---|---|
| `COMMAND_PREFIX` | Prefisso dei comandi testuali (default `!`) |
| `DEV_GUILD_ID` | ID di un server di test: gli slash command compaiono subito solo lì |
| `DATABASE_PATH` | Percorso del database (default `data/webhooks.db`) |

## Avvio

```bash
python main.py
```

Al primo avvio il bot crea da solo il database e sincronizza gli slash command. I comandi globali
possono impiegare qualche minuto a comparire; con `DEV_GUILD_ID` sono immediati.

## Comandi

### `!dici <testo>`
Elimina il tuo messaggio e invia un nuovo messaggio con il solo testo (il comando non è più visibile).
**Solo gli amministratori** possono usarlo; gli altri utenti ricevono un avviso di permessi insufficienti
(che sparisce dopo 10 secondi) e il loro messaggio non viene toccato.
Funziona in ogni canale in cui il bot può scrivere e cancellare messaggi. Se il testo è vuoto il bot
ti avvisa con un messaggio che sparisce dopo 10 secondi.

### `/crea_webhook nome [immagine]`
Crea un webhook nel canale in cui esegui il comando e lo salva nel database.
Se non carichi un'immagine, l'avatar è **l'icona del server** (o un'immagine predefinita se il server
non ne ha una).

### `/messaggio webhook testo`
Invia un messaggio tramite il webhook scelto (non tramite l'account del bot). Il campo `webhook`
propone i webhook del server mentre scrivi. Il messaggio viene pubblicato nel canale del webhook.

### `/embed_messaggio webhook [titolo] [descrizione] [colore] [autore] [immagine] [miniatura] [footer] [timestamp]`
Invia un embed tramite il webhook. Tutti i campi tranne `webhook` sono facoltativi (ne serve almeno uno
tra titolo, descrizione, autore, immagine, miniatura e footer). Prima dell'invio compare
un'**anteprima** visibile solo a te, con i pulsanti **Invia** e **Annulla**.

- `colore`: codice esadecimale (`#5865F2`) oppure nome (rosso, verde, blu, giallo, arancione, viola, rosa, nero, bianco, grigio).
- `immagine` e `miniatura`: file da caricare (PNG, JPG, GIF, WEBP, max 8 MB). Vengono ricaricati dal bot
  insieme al messaggio, così non scadono.

### `/rimuovi_webhook webhook`
Mostra una richiesta di conferma; se confermi, elimina il webhook da Discord e dal database.

> **A capo negli slash command**: Discord non permette di andare a capo nei campi degli slash command.
> Scrivi la sequenza `\n` dove vuoi un a capo (vale per `testo` e `descrizione`).

## Chi può fare cosa

| Azione | Chi può farla |
|---|---|
| Creare, usare e rimuovere webhook (tutti gli slash command) | Chi ha il permesso **Gestisci webhook** oppure è **Amministratore** |
| `!dici` | Solo chi ha il permesso **Amministratore** (il bot deve poter scrivere e gestire i messaggi nel canale) |

Gli slash command di gestione sono nascosti a chi non ha il permesso, e il controllo viene comunque
rifatto dal bot a ogni esecuzione. I comandi funzionano solo nei server, non nei messaggi privati.

Menzioni: nei messaggi inviati dal bot (`!dici`, `/messaggio`) `@everyone`, `@here` e i ruoli funzionano
solo se chi usa il comando ha il permesso *Menziona @everyone, @here e tutti i ruoli*; le menzioni ai singoli utenti
sono sempre consentite.

## Sicurezza

- **Token dei webhook**: non vengono mai salvati nel database, né scritti nei log, né mostrati nei messaggi.
  Il bot li richiede a Discord solo quando servono e li tiene in memoria.
- **Log**: ogni riga passa da un filtro che oscura i token (bot e webhook) anche nei traceback.
- **Isolamento tra server**: ogni ricerca nel database è filtrata per server, e il webhook recuperato da Discord
  viene ricontrollato prima dell'uso. Non è possibile usare webhook di altri server.
- **`.env`**: contiene il token del bot. Non condividerlo e non caricarlo online (è già nel `.gitignore`).
  Se pensi che il token sia stato esposto, rigeneralo dal Developer Portal.

## Avatar automatico per server

- Alla creazione, il webhook riceve come immagine l'icona del server in cui viene creato.
- A ogni invio, se non hai caricato un'immagine personalizzata, il bot usa l'**icona attuale** del server:
  se cambi l'icona, i messaggi successivi la usano subito.
- Se il server non ha un'icona, resta l'immagine predefinita in `assets/default_avatar.png`
  (puoi sostituirla con una tua immagine quadrata).

## Webhook eliminati a mano

Se elimini un webhook dalle impostazioni di Discord, il bot lo toglie dal database appena riceve la notifica.
Se per qualsiasi motivo non la ricevesse, la prima volta che provi a usarlo ti avvisa e lo rimuove dall'elenco.
Lo stesso accade se viene eliminato un canale o il bot viene rimosso dal server.

## Struttura del progetto

```
discord-webhook-bot/
├── main.py              # avvio del bot, caricamento cog, sincronizzazione slash command
├── config.py            # lettura del file .env
├── database.py          # SQLite (webhook per server/canale)
├── cogs/
│   ├── say.py           # comando !dici
│   ├── webhooks.py      # /crea_webhook, /messaggio, /embed_messaggio, /rimuovi_webhook
│   └── errors.py        # messaggi di errore chiari per utenti
├── utils/
│   ├── embeds.py        # embed di conferma/errore/avviso
│   ├── errors.py        # errori mostrabili e traduzione errori Discord
│   ├── permissions.py   # controlli permessi e menzioni
│   ├── avatars.py       # icona del server / immagine predefinita
│   ├── attachments.py   # validazione immagini caricate
│   ├── interactions.py  # risposte "solo per te"
│   └── logger.py        # log con oscuramento dei token
├── assets/default_avatar.png
├── data/                # database e log (creata automaticamente)
├── .env                 # token e impostazioni
├── .env.example
└── requirements.txt
```

## Problemi comuni

| Problema | Soluzione |
|---|---|
| "Token non valido" all'avvio | Controlla `DISCORD_TOKEN` nel `.env` (senza spazi o virgolette). |
| "Message Content Intent non attivo" | Attivalo nel Developer Portal (vedi Configurazione, punto 2). |
| Gli slash command non compaiono | Verifica di aver invitato il bot con lo scope `applications.commands`; i comandi globali possono richiedere qualche minuto (usa `DEV_GUILD_ID` per i test). |
| "Permessi del bot insufficienti" | Dai al bot il permesso **Gestisci webhook** (anche nelle impostazioni del canale). |
| `!dici` non risponde | Controlla che il bot possa **Invia messaggi** e **Gestisci messaggi** nel canale. |
| Limite raggiunto | Discord permette al massimo 15 webhook per canale. |
