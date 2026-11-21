"""Embed standard per conferme, errori e avvisi."""
from __future__ import annotations

from typing import Optional

import discord

COLOUR_SUCCESS = discord.Colour(0x57F287)
COLOUR_ERROR = discord.Colour(0xED4245)
COLOUR_WARNING = discord.Colour(0xFEE75C)
COLOUR_INFO = discord.Colour(0x5865F2)


def _build(emoji: str, title: str, description: Optional[str], colour: discord.Colour) -> discord.Embed:
    return discord.Embed(title=f"{emoji} {title}", description=description, colour=colour)


def success(title: str, description: Optional[str] = None) -> discord.Embed:
    return _build("✅", title, description, COLOUR_SUCCESS)


def error(title: str, description: Optional[str] = None) -> discord.Embed:
    return _build("❌", title, description, COLOUR_ERROR)


def warning(title: str, description: Optional[str] = None) -> discord.Embed:
    return _build("⚠️", title, description, COLOUR_WARNING)


def info(title: str, description: Optional[str] = None) -> discord.Embed:
    return _build("ℹ️", title, description, COLOUR_INFO)
