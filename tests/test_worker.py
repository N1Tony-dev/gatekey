"""
Testy logiki SequenceWorker - bez Qt event loopa, bez prawdziwego Win32.
input_sim jest w calosci podmieniony (monkeypatch), wiec te testy nigdy
nie wysylaja prawdziwych klawiszy ani nie dotykaja zadnego realnego okna
(w tym Robloxa) - patrz zasada bezpieczenstwa w planie implementacji.
"""

from __future__ import annotations

import threading
import time

import pytest

import worker as worker_mod
from worker import SequenceWorker


class RecordingSink:
    def __init__(self):
        self.statuses: list[tuple[str, str]] = []
        self.progresses: list[int] = []
        self.finished_value: bool | None = None

    def on_status(self, message: str, phase: str) -> None:
        self.statuses.append((message, phase))

    def on_progress(self, percent: int) -> None:
        self.progresses.append(percent)

    def on_finished(self, completed: bool) -> None:
        self.finished_value = completed


def make_worker(monkeypatch, key_log: list[str]):
    stop_event = threading.Event()
    w = SequenceWorker(stop_event)

    def fake_send(down: bool) -> None:
        key_log.append("down" if down else "up")

    monkeypatch.setattr(worker_mod.input_sim, "send_e_key", fake_send)
    monkeypatch.setattr(worker_mod.input_sim, "find_window_by_process", lambda exe: 12345)
    monkeypatch.setattr(worker_mod.input_sim, "is_window_foreground", lambda hwnd: True)
    monkeypatch.setattr(worker_mod.input_sim, "activate_window", lambda hwnd: True)
    return w, stop_event


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "reps,hold,expected_substr",
    [
        (0, 21, "powtorzen"),
        (-1, 21, "powtorzen"),
        (1.5, 21, "powtorzen"),
        (1, 0, "trzymania"),
        (1, -5, "trzymania"),
    ],
)
def test_validate_rejects_invalid(reps, hold, expected_substr):
    msg = worker_mod.validate(reps, hold)
    assert msg is not None
    assert expected_substr in msg


@pytest.mark.parametrize("reps,hold", [(1, 21), (5, 0.1), (999, 999.0)])
def test_validate_accepts_valid(reps, hold):
    assert worker_mod.validate(reps, hold) is None


# ---------------------------------------------------------------------------
# SequenceWorker.run() - przebieg sterowania (zdarzenia, nie prawdziwy czas)
# ---------------------------------------------------------------------------

def test_worker_completes_all_cycles(monkeypatch):
    key_log: list[str] = []
    w, stop_event = make_worker(monkeypatch, key_log)

    monkeypatch.setattr(worker_mod, "COUNTDOWN_MS", 20)
    monkeypatch.setattr(worker_mod, "GAP_MS", 20)
    monkeypatch.setattr(worker_mod, "GAP_JITTER_MS", 0)
    monkeypatch.setattr(worker_mod, "HOLD_JITTER_MS", 0)
    monkeypatch.setattr(worker_mod, "WAIT_STEP_S", 0.01)

    sink = RecordingSink()
    w.status_changed.connect(sink.on_status)
    w.progress_changed.connect(sink.on_progress)
    w.finished.connect(sink.on_finished)

    w.run(reps=2, hold_seconds=0.03)

    phases = [phase for _, phase in sink.statuses]
    assert phases == ["countdown", "holding", "gap", "holding", "gap", "done"]
    assert sink.finished_value is True
    assert sink.progresses[-1] == 100

    # klucz E: zawsze zaczyna sie od "down", konczy na "up", i kazdy cykl
    # ma dokladnie jedno zwolnienie (E nigdy nie zostaje "zawieszone")
    assert key_log[0] == "down"
    assert key_log[-1] == "up"
    assert key_log.count("up") == 2


def test_worker_stop_mid_hold_releases_key(qapp, monkeypatch):
    key_log: list[str] = []
    w, stop_event = make_worker(monkeypatch, key_log)
    monkeypatch.setattr(worker_mod, "COUNTDOWN_MS", 20)

    sink = RecordingSink()
    w.status_changed.connect(sink.on_status)
    w.finished.connect(sink.on_finished)

    t = threading.Thread(target=w.run, kwargs={"reps": 1, "hold_seconds": 2.0})
    t.start()
    time.sleep(0.3)  # na pewno w trakcie trzymania (countdown=20ms, hold=2000ms)
    stop_event.set()
    t.join(timeout=2)
    qapp.processEvents()  # dostarcz sygnaly zakolejkowane z tla watku

    assert not t.is_alive()
    assert sink.finished_value is False
    assert sink.statuses[-1][1] == "stopped"
    # E musi zostac zwolnione mimo przerwania w trakcie trzymania
    assert key_log[-1] == "up"


def test_worker_stop_during_countdown_never_presses_key(qapp, monkeypatch):
    key_log: list[str] = []
    w, stop_event = make_worker(monkeypatch, key_log)
    monkeypatch.setattr(worker_mod, "COUNTDOWN_MS", 2000)

    sink = RecordingSink()
    w.finished.connect(sink.on_finished)

    t = threading.Thread(target=w.run, kwargs={"reps": 1, "hold_seconds": 5.0})
    t.start()
    time.sleep(0.1)
    stop_event.set()
    t.join(timeout=2)
    qapp.processEvents()  # dostarcz sygnaly zakolejkowane z tla watku

    assert not t.is_alive()
    assert sink.finished_value is False
    assert key_log == []  # zatrzymane w odliczaniu - E nigdy nie zostalo wcisniete
