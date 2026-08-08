"""
Logika sekwencji trzymania E: odliczanie -> (aktywuj Roblox -> trzymaj E ->
przerwa) x reps. Cala komunikacja z Win32 idzie przez input_sim (nigdy
bezposrednio), dzieki czemu ten modul da sie testowac bez prawdziwego
wysylania klawiszy - patrz tests/test_worker.py.
"""

from __future__ import annotations

import random
import threading
import time

from PySide6.QtCore import QObject, Signal

import input_sim

ROBLOX_EXE = "RobloxPlayerBeta.exe"

COUNTDOWN_MS = 3000
GAP_MS = 1000
GAP_JITTER_MS = 100
HOLD_JITTER_MS = 150
WAIT_STEP_S = 0.1
HOLD_STEP_S = 0.015
REPEAT_FIRST_MS = 500
REPEAT_INTERVAL_MS = 33
ROBLOX_POLL_S = 0.2
ROBLOX_ACTIVATE_TIMEOUT_S = 2.0


def validate(reps, hold_seconds) -> str | None:
    """Zwraca komunikat bledu albo None jesli wartosci sa poprawne."""
    try:
        reps_ok = int(reps) == float(reps) and int(reps) > 0
    except (TypeError, ValueError):
        reps_ok = False
    if not reps_ok:
        return "Podaj dodatnia liczbe calkowita powtorzen."

    try:
        hold_ok = float(hold_seconds) > 0
    except (TypeError, ValueError):
        hold_ok = False
    if not hold_ok:
        return "Podaj dodatni czas trzymania w sekundach."

    return None


class SequenceWorker(QObject):
    # (wiadomosc, faza) - faza steruje kolorem kropki statusu i paska postepu
    status_changed = Signal(str, str)
    progress_changed = Signal(int)
    finished = Signal(bool)  # True = zakonczono wszystkie cykle, False = zatrzymano

    def __init__(self, stop_event: threading.Event):
        super().__init__()
        self._stop_event = stop_event
        self._e_down = False

    def run(self, reps: int, hold_seconds: float) -> None:
        self._stop_event.clear()
        self._e_down = False
        hold_ms = round(hold_seconds * 1000)

        try:
            self.status_changed.emit("Start za 3s... kliknij w okno Robloxa!", "countdown")
            if not self._wait_or_stop(COUNTDOWN_MS):
                self._finish(False, reps)
                return

            completed_all = False
            for cycle in range(1, reps + 1):
                if self._stop_event.is_set():
                    break
                if not self._ensure_roblox_active():
                    break

                self.status_changed.emit(f"Cykl {cycle}/{reps} - trzymanie E", "holding")
                hold_time = max(hold_ms + random.randint(-HOLD_JITTER_MS, HOLD_JITTER_MS), 0)
                if not self._hold_e(hold_time):
                    break
                self._press_e(False)

                if self._stop_event.is_set():
                    break
                self.status_changed.emit(f"Cykl {cycle}/{reps} - przerwa", "gap")
                gap_time = max(GAP_MS + random.randint(-GAP_JITTER_MS, GAP_JITTER_MS), 0)
                if not self._wait_or_stop(gap_time):
                    break
            else:
                completed_all = True

            self._finish(completed_all, reps)
        finally:
            self._press_e(False)

    # -- pomocnicze -------------------------------------------------------

    def _finish(self, completed: bool, reps: int) -> None:
        self._press_e(False)
        if completed:
            self.progress_changed.emit(100)
            self.status_changed.emit(f"Zakonczono ({reps} cykli).", "done")
        else:
            self.status_changed.emit("Zatrzymano.", "stopped")
        self.finished.emit(completed)

    def _press_e(self, down: bool) -> None:
        if down and not self._e_down:
            input_sim.send_e_key(True)
            self._e_down = True
        elif not down and self._e_down:
            input_sim.send_e_key(False)
            self._e_down = False

    def _hold_e(self, duration_ms: int) -> bool:
        """Trzyma E przez duration_ms, dosylajac powtorzone sygnaly 'down'
        (jak auto-repeat prawdziwej klawiatury: pierwszy po 500ms, potem co
        33ms) - niektore gry licza trzymanie po powtarzanych KEYDOWN, nie
        tylko po stanie klawisza. Pulsy repeat NIE ida przez _press_e -
        strażnik stanu w _press_e uznalby E juz za wcisniete i pominal
        kazdy puls, co calkowicie zniweczyloby ten mechanizm."""
        self._press_e(True)
        start = time.monotonic()
        next_repeat_ms = REPEAT_FIRST_MS

        while True:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms >= duration_ms:
                break
            if self._stop_event.is_set():
                return False

            percent = 100 if duration_ms <= 0 else min(elapsed_ms / duration_ms * 100, 100)
            self.progress_changed.emit(round(percent))

            if elapsed_ms >= next_repeat_ms:
                input_sim.send_e_key(True)
                next_repeat_ms += REPEAT_INTERVAL_MS

            time.sleep(HOLD_STEP_S)

        self.progress_changed.emit(100)
        return True

    def _wait_or_stop(self, total_ms: int) -> bool:
        if total_ms <= 0:
            return True
        start = time.monotonic()
        while True:
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms >= total_ms:
                self.progress_changed.emit(100)
                return True
            if self._stop_event.is_set():
                return False
            self.progress_changed.emit(round(min(elapsed_ms / total_ms * 100, 100)))
            time.sleep(WAIT_STEP_S)

    def _ensure_roblox_active(self) -> bool:
        """Odpowiednik EnsureRobloxActive z AHK: sprawdza czy Roblox jest
        aktywnym oknem, probuje go aktywowac, a jesli sie nie da - czeka,
        informujac uzytkownika, az sam przelaczy sie na Roblox albo user
        przerwie sekwencje."""
        hwnd = input_sim.find_window_by_process(ROBLOX_EXE)
        if hwnd and input_sim.is_window_foreground(hwnd):
            return True

        if hwnd:
            input_sim.activate_window(hwnd)
            deadline = time.monotonic() + ROBLOX_ACTIVATE_TIMEOUT_S
            while time.monotonic() < deadline:
                if input_sim.is_window_foreground(hwnd):
                    return True
                if self._stop_event.is_set():
                    return False
                time.sleep(0.05)

        waiting_emitted = False
        while True:
            hwnd = input_sim.find_window_by_process(ROBLOX_EXE)
            if hwnd and input_sim.is_window_foreground(hwnd):
                return True
            if self._stop_event.is_set():
                return False
            if not waiting_emitted:
                self.status_changed.emit(
                    "Roblox nie jest aktywnym oknem! Kliknij w Roblox - czekam...", "waiting"
                )
                waiting_emitted = True
            time.sleep(ROBLOX_POLL_S)
