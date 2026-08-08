"""
Testy bramki Discord. Zero prawdziwych wywolan do API Discorda - requests
jest w calosci podmieniony (monkeypatch) wszedzie oprocz testow lokalnego
serwera callback, ktore uzywaja prawdziwego gniazda na localhost (bez
zadnego ruchu na zewnatrz) - to jedyny "prawdziwy" ruch sieciowy w tych
testach i nigdy nie dotyka Discorda.
"""

from __future__ import annotations

import threading
import time

import pytest
import requests

import discord_gate as gate_mod
from config import Config


def make_config(**overrides) -> Config:
    defaults = dict(
        client_id="client123",
        client_secret="secret123",
        bot_token="bottoken123",
        guild_id="guild123",
        required_role_id="role123",
        redirect_port=47699,
    )
    defaults.update(overrides)
    return Config(**defaults)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------

def test_build_authorize_url_contains_required_params():
    url = gate_mod.build_authorize_url("cid", "http://localhost:47624/callback", "state123")
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "scope=identify" in url
    assert "state=state123" in url
    assert "localhost%3A47624%2Fcallback" in url or "localhost:47624/callback" in url


# ---------------------------------------------------------------------------
# run_local_callback_server - prawdziwe gniazdo na localhost, zero ruchu
# na zewnatrz (nigdy nie dotyka Discorda)
# ---------------------------------------------------------------------------

def _run_server_in_thread(port, timeout_s, state, result_holder):
    code, error = gate_mod.run_local_callback_server(port, timeout_s, state)
    result_holder["code"] = code
    result_holder["error"] = error


def test_callback_server_receives_code():
    port = 47701
    result = {}
    t = threading.Thread(target=_run_server_in_thread, args=(port, 5.0, "expected-state", result))
    t.start()
    time.sleep(0.3)
    resp = requests.get(f"http://localhost:{port}/callback", params={"code": "abc123", "state": "expected-state"})
    assert resp.status_code == 200
    t.join(timeout=5)
    assert result["code"] == "abc123"
    assert result["error"] is None


def test_callback_server_detects_state_mismatch():
    port = 47702
    result = {}
    t = threading.Thread(target=_run_server_in_thread, args=(port, 5.0, "expected-state", result))
    t.start()
    time.sleep(0.3)
    requests.get(f"http://localhost:{port}/callback", params={"code": "abc123", "state": "wrong-state"})
    t.join(timeout=5)
    assert result["code"] is None
    assert result["error"] == "state_mismatch"


def test_callback_server_reports_discord_error():
    port = 47703
    result = {}
    t = threading.Thread(target=_run_server_in_thread, args=(port, 5.0, "expected-state", result))
    t.start()
    time.sleep(0.3)
    requests.get(f"http://localhost:{port}/callback", params={"error": "access_denied", "state": "expected-state"})
    t.join(timeout=5)
    assert result["code"] is None
    assert result["error"] == "access_denied"


def test_callback_server_times_out_without_request():
    code, error = gate_mod.run_local_callback_server(47704, 0.3, "expected-state")
    assert code is None
    assert error is None


# ---------------------------------------------------------------------------
# exchange_code / fetch_current_user_id / member_has_role (requests mocked)
# ---------------------------------------------------------------------------

def test_exchange_code_returns_access_token(monkeypatch):
    monkeypatch.setattr(
        gate_mod.requests, "post", lambda *a, **kw: FakeResponse(200, {"access_token": "tok-xyz"})
    )
    token = gate_mod.exchange_code("cid", "secret", "code123", "http://localhost:47624/callback")
    assert token == "tok-xyz"


def test_fetch_current_user_id(monkeypatch):
    monkeypatch.setattr(gate_mod.requests, "get", lambda *a, **kw: FakeResponse(200, {"id": "999888777"}))
    assert gate_mod.fetch_current_user_id("tok-xyz") == "999888777"


def test_member_has_role_true(monkeypatch):
    monkeypatch.setattr(
        gate_mod.requests, "get", lambda *a, **kw: FakeResponse(200, {"roles": ["role123", "role456"]})
    )
    assert gate_mod.member_has_role("bot", "guild", "user", "role123") is True


def test_member_has_role_false_when_missing(monkeypatch):
    monkeypatch.setattr(gate_mod.requests, "get", lambda *a, **kw: FakeResponse(200, {"roles": ["role456"]}))
    assert gate_mod.member_has_role("bot", "guild", "user", "role123") is False


def test_member_has_role_false_when_not_a_member(monkeypatch):
    monkeypatch.setattr(gate_mod.requests, "get", lambda *a, **kw: FakeResponse(404))
    assert gate_mod.member_has_role("bot", "guild", "user", "role123") is False


# ---------------------------------------------------------------------------
# GateVerifier.run() - orkiestracja z podmienionymi funkcjami niskiego
# poziomu (bez jakiegokolwiek prawdziwego ruchu sieciowego)
# ---------------------------------------------------------------------------

