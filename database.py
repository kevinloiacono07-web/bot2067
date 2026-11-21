"""Persistenza SQLite per i webhook creati dal bot.

Nel database NON viene mai salvato il token dei webhook: il bot lo ottiene da Discord
(grazie al permesso Gestisci webhook) solo nel momento in cui serve e lo tiene in memoria.
Qui si salvano soltanto identificativo, server, canale, nome e qualche metadato.
"""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, TypeVar

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id    INTEGER PRIMARY KEY,
    guild_id      INTEGER NOT NULL,
    channel_id    INTEGER NOT NULL,
    name          TEXT    NOT NULL,
    custom_avatar INTEGER NOT NULL DEFAULT 0,
    created_by    INTEGER NOT NULL,
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_webhooks_guild
ON webhooks (guild_id);

CREATE INDEX IF NOT EXISTS idx_webhooks_channel
ON webhooks (channel_id);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id    INTEGER PRIMARY KEY,
    prefix      TEXT NOT NULL DEFAULT '!',
    log_channel INTEGER,
    created_at  TEXT NOT NULL
);
"""



@dataclass(frozen=True)
class WebhookRecord:
    webhook_id: int
    guild_id: int
    channel_id: int
    name: str
    custom_avatar: bool
    created_by: int
    created_at: str


def _to_record(row: sqlite3.Row) -> WebhookRecord:
    return WebhookRecord(
        webhook_id=row["webhook_id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        name=row["name"],
        custom_avatar=bool(row["custom_avatar"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


class Database:
    """Wrapper asincrono (thread + lock) attorno a una connessione SQLite."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
        self._conn = conn

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            await asyncio.to_thread(conn.close)

    async def _run(self, func: Callable[[sqlite3.Connection], T]) -> T:
        if self._conn is None:
            raise RuntimeError("Database non inizializzato.")
        async with self._lock:
            return await asyncio.to_thread(func, self._conn)

    # ------------------------------------------------------------------ scrittura

    async def add_webhook(
        self,
        *,
        webhook_id: int,
        guild_id: int,
        channel_id: int,
        name: str,
        custom_avatar: bool,
        created_by: int,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR REPLACE INTO webhooks "
                "(webhook_id, guild_id, channel_id, name, custom_avatar, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (webhook_id, guild_id, channel_id, name, int(custom_avatar), created_by, created_at),
            )
            conn.commit()

        await self._run(op)

    async def remove_webhook(self, webhook_id: int) -> bool:
        def op(conn: sqlite3.Connection) -> bool:
            cur = conn.execute("DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,))
            conn.commit()
            return cur.rowcount > 0

        return await self._run(op)

    async def remove_by_channel(self, channel_id: int) -> int:
        def op(conn: sqlite3.Connection) -> int:
            cur = conn.execute("DELETE FROM webhooks WHERE channel_id = ?", (channel_id,))
            conn.commit()
            return cur.rowcount

        return await self._run(op)

    async def remove_guild(self, guild_id: int) -> int:
        def op(conn: sqlite3.Connection) -> int:
            cur = conn.execute("DELETE FROM webhooks WHERE guild_id = ?", (guild_id,))
            conn.commit()
            return cur.rowcount

        return await self._run(op)

    # ------------------------------------------------------------------ lettura

    async def get_webhook(self, guild_id: int, webhook_id: int) -> Optional[WebhookRecord]:
        """Restituisce il webhook solo se appartiene al server indicato."""

        def op(conn: sqlite3.Connection) -> Optional[WebhookRecord]:
            row = conn.execute(
                "SELECT * FROM webhooks WHERE webhook_id = ? AND guild_id = ?",
                (webhook_id, guild_id),
            ).fetchone()
            return _to_record(row) if row else None

        return await self._run(op)

    async def find_by_name(self, guild_id: int, name: str) -> List[WebhookRecord]:
        def op(conn: sqlite3.Connection) -> List[WebhookRecord]:
            rows = conn.execute(
                "SELECT * FROM webhooks WHERE guild_id = ? AND name = ? COLLATE NOCASE",
                (guild_id, name),
            ).fetchall()
            return [_to_record(r) for r in rows]

        return await self._run(op)

    async def list_webhooks(self, guild_id: int) -> List[WebhookRecord]:
        def op(conn: sqlite3.Connection) -> List[WebhookRecord]:
            rows = conn.execute(
                "SELECT * FROM webhooks WHERE guild_id = ? ORDER BY name COLLATE NOCASE, webhook_id",
                (guild_id,),
            ).fetchall()
            return [_to_record(r) for r in rows]

        return await self._run(op)

    async def list_by_channel(self, channel_id: int) -> List[WebhookRecord]:
        def op(conn: sqlite3.Connection) -> List[WebhookRecord]:
            rows = conn.execute(
                "SELECT * FROM webhooks WHERE channel_id = ?", (channel_id,)
            ).fetchall()
            return [_to_record(r) for r in rows]

        return await self._run(op)

    # ------------------------------------------------------------
    # CONFIGURAZIONE SERVER
    # ------------------------------------------------------------

    async def get_guild_settings(self, guild_id: int) -> dict:
        def op(conn: sqlite3.Connection) -> dict:
            row = conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?",
                (guild_id,)
            ).fetchone()

            if row is None:
                created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

                conn.execute(
                    """
                    INSERT INTO guild_settings
                    (guild_id, prefix, log_channel, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (guild_id, "!", None, created_at)
                )
                conn.commit()

                return {
                    "guild_id": guild_id,
                    "prefix": "!",
                    "log_channel": None,
                    "created_at": created_at,
                }

            return dict(row)

        return await self._run(op)

    async def update_guild_prefix(self, guild_id: int, prefix: str) -> None:
        await self.get_guild_settings(guild_id)

        def op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE guild_settings SET prefix = ? WHERE guild_id = ?",
                (prefix, guild_id)
            )
            conn.commit()

        await self._run(op)

    async def update_log_channel(self, guild_id: int, channel_id: int | None) -> None:
        await self.get_guild_settings(guild_id)

        def op(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE guild_settings SET log_channel = ? WHERE guild_id = ?",
                (channel_id, guild_id)
            )
            conn.commit()

        await self._run(op)