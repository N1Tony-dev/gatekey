"""
Gatekey - GUI (PySide6).

Ekran bramki (GatePage): trzeba polaczyc konto Discord i miec wymagana
role na serwerze, zeby odblokowac wlasciwe narzedzie.

Ekran sterowania (ControlPage, po odblokowaniu): "Roblox Auto E" - trzyma
klawisz E N razy z przerwami (Start/Stop albo F5/Esc). Cala logika
sekwencji zyje w worker.SequenceWorker, uruchamianym w osobnym QThread,
zeby okno nigdy nie zamarzalo w trakcie trzymania/oczekiwania.
"""

from __future__ import annotations

import ctypes.wintypes as wintypes
import sys
import threading

from PySide6.QtCore import QAbstractNativeEventFilter, QThread, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import requests

import input_sim
import session
import updater
import worker as worker_mod
from config import Config, ConfigError, load_config
from discord_gate import GateVerifier
from version import __version__
from worker import SequenceWorker

WINDOW_W, WINDOW_H = 720, 420
LEFT_COL_W = 280
RIGHT_COL_W = 320

QSS = """
QWidget#MainWindow {
    background: #18181B;
}
QLabel#badge {
    background: #5865F2;
    border-radius: 14px;
    color: #FFFFFF;
    font-size: 20px;
    font-weight: 700;
}
QLabel#titleLabel {
    color: #F2F2F2;
    font-size: 15px;
    font-weight: 700;
}
QLabel#subtitleLabel {
    color: #9A9A9F;
    font-size: 9pt;
}
QFrame#divider {
    background: #2D2D33;
    border: none;
}
QFrame#vDivider {
    background: #2D2D33;
    border: none;
}
QLabel#sectionLabel {
    color: #6E6E73;
    font-size: 8pt;
    font-weight: 700;
}
QFrame#card {
    background: #212126;
    border-radius: 12px;
}
QLabel#fieldLabel {
    color: #9A9A9F;
    font-size: 9pt;
}
QSpinBox#repsSpin, QDoubleSpinBox#holdSpin {
    background: #2A2A31;
    color: #F2F2F2;
    border: 1px solid #33333A;
    border-radius: 6px;
    padding: 4px;
    font-size: 11pt;
}
QSpinBox#repsSpin::up-button, QDoubleSpinBox#holdSpin::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    background: #33333A;
    border-top-right-radius: 6px;
}
QSpinBox#repsSpin::down-button, QDoubleSpinBox#holdSpin::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    background: #33333A;
    border-bottom-right-radius: 6px;
}
QPushButton#startButton, QPushButton#connectButton {
    background: #5865F2;
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    font-size: 11pt;
    font-weight: 700;
}
QPushButton#startButton:hover, QPushButton#connectButton:hover {
    background: #6C76F5;
}
QPushButton#startButton:disabled, QPushButton#connectButton:disabled {
    background: #3A3D6E;
    color: #B8BAD8;
}
QPushButton#stopButton {
    background: #2A2A31;
    color: #9A9A9F;
    border: none;
    border-radius: 10px;
    font-size: 11pt;
    font-weight: 700;
}
QPushButton#stopButton:hover {
    background: #35353D;
}
QProgressBar#progressBar {
    background: #232328;
    border: none;
    border-radius: 4px;
}
QProgressBar#progressBar::chunk {
    background: #5865F2;
    border-radius: 4px;
}
QProgressBar#progressBar[phase="holding"]::chunk { background: #3DDC84; }
QProgressBar#progressBar[phase="gap"]::chunk { background: #F5A623; }
QProgressBar#progressBar[phase="stopped"]::chunk { background: #E74C3C; }
QProgressBar#progressBar[phase="done"]::chunk { background: #3DDC84; }
QProgressBar#progressBar[phase="waiting"]::chunk { background: #E74C3C; }
QLabel#statusDot {
    background: #6E6E73;
    border-radius: 5px;
}
QLabel#statusDot[phase="countdown"] { background: #5865F2; }
QLabel#statusDot[phase="holding"] { background: #3DDC84; }
QLabel#statusDot[phase="gap"] { background: #F5A623; }
QLabel#statusDot[phase="waiting"] { background: #E74C3C; }
QLabel#statusDot[phase="stopped"] { background: #E74C3C; }
QLabel#statusDot[phase="done"] { background: #3DDC84; }
QLabel#statusLabel {
    color: #9A9A9F;
    font-size: 9pt;
}
QLabel#versionLabel {
    color: #4A4A50;
    font-size: 8pt;
}
"""

