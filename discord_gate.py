"""
Bramka dostepu Gatekey: logowanie przez Discord OAuth2 (lokalny serwer
callback) + sprawdzenie roli na serwerze przez token bota.

GET /guilds/{guild.id}/members/{user.id} (pojedynczy czlonek) NIE wymaga
uprzywilejowanego Server Members Intent - wymaga go tylko masowe listowanie
czlonkow - wiec bota wystarczy dodac do serwera, bez wlaczania intencji.
"""

from __future__ import annotations

import http.server
import secrets
import time
import urllib.parse
import webbrowser

import requests
from PySide6.QtCore import QObject, Signal

from config import Config

API_BASE = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
TOKEN_URL = f"{API_BASE}/oauth2/token"

CALLBACK_TIMEOUT_S = 120
HTTP_TIMEOUT_S = 10

_CALLBACK_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Gatekey</title>
<style>body{background:#18181B;color:#F2F2F2;font-family:Segoe UI,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
div{text-align:center}</style></head>
<body><div><h2>Gatekey</h2><p>Mozesz zamknac ta karte i wrocic do aplikacji.</p></div></body></html>"""


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def run_local_callback_server(port: int, timeout_s: float, expected_state: str) -> tuple[str | None, str | None]:
    """Uruchamia jednorazowy lokalny serwer HTTP na callback OAuth2.
    Zwraca (code, error) - error moze byc "state_mismatch", tym co Discord
    zwrocil w parametrze error (np. "access_denied"), albo None."""

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            state = params.get("state", [None])[0]
            if state != expected_state:
                self.server.auth_error = "state_mismatch"  # type: ignore[attr-defined]
            else:
                self.server.auth_code = params.get("code", [None])[0]  # type: ignore[attr-defined]
                self.server.auth_error = params.get("error", [None])[0]  # type: ignore[attr-defined]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_CALLBACK_HTML.encode("utf-8"))

        def log_message(self, format: str, *args) -> None:  # noqa: A002 - sygnatura BaseHTTPRequestHandler
            pass

    server = http.server.HTTPServer(("localhost", port), _CallbackHandler)
    server.auth_code = None  # type: ignore[attr-defined]
    server.auth_error = None  # type: ignore[attr-defined]
    server.timeout = 1.0

    deadline = time.monotonic() + timeout_s
    while server.auth_code is None and server.auth_error is None and time.monotonic() < deadline:  # type: ignore[attr-defined]
        server.handle_request()
    server.server_close()

    return server.auth_code, server.auth_error  # type: ignore[attr-defined]


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> str:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_current_user_id(access_token: str) -> str:
    resp = requests.get(
        f"{API_BASE}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=HTTP_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def member_has_role(bot_token: str, guild_id: str, user_id: str, role_id: str) -> bool:
    resp = requests.get(
        f"{API_BASE}/guilds/{guild_id}/members/{user_id}",
        headers={"Authorization": f"Bot {bot_token}"},
        timeout=HTTP_TIMEOUT_S,
    )
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return role_id in resp.json().get("roles", [])


class GateVerifier(QObject):
    status_changed = Signal(str)
    finished = Signal(bool, str)  # (odblokowano, wiadomosc)

    def __init__(self, cfg: Config):
        super().__init__()
        self._cfg = cfg

    def run(self) -> None:
        cfg = self._cfg
        try:
            state = secrets.token_urlsafe(16)
            url = build_authorize_url(cfg.client_id, cfg.redirect_uri, state)

            self.status_changed.emit("Otwieram przegladarke...")
            webbrowser.open(url)

            self.status_changed.emit("Czekam na autoryzacje w przegladarce...")
            code, error = run_local_callback_server(cfg.redirect_port, CALLBACK_TIMEOUT_S, state)

            if error == "state_mismatch":
                self.finished.emit(False, "Blad bezpieczenstwa (state) - sprobuj ponownie.")
                return
            if error:
                self.finished.emit(False, "Odmowiono dostepu w Discordzie.")
                return
            if not code:
                self.finished.emit(False, "Przekroczono czas oczekiwania na autoryzacje.")
                return

            self.status_changed.emit("Wymieniam kod na token...")
            access_token = exchange_code(cfg.client_id, cfg.client_secret, code, cfg.redirect_uri)

            self.status_changed.emit("Pobieram tozsamosc Discord...")
            user_id = fetch_current_user_id(access_token)

            self.status_changed.emit("Sprawdzam role na serwerze...")
            if member_has_role(cfg.bot_token, cfg.guild_id, user_id, cfg.required_role_id):
                self.finished.emit(True, "Zweryfikowano - dostep odblokowany.")
            else:
                self.finished.emit(False, "Brak wymaganej roli na serwerze.")
        except requests.RequestException as exc:
            self.finished.emit(False, f"Blad polaczenia z Discord: {exc}")
        except Exception as exc:  # ostatnia linia obrony - watek nigdy nie moze zabic sie niezlapanym wyjatkiem
            self.finished.emit(False, f"Nieoczekiwany blad: {exc}")
