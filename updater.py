"""
Automatyczna aktualizacja Gatekey z GitHub Releases. Dziala tylko w
spakowanej wersji (.exe) - w trybie deweloperskim (python main.py) nie ma
czego podmieniac, wiec caly ten modul jest wtedy po prostu pomijany
(patrz sys.frozen w main.py).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import requests

from version import __version__

GITHUB_OWNER = "N1Tony-dev"
GITHUB_REPO = "gatekey"
ASSET_NAME = "Gatekey.exe"
API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
HTTP_TIMEOUT_S = 10
DOWNLOAD_TIMEOUT_S = 60


def _parse_version(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_update() -> tuple[str, str] | None:
    """Zwraca (nowy_numer_wersji, download_url) jesli na GitHubie jest
    wydanie nowsze niz __version__. Zwraca None gdy nie ma nowszej wersji
    ALBO gdy sprawdzenie sie nie udalo (np. brak internetu) - w obu
    przypadkach aplikacja ma po prostu ruszyc normalnie dalej."""
    try:
        resp = requests.get(API_URL, timeout=HTTP_TIMEOUT_S)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None

    latest_tag = data.get("tag_name") or ""
    if not latest_tag or _parse_version(latest_tag) <= _parse_version(__version__):
        return None

    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if asset is None:
        return None

    return latest_tag, asset["browser_download_url"]


def download_update(url: str, progress_cb: Callable[[int], None] | None = None) -> Path:
    """Pobiera nowy .exe do pliku tymczasowego i zwraca jego sciezke."""
    dest = Path(tempfile.gettempdir()) / "Gatekey_update.exe"
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_S) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=262144):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(min(int(downloaded / total * 100), 100))
    return dest


def apply_update_and_relaunch(new_exe_path: Path) -> None:
    """Podmienia biezacy .exe na pobrana nowsza wersje i uruchamia ja
    ponownie. Konczy biezacy proces (sys.exit) - nie wraca do wywolujacego.

    Dziala przez male .bat w katalogu tymczasowym: czeka az biezacy proces
    (po PID) faktycznie zniknie z listy procesow, probuje podmienic plik
    (w petli - .exe moze byc przez chwile zablokowany tuz po zamknieciu),
    uruchamia nowa wersje, i usuwa sam siebie."""
    current_exe = Path(sys.executable)
    pid = os.getpid()
    updater_script = Path(tempfile.gettempdir()) / "gatekey_updater.bat"

    script = f"""@echo off
:waitproc
tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto waitproc
)
:trymove
move /Y "{new_exe_path}" "{current_exe}" >NUL 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto trymove
)
start "Gatekey" /B "{current_exe}"
timeout /t 1 /nobreak >NUL
del "%~f0"
"""
    updater_script.write_text(script, encoding="utf-8")

    # Tylko CREATE_NO_WINDOW (bez DETACHED_PROCESS) - laczenie obu jest
    # znanym zrodlem problemow na Windows: DETACHED_PROCESS odbiera procesowi
    # konsole calkowicie, a polecenia w .bat (tasklist/find/move/timeout)
    # potrzebuja niewidocznej konsoli, nie jej braku.
    subprocess.Popen(
        ["cmd", "/c", str(updater_script)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    sys.exit(0)
