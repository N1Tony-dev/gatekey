"""
Zapamietuje udana weryfikacje Discord na TYM komputerze, zeby Gatekey nie
prosil o ponowna autoryzacje przy kazdym uruchomieniu. Wpis jest powiazany
z identyfikatorem tej konkretnej maszyny - skopiowanie calego folderu
(.exe + .env + plik sesji) na inny komputer NIE przenosi odblokowania,
bo identyfikator maszyny sie nie zgodzi i Gatekey poprosi o autoryzacje
od nowa.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from config import app_dir

SESSION_FILE = app_dir() / ".session"


def machine_id() -> str:
    return format(uuid.getnode(), "x")


def save_verified_session(discord_user_id: str) -> None:
    data = {
        "machine_id": machine_id(),
        "discord_user_id": discord_user_id,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")


def has_valid_session() -> bool:
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("discord_user_id")) and data.get("machine_id") == machine_id()


def clear_session() -> None:
    try:
        SESSION_FILE.unlink()
    except FileNotFoundError:
        pass