# Faza -> czy tekst statusu ma byc pogrubiony (mirror AHK SetStatus: tylko
# waga fontu i kolor kropki zmienia sie per faza, kolor tekstu jest stale dim).
PHASE_BOLD = {
    "idle": False,
    "countdown": True,
    "waiting": True,
    "holding": True,
    "gap": False,
    "stopped": True,
    "done": True,
}


def _set_phase(widgets, phase: str) -> None:
    for w in widgets:
        w.setProperty("phase", phase)
        w.style().unpolish(w)
        w.style().polish(w)


def _make_badge(letter: str) -> QLabel:
    badge = QLabel(letter)
    badge.setObjectName("badge")
    badge.setFixedSize(48, 48)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
    return badge


def _make_status_row() -> tuple[QHBoxLayout, QLabel, QLabel]:
    row = QHBoxLayout()
    row.setSpacing(8)
    dot = QLabel()
    dot.setObjectName("statusDot")
    dot.setFixedSize(10, 10)
    label = QLabel("Gotowy.")
    label.setObjectName("statusLabel")
    label.setWordWrap(True)
    row.addWidget(dot)
    row.addWidget(label, 1)
    return row, dot, label


class HotkeyEventFilter(QAbstractNativeEventFilter):
    """Nasluchuje WM_HOTKEY (zarejestrowany przez input_sim.register_global_hotkey
    - tylko na czas trwania sekwencji, patrz ControlPage) i od razu ustawia
    stop_event - bez posrednictwa Qt signal/slot, bo worker blokuje wlasna
    petle zdarzen na czas trwania sekwencji (patrz worker.py). Pyta MainWindow
    o aktualny stop_event zamiast trzymac wlasny, bo ControlPage (i jej
    stop_event) powstaje dopiero po odblokowaniu bramki Discord."""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self._window = window

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == input_sim.WM_HOTKEY:
                stop_event = self._window.active_stop_event
                if stop_event is not None:
                    stop_event.set()
        return False, 0


class GatePage(QWidget):
    """Ekran startowy: trzeba polaczyc konto Discord i miec wymagana role
    na serwerze, zeby przejsc dalej."""

    unlocked = Signal()

    def __init__(self, cfg: Config | None, cfg_error: ConfigError | None):
        super().__init__()
        self._cfg = cfg
        self._cfg_error = cfg_error
        self._thread: QThread | None = None
        self._verifier: GateVerifier | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addStretch(1)

        center = QVBoxLayout()
        center.setSpacing(0)
        center.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        badge = _make_badge("G")
        center.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)

        center.addSpacing(16)
        title = QLabel("Gatekey")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        center.addWidget(title)

        center.addSpacing(4)
        subtitle = QLabel("Polacz konto Discord, aby odblokowac")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(subtitle)

        center.addSpacing(26)
        self.connect_button = QPushButton("Polacz z Discord")
        self.connect_button.setObjectName("connectButton")
        self.connect_button.setFixedSize(220, 44)
        self.connect_button.setCursor(Qt.CursorShape.PointingHandCursor)
        center.addWidget(self.connect_button, 0, Qt.AlignmentFlag.AlignHCenter)

        center.addSpacing(18)
        status_row, self.status_dot, self.status_label = _make_status_row()
        status_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.status_label.setMaximumWidth(380)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addLayout(status_row)

        root.addLayout(center)
        root.addStretch(1)

        self.connect_button.clicked.connect(self._on_connect_clicked)
        _set_phase([self.status_dot], "idle")

        if self._cfg_error is not None:
            self.connect_button.setEnabled(False)
            self._set_status(f"Brak konfiguracji: {', '.join(self._cfg_error.missing_keys)}", "stopped")

    def _set_status(self, message: str, phase: str) -> None:
        self.status_label.setText(message)
        font = self.status_label.font()
        font.setBold(PHASE_BOLD.get(phase, False))
        self.status_label.setFont(font)
        _set_phase([self.status_dot], phase)

    def _on_connect_clicked(self) -> None:
        if self._cfg is None:
            return
        self.connect_button.setEnabled(False)
        self._set_status("Laczenie z Discord...", "countdown")

        self._thread = QThread(self)
        self._verifier = GateVerifier(self._cfg)
        self._verifier.moveToThread(self._thread)
        self._thread.started.connect(self._verifier.run)
        self._verifier.status_changed.connect(lambda msg: self._set_status(msg, "countdown"))
        self._verifier.finished.connect(self._on_verification_finished)
        self._thread.start()

    def _on_verification_finished(self, unlocked: bool, message: str) -> None:
        self._thread.quit()
        self._thread.wait(2000)
        self._thread = None
        self._verifier = None

        if unlocked:
            self._set_status(message, "done")
            self.unlocked.emit()
        else:
            self._set_status(message, "stopped")
            self.connect_button.setEnabled(True)


