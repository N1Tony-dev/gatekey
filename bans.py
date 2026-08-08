"""
Sprawdzanie bana konta Discord - dane w tym samym repo co wiazania
urzadzen (gatekey-devices/bans.json), ten sam ograniczony token.
Zarzadzanie banami (dodawanie/usuwanie) odbywa sie z osobnej, statycznej
strony administracyjnej (docs/index.html w repo gatekey), nie z tego
modulu - ten modul TYLKO odczytuje, nigdy nie zapisuje.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import requests

from device_binding import GITHUB_OWNER, BINDINGS_REPO, _headers

BANS_PATH = "bans.json"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{BINDINGS_REPO}/contents/{BANS_PATH}"
HTTP_TIMEOUT_S = 10


def check_ban(discord_user_id: str) -> tuple[bool, str | None]:
    """Zwraca (czy_zbanowany, komunikat). Kazdy blad (brak pliku bans.json,
    problem z siecia) jest traktowany jako "nie zbanowany" - awaria tej
    kontroli nigdy nie moze byc powodem blokady dostepu."""
    try:
        resp = requests.get(API_URL, headers=_headers(), timeout=HTTP_TIMEOUT_S)
        if resp.status_code == 404:
            return False, None
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode("utf-8")
        bans = json.loads(content)
    except (requests.RequestException, ValueError, KeyError):
        return False, None

    entry = bans.get(discord_user_id)
    if not entry or not entry.get("banned_until"):
        return False, None

    try:
        banned_until = datetime.fromisoformat(entry["banned_until"].replace("Z", "+00:00"))
    except ValueError:
        return False, None

    if banned_until <= datetime.now(timezone.utc):
        return False, None

    formatted = banned_until.strftime("%Y-%m-%d %H:%M UTC")
    reason = entry.get("reason") or ""
    suffix = f" Powod: {reason}" if reason else ""
    return True, f"Zbanowano do {formatted}.{suffix}"
