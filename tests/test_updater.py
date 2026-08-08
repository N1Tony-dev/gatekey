"""Testy logiki sprawdzania aktualizacji - requests w calosci zamockowany,
zero prawdziwych wywolan do GitHub API. apply_update_and_relaunch (ktore
konczy proces i podmienia plik .exe) celowo NIE jest tu testowane
automatycznie - to nieodwracalna operacja na prawdziwym systemie plikow,
weryfikowana recznie (patrz plan wydania w README)."""

from __future__ import annotations

import updater


def test_parse_version_basic():
    assert updater._parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_strips_v_prefix():
    assert updater._parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_ordering():
    assert updater._parse_version("1.10.0") > updater._parse_version("1.9.0")
    assert updater._parse_version("2.0.0") > updater._parse_version("1.99.99")


def test_check_for_update_none_when_same_version(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.0.0")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v1.0.0", "assets": [{"name": "Gatekey.exe", "browser_download_url": "x"}]}

    monkeypatch.setattr(updater.requests, "get", lambda *a, **kw: FakeResponse())
    assert updater.check_for_update() is None


def test_check_for_update_returns_newer_version(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.0.0")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "tag_name": "v1.1.0",
                "assets": [{"name": "Gatekey.exe", "browser_download_url": "https://example/Gatekey.exe"}],
            }

    monkeypatch.setattr(updater.requests, "get", lambda *a, **kw: FakeResponse())
    result = updater.check_for_update()
    assert result == ("v1.1.0", "https://example/Gatekey.exe")


def test_check_for_update_none_when_asset_missing(monkeypatch):
    monkeypatch.setattr(updater, "__version__", "1.0.0")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": "v1.1.0", "assets": [{"name": "other.exe", "browser_download_url": "x"}]}

    monkeypatch.setattr(updater.requests, "get", lambda *a, **kw: FakeResponse())
    assert updater.check_for_update() is None


def test_check_for_update_none_on_network_error(monkeypatch):
    import requests

    def raise_err(*a, **kw):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(updater.requests, "get", raise_err)
    assert updater.check_for_update() is None
