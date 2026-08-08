"""
Wspolna lista "Discord user_id -> ID komputera", trzymana jako maly plik
JSON w dedykowanym repo GitHub (N1Tony-dev/gatekey-devices) - to jedyne
miejsce, gdzie rozne komputery moga sie nawzajem "zobaczyc" (lokalny plik
.session z session.py tego nie umozliwia, bo kazdy komputer ma swoj wlasny).

Twarda blokada: jedno konto Discord moze byc powiazane tylko z JEDNYM
komputerem naraz. Proba zweryfikowania tego samego konta na innym
komputerze zostaje odrzucona, dopoki administrator recznie nie usunie
wpisu z bindings.json w repo gatekey-devices.

BEZPIECZENSTWO: token ponizej ma dostep WYLACZNIE do repozytorium
gatekey-devices (Contents: read/write, nic wiecej) - to minimalizuje
szkody, jesli ktos wyciagnie go z .exe, ale nie eliminuje ryzyka calkowicie:
kazdy sekret wbudowany w dystrybuowana aplikacje jest w koncu wyciagalny
przez wystarczajaco zdeterminowana osobe. To podnosi poprzeczke bardzo
wysoko (odstrasza przypadkowe/casualowe obejscia), nie jest to jednak
zabezpieczenie klasy "nie do zlamania".
"""

from __future__ import annotations

import base64
import json
import time

import requests

GITHUB_OWNER = "N1Tony-dev"
BINDINGS_REPO = "gatekey-devices"
BINDINGS_PATH = "bindings.json"

# Token trzymany OSOBNO w device_binding_secret.py - ten plik NIGDY nie
# trafia do gita (patrz .gitignore), bo repo "gatekey" jest publiczne, a
# commitowanie tokena wprost do kodu zrodlowego byloby dostepne dla kazdego
# od razu na GitHubie (duzo gorzej niz wyciaganie go ze skompilowanego .exe).
# Sekret trafia do .exe wylacznie w momencie budowania (PyInstaller pakuje
# lokalny plik, niezaleznie od tego czy jest w git). Patrz README:
# "Wydawanie nowej wersji" po instrukcje odtworzenia tego pliku lokalnie.
from device_binding_secret import BINDINGS_TOKEN  # noqa: E402

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{BINDINGS_REPO}/contents/{BINDINGS_PATH}"
HTTP_TIMEOUT_S = 10
MAX_RETRIES = 5


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {BINDINGS_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def _fetch_bindings() -> tuple[dict, str]:
    """Zwraca (bindings, sha) - sha jest potrzebne do bezpiecznego zapisu
    (optymistyczne blokowanie: GitHub odrzuci PUT ze starym sha kodem 409,
    jesli ktos inny zapisal w miedzyczasie)."""
    resp = requests.get(API_URL, headers=_headers(), timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]


def _write_bindings(bindings: dict, sha: str) -> bool:
    """Zwraca True jesli zapis sie udal, False przy konflikcie 409 (ktos
    inny zapisal w miedzyczasie - trzeba pobrac na nowo i sprobowac ponownie)."""
    body = {
        "message": "Update device bindings",
        "content": base64.b64encode(json.dumps(bindings, indent=2).encode("utf-8")).decode("ascii"),
        "sha": sha,
    }
    resp = requests.put(API_URL, headers=_headers(), json=body, timeout=HTTP_TIMEOUT_S)
    if resp.status_code == 409:
        return False
    resp.raise_for_status()
    return True


def check_and_bind(discord_user_id: str, machine_id: str) -> tuple[bool, str]:
    """Probuje powiazac discord_user_id z machine_id. Jesli to konto jest
    juz powiazane z INNYM komputerem - odrzuca (twarda blokada). Jesli jest
    juz powiazane z TYM SAMYM komputerem - przepuszcza (nic sie nie zmienia).
    W przeciwnym razie zapisuje nowe powiazanie. Zwraca (dozwolone, komunikat)."""
    for _ in range(MAX_RETRIES):
        try:
            bindings, sha = _fetch_bindings()
        except requests.RequestException as exc:
            return False, f"Nie udalo sie polaczyc z lista urzadzen: {exc}"

        existing = bindings.get(discord_user_id)
        if existing is not None:
            if existing.get("machine_id") == machine_id:
                return True, "OK"
            return False, "To konto Discord jest juz przypisane do innego komputera."

        bindings[discord_user_id] = {
            "machine_id": machine_id,
            "bound_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            if _write_bindings(bindings, sha):
                return True, "OK"
        except requests.RequestException as exc:
            return False, f"Nie udalo sie zapisac przypisania urzadzenia: {exc}"
        # 409 - ktos inny zapisal w miedzyczasie, petla sprobuje ponownie od nowa

    return False, "Nie udalo sie zapisac przypisania urzadzenia (zbyt wiele rownoczesnych prob) - sprobuj ponownie."
