"""Testy sprawdzania bana - requests w calosci zamockowany, zero
prawdziwych wywolan do GitHub API / repo gatekey-devices."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import requests

import bans as bans_mod


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _encode(data: dict) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")


def test_check_ban_none_when_file_missing(monkeypatch):
    monkeypatch.setattr(bans_mod.requests, "get", lambda *a, **kw: FakeResponse(404))
    banned, message = bans_mod.check_ban("user1")
    assert banned is False
    assert message is None


def test_check_ban_none_when_user_not_listed(monkeypatch):
    monkeypatch.setattr(
        bans_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode({}), "sha": "sha1"}),
    )
    banned, message = bans_mod.check_ban("user1")
    assert banned is False


def test_check_ban_true_when_active(monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    data = {"user1": {"banned_until": future, "reason": "spam"}}
    monkeypatch.setattr(
        bans_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode(data), "sha": "sha1"}),
    )
    banned, message = bans_mod.check_ban("user1")
    assert banned is True
    assert "spam" in message


def test_check_ban_false_when_expired(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    data = {"user1": {"banned_until": past}}
    monkeypatch.setattr(
        bans_mod.requests, "get",
        lambda *a, **kw: FakeResponse(200, {"content": _encode(data), "sha": "sha1"}),
    )
    banned, message = bans_mod.check_ban("user1")
    assert banned is False


def test_check_ban_false_on_network_error(monkeypatch):
    def raise_err(*a, **kw):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(bans_mod.requests, "get", raise_err)
    banned, message = bans_mod.check_ban("user1")
    assert banned is False
