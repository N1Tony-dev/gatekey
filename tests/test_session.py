"""Testy cache'a zweryfikowanej sesji - operuja na tymczasowym pliku
(monkeypatch SESSION_FILE), nigdy na prawdziwym pliku .session projektu."""

from __future__ import annotations

import session as session_mod


def test_has_valid_session_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSION_FILE", tmp_path / ".session")
    assert session_mod.has_valid_session() is False


def test_save_then_has_valid_session_true_on_same_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSION_FILE", tmp_path / ".session")
    session_mod.save_verified_session("111222333")
    assert session_mod.has_valid_session() is True


def test_has_valid_session_false_on_machine_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSION_FILE", tmp_path / ".session")
    session_mod.save_verified_session("111222333")
    monkeypatch.setattr(session_mod, "_machine_id", lambda: "different-machine")
    assert session_mod.has_valid_session() is False


def test_has_valid_session_false_on_corrupt_file(tmp_path, monkeypatch):
    session_file = tmp_path / ".session"
    session_file.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(session_mod, "SESSION_FILE", session_file)
    assert session_mod.has_valid_session() is False


def test_clear_session_removes_file(tmp_path, monkeypatch):
    session_file = tmp_path / ".session"
    monkeypatch.setattr(session_mod, "SESSION_FILE", session_file)
    session_mod.save_verified_session("111222333")
    assert session_file.exists()
    session_mod.clear_session()
    assert not session_file.exists()


def test_clear_session_noop_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSION_FILE", tmp_path / ".session")
    session_mod.clear_session()  # nie powinno rzucic wyjatku