class ControlPage(QWidget):
    """Narzedzie 'Roblox Auto E' - identyczna logika co przed Gatekey,
    tylko przelozona na uklad dwukolumnowy (poziome okno)."""

    _start_requested = Signal(int, float)

    def __init__(self):
        super().__init__()
        self._running = False
        self._stop_event = threading.Event()
        self._build_ui()
        self._build_thread()
        _set_phase([self.progress_bar, self.status_dot], "idle")

    # -- budowa UI ----------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(28)

        # ---- lewa kolumna: naglowek + ustawienia ----
        left = QVBoxLayout()
        left.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(_make_badge("E"))

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Roblox Auto E")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Automatyczne przytrzymywanie klawisza")
        subtitle.setObjectName("subtitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        left.addLayout(header)

        left.addSpacing(22)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        divider.setFixedWidth(LEFT_COL_W)
        left.addWidget(divider)

        left.addSpacing(18)
        section_label = QLabel("USTAWIENIA")
        section_label.setObjectName("sectionLabel")
        f = section_label.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        section_label.setFont(f)
        left.addWidget(section_label)

        left.addSpacing(8)
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(LEFT_COL_W)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(6)

        reps_label = QLabel("Liczba powtorzen")
        reps_label.setObjectName("fieldLabel")
        self.reps_spin = QSpinBox()
        self.reps_spin.setObjectName("repsSpin")
        self.reps_spin.setRange(1, 999)
        self.reps_spin.setValue(1)
        self.reps_spin.setFixedWidth(110)
        self.reps_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hold_label = QLabel("Czas trzymania (s)")
        hold_label.setObjectName("fieldLabel")
        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setObjectName("holdSpin")
        self.hold_spin.setRange(0.1, 999.0)
        self.hold_spin.setDecimals(1)
        self.hold_spin.setSingleStep(1.0)
        self.hold_spin.setValue(21.0)
        self.hold_spin.setFixedWidth(110)
        self.hold_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card_layout.addWidget(reps_label)
        card_layout.addWidget(self.reps_spin)
        card_layout.addSpacing(10)
        card_layout.addWidget(hold_label)
        card_layout.addWidget(self.hold_spin)
        left.addWidget(card)
        left.addStretch(1)

        root.addLayout(left)

        # ---- pionowy separator ----
        v_divider = QFrame()
        v_divider.setObjectName("vDivider")
        v_divider.setFixedWidth(1)
        root.addWidget(v_divider)

        # ---- prawa kolumna: sterowanie ----
        right = QVBoxLayout()
        right.setSpacing(0)
        right.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.start_button = QPushButton("‣  Start   F5")
        self.start_button.setObjectName("startButton")
        self.start_button.setFixedHeight(44)
        self.start_button.setFixedWidth(RIGHT_COL_W)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.start_button)
        right.addLayout(btn_row)

        right.addSpacing(12)
        stop_row = QHBoxLayout()
        self.stop_button = QPushButton("■  Stop   Esc")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setFixedHeight(44)
        self.stop_button.setFixedWidth(RIGHT_COL_W)
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_row.addWidget(self.stop_button)
        right.addLayout(stop_row)

        right.addSpacing(24)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setFixedWidth(RIGHT_COL_W)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        right.addWidget(self.progress_bar)

        right.addSpacing(16)
        status_row, self.status_dot, self.status_label = _make_status_row()
        right.addLayout(status_row)
        right.addStretch(1)

        root.addLayout(right)

        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)

        # F5 dziala tylko gdy nasze okno ma fokus - Qt shortcuts sa domyslnie
        # skoped do widgetu/okna (WindowShortcut), nie sa globalne w systemie.
        # To swiadomie inaczej niz Esc (patrz register_global_hotkey), zeby
        # przypadkowy F5 w innym programie nie odpalal trzymania E w tle -
        # dokladnie ten sam blad zdarzyl sie w pierwszej wersji AHK.
        start_shortcut = QShortcut(QKeySequence("F5"), self)
        start_shortcut.activated.connect(self._on_start_clicked)

    def _build_thread(self) -> None:
        self._worker = SequenceWorker(self._stop_event)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._start_requested.connect(self._worker.run)
        self._worker.status_changed.connect(self._on_status_changed)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    # -- handlery -------------------------------------------------------

    def _on_start_clicked(self) -> None:
        if self._running:
            return
        reps = self.reps_spin.value()
        hold_seconds = self.hold_spin.value()
        error = worker_mod.validate(reps, hold_seconds)
        if error:
            QMessageBox.warning(self, "Blad", error)
            return

        self._running = True
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        input_sim.register_global_hotkey(int(self.window().winId()))
        self._start_requested.emit(reps, float(hold_seconds))

    def _on_stop_clicked(self) -> None:
        self._stop_event.set()

    def _on_status_changed(self, message: str, phase: str) -> None:
        self.status_label.setText(message)
        font = self.status_label.font()
        font.setBold(PHASE_BOLD.get(phase, False))
        self.status_label.setFont(font)
        _set_phase([self.progress_bar, self.status_dot], phase)

    def _on_progress_changed(self, percent: int) -> None:
        self.progress_bar.setValue(percent)

    def _on_finished(self, completed: bool) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        input_sim.unregister_global_hotkey(int(self.window().winId()))

    def shutdown(self) -> None:
        self._stop_event.set()
        input_sim.unregister_global_hotkey(int(self.window().winId()))
        self._thread.quit()
        self._thread.wait(2000)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._dark_titlebar_applied = False
        self._control_page: ControlPage | None = None

        try:
            self._cfg = load_config()
            self._cfg_error = None
        except ConfigError as exc:
            self._cfg = None
            self._cfg_error = exc

        self.setObjectName("MainWindow")
        self.setWindowTitle("Gatekey")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedSize(WINDOW_W, WINDOW_H)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # Jesli to urzadzenie ma juz zapisana udana weryfikacje (patrz
        # session.py), pomijamy ekran bramki calkowicie - Gatekey nie pyta
        # o autoryzacje przy kazdym uruchomieniu, tylko raz na komputer.
        if self._cfg is not None and session.has_valid_session():
            self._show_control_page()
        else:
            self._gate_page = GatePage(self._cfg, self._cfg_error)
            self._gate_page.unlocked.connect(self._on_unlocked)
            self._stack.addWidget(self._gate_page)

        version_row = QHBoxLayout()
        version_row.addStretch(1)
        version_label = QLabel(f"v{__version__}")
        version_label.setObjectName("versionLabel")
        version_row.addWidget(version_label)
        root.addLayout(version_row)

        self.setStyleSheet(QSS)

    def _on_unlocked(self) -> None:
        self._show_control_page()

    def _show_control_page(self) -> None:
        self._control_page = ControlPage()
        self._stack.addWidget(self._control_page)
        self._stack.setCurrentWidget(self._control_page)

    @property
    def active_stop_event(self) -> threading.Event | None:
        if self._control_page is not None:
            return self._control_page._stop_event
        return None

    # -- Qt lifecycle -----------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._dark_titlebar_applied:
            input_sim.apply_dark_titlebar(int(self.winId()))
            self._dark_titlebar_applied = True

    def closeEvent(self, event) -> None:
        if self._control_page is not None:
            self._control_page.shutdown()
        super().closeEvent(event)