class Sink:
    def __init__(self):
        self.statuses: list[str] = []
        self.result: tuple[bool, str] | None = None

    def on_status(self, msg):
        self.statuses.append(msg)

    def on_finished(self, unlocked, msg):
        self.result = (unlocked, msg)


def make_verifier(
    monkeypatch, *, code="code123", error=None, has_role=True, exc=None,
    bind_allowed=True, bind_message="OK", banned=False, ban_message="",
):
    monkeypatch.setattr(gate_mod, "webbrowser", type("_W", (), {"open": staticmethod(lambda url: None)}))
    monkeypatch.setattr(gate_mod, "run_local_callback_server", lambda port, timeout_s, state: (code, error))
    monkeypatch.setattr(gate_mod, "exchange_code", lambda *a, **kw: "access-token")
    monkeypatch.setattr(gate_mod, "fetch_current_user_id", lambda token: "user-id")
    monkeypatch.setattr(gate_mod, "check_ban", lambda user_id: (banned, ban_message))

    def fake_member_has_role(*a, **kw):
        if exc is not None:
            raise exc
        return has_role

    monkeypatch.setattr(gate_mod, "member_has_role", fake_member_has_role)

    # save_verified_session i check_and_bind pisza do prawdziwych zasobow
    # (plik .session obok .env, wspolne repo GitHub gatekey-devices) - w
    # testach NIGDY nie chcemy dotykac tego prawdziwego stanu, wiec obie
    # funkcje podmieniamy na nagrywajace no-opy (w miejscu, gdzie
    # discord_gate.py je zaimportowal - patrz "from session/device_binding import ...").
    saved_calls = []
    monkeypatch.setattr(gate_mod, "save_verified_session", lambda user_id: saved_calls.append(user_id))
    monkeypatch.setattr(gate_mod, "machine_id", lambda: "test-machine-id")
    bind_calls = []

    def fake_check_and_bind(user_id, mid):
        bind_calls.append((user_id, mid))
        return bind_allowed, bind_message

    monkeypatch.setattr(gate_mod, "check_and_bind", fake_check_and_bind)

    verifier = gate_mod.GateVerifier(make_config())
    sink = Sink()
    verifier.status_changed.connect(sink.on_status)
    verifier.finished.connect(sink.on_finished)
    return verifier, sink, saved_calls


def test_gate_verifier_success(monkeypatch):
    verifier, sink, saved_calls = make_verifier(monkeypatch, has_role=True)
    verifier.run()
    assert sink.result == (True, "Zweryfikowano - dostep odblokowany.")
    assert saved_calls == ["user-id"]  # sesja zapisana dokladnie raz, dla wlasciwego usera


def test_gate_verifier_banned_account_rejected_before_role_check(monkeypatch):
    verifier, sink, saved_calls = make_verifier(
        monkeypatch, has_role=True, banned=True, ban_message="Zbanowano do 2026-01-01 00:00 UTC.",
    )
    verifier.run()
    assert sink.result == (False, "Zbanowano do 2026-01-01 00:00 UTC.")
    assert saved_calls == []


def test_gate_verifier_device_already_bound_elsewhere(monkeypatch):
    verifier, sink, saved_calls = make_verifier(
        monkeypatch, has_role=True, bind_allowed=False,
        bind_message="To konto Discord jest juz przypisane do innego komputera.",
    )
    verifier.run()
    assert sink.result == (False, "To konto Discord jest juz przypisane do innego komputera.")
    assert saved_calls == []  # brak zgody na przypisanie - sesja lokalna NIE moze zostac zapisana


def test_gate_verifier_missing_role(monkeypatch):
    verifier, sink, saved_calls = make_verifier(monkeypatch, has_role=False)
    verifier.run()
    assert sink.result[0] is False
    assert "roli" in sink.result[1]
    assert saved_calls == []  # brak roli - sesja NIE moze zostac zapisana


def test_gate_verifier_timeout(monkeypatch):
    verifier, sink, _ = make_verifier(monkeypatch, code=None, error=None)
    verifier.run()
    assert sink.result[0] is False
    assert "czas" in sink.result[1]


def test_gate_verifier_discord_denied(monkeypatch):
    verifier, sink, _ = make_verifier(monkeypatch, code=None, error="access_denied")
    verifier.run()
    assert sink.result == (False, "Odmowiono dostepu w Discordzie.")


def test_gate_verifier_state_mismatch(monkeypatch):
    verifier, sink, _ = make_verifier(monkeypatch, code=None, error="state_mismatch")
    verifier.run()
    assert sink.result[0] is False
    assert "state" in sink.result[1] or "bezpieczenstwa" in sink.result[1]


def test_gate_verifier_network_error_is_never_unhandled(monkeypatch):
    verifier, sink, _ = make_verifier(monkeypatch, exc=requests.ConnectionError("boom"))
    verifier.run()  # nie powinno rzucic wyjatku
    assert sink.result[0] is False
    assert "Blad polaczenia" in sink.result[1]
