"""
Wczytuje i waliduje ustawienia z .env potrzebne do bramki Discord (Gatekey).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def app_dir() -> Path:
    """Folder z .env - obok .exe gdy zapakowane (PyInstaller), obok tego
    pliku w trybie deweloperskim. cwd nie jest tu wiarygodne: po spakowaniu
    zalezy od tego, jak uzytkownik uruchomil .exe (skrot, PowerShell, itd.)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


load_dotenv(app_dir() / ".env")

REQUIRED_KEYS = (
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_REQUIRED_ROLE_ID",
)

DEFAULT_REDIRECT_PORT = 47624


class ConfigError(Exception):
    """Brakuje wymaganych wartosci w .env - patrz .env.example."""

    def __init__(self, missing_keys: list[str]):
        self.missing_keys = missing_keys
        keys = ", ".join(missing_keys)
        super().__init__(f"Brakuje ustawien w .env: {keys}")


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    bot_token: str
    guild_id: str
    required_role_id: str
    redirect_port: int

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.redirect_port}/callback"


def load_config() -> Config:
    missing = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
    if missing:
        raise ConfigError(missing)

    port_raw = os.environ.get("DISCORD_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT))
    try:
        port = int(port_raw)
    except ValueError:
        port = DEFAULT_REDIRECT_PORT

    return Config(
        client_id=os.environ["DISCORD_CLIENT_ID"],
        client_secret=os.environ["DISCORD_CLIENT_SECRET"],
        bot_token=os.environ["DISCORD_BOT_TOKEN"],
        guild_id=os.environ["DISCORD_GUILD_ID"],
        required_role_id=os.environ["DISCORD_REQUIRED_ROLE_ID"],
        redirect_port=port,
    )