def _try_auto_update(app: QApplication) -> None:
    """Sprawdza GitHub Releases i - jesli jest nowsza wersja - pobiera ja
    i restartuje aplikacje jako nowa wersja (updater.apply_update_and_relaunch
    konczy proces sam, sys.exit). Dziala tylko w spakowanym .exe: w trybie
    deweloperskim nie ma czego podmieniac. Kazdy blad (brak internetu, API
    niedostepne) jest cichy - aplikacja ma zawsze normalnie wystartowac,
    aktualizacja nigdy nie moze blokowac dzialania."""
    if not getattr(sys, "frozen", False):
        return

    update = updater.check_for_update()
    if update is None:
        return
    new_version, url = update

    dialog = QWidget()
    dialog.setObjectName("MainWindow")
    dialog.setWindowTitle("Gatekey")
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    dialog.setFixedSize(360, 130)
    dialog.setStyleSheet(QSS)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 24, 24, 24)
    label = QLabel(f"Pobieram aktualizacje Gatekey {new_version}...")
    label.setObjectName("statusLabel")
    bar = QProgressBar()
    bar.setObjectName("progressBar")
    bar.setRange(0, 100)
    bar.setTextVisible(False)
    layout.addWidget(label)
    layout.addSpacing(14)
    layout.addWidget(bar)
    dialog.show()
    app.processEvents()

    def on_progress(percent: int) -> None:
        bar.setValue(percent)
        app.processEvents()

    try:
        new_exe_path = updater.download_update(url, progress_cb=on_progress)
    except requests.RequestException:
        dialog.close()
        return

    dialog.close()
    updater.apply_update_and_relaunch(new_exe_path)  # konczy proces (sys.exit)


def main() -> None:
    app = QApplication(sys.argv)
    _try_auto_update(app)

    window = MainWindow()

    hotkey_filter = HotkeyEventFilter(window)
    app.installNativeEventFilter(hotkey_filter)
    window._hotkey_filter = hotkey_filter  # trzymaj referencje przy zyciu

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
