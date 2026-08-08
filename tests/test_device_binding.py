"""Testy logiki wiazania urzadzen - requests w calosci zamockowany, zero
prawdziwych wywolan do GitHub API / repo gatekey-devices."""

from __future__ import annotations

import base64
import json

import requests

import device_binding as db_mod


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _encode(bindings: dict) -> str:
    return base64.b64encode(json.dumps(bindings).encode("utf-8")).decode("ascii")


def test_check_and_bind_allows_new_user(monkeypatch):
    monkeypatch.setattr(
        db_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode({}), "sha": "sha1"}),
    )
    put_calls = []

    def fake_put(url, headers=None, json=None, timeout=None):
        put_calls.append(json)
        return FakeResponse(200)

    monkeypatch.setattr(db_mod.requests, "put", fake_put)

    allowed, message = db_mod.check_and_bind("user1", "machineA")
    assert allowed is True
    assert message == "OK"
    assert len(put_calls) == 1
    written = json.loads(base64.b64decode(put_calls[0]["content"]))
    assert written["user1"]["machine_id"] == "machineA"


def test_check_and_bind_allows_same_machine_reverify(monkeypatch):
    existing = {"user1": {"machine_id": "machineA", "bound_at": "2026-01-01T00:00:00Z"}}
    monkeypatch.setattr(
        db_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode(existing), "sha": "sha1"}),
    )
    monkeypatch.setattr(db_mod.requests, "put", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("nie powinno zapisywac")))

    allowed, message = db_mod.check_and_bind("user1", "machineA")
    assert allowed is True


def test_check_and_bind_rejects_different_machine(monkeypatch):
    existing = {"user1": {"machine_id": "machineA", "bound_at": "2026-01-01T00:00:00Z"}}
    monkeypatch.setattr(
        db_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode(existing), "sha": "sha1"}),
    )

    allowed, message = db_mod.check_and_bind("user1", "machineB")
    assert allowed is False
    assert "innego komputera" in message


def test_check_and_bind_retries_on_409_conflict(monkeypatch):
    call_count = {"n": 0}

    def fake_get(*a, **kw):
        call_count["n"] += 1
        return FakeResponse(200, {"content": _encode({}), "sha": f"sha{call_count['n']}"})

    put_attempts = []

    def fake_put(url, headers=None, json=None, timeout=None):
        put_attempts.append(json)
        if len(put_attempts) == 1:
            return FakeResponse(409)  # ktos inny zapisal w miedzyczasie
        return FakeResponse(200)

    monkeypatch.setattr(db_mod.requests, "get", fake_get)
    monkeypatch.setattr(db_mod.requests, "put", fake_put)

    allowed, message = db_mod.check_and_bind("user1", "machineA")
    assert allowed is True
    assert len(put_attempts) == 2  # pierwsza proba 409, druga sie udala
    assert call_count["n"] == 2  # fetch powtorzony po konflikcie


def test_check_and_bind_network_error_is_never_unhandled(monkeypatch):
    def raise_err(*a, **kw):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(db_mod.requests, "get", raise_err)

    allowed, message = db_mod.check_and_bind("user1", "machineA")
    assert allowed is False
    assert "urzadzen" in message
