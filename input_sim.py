"""
Cala warstwa Win32: wysylanie klawisza E (scan-code SendInput), wyszukiwanie
i aktywacja okna po nazwie procesu, ciemny pasek tytulu okna, oraz globalny
skrot Esc (RegisterHotKey). Zadnych importow Qt w tym pliku - dzieki temu
worker.py moze byc testowany bez dotykania prawdziwego Win32 (patrz testy).
"""

import ctypes
import ctypes.wintypes as wintypes
import os

import win32api
import win32con
import win32gui
import win32process

# ---------------------------------------------------------------------------
# SendInput - wysylanie klawisza E po skan-kodzie (0x12), tak jak AHK "sc012".
# Nie uzywamy KEYEVENTF_EXTENDEDKEY - E to zwykly, nie-rozszerzony klawisz.
# ---------------------------------------------------------------------------

ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

E_SCANCODE = 0x12
INPUT_KEYBOARD = 1
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("time", ctypes.c_uint32),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", ctypes.c_uint32),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (
        ("type", ctypes.c_uint32),
        ("union", _INPUTUNION),
    )


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT

_user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
_user32.RegisterHotKey.restype = wintypes.BOOL

_user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.UnregisterHotKey.restype = wintypes.BOOL

_user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
_user32.AttachThreadInput.restype = wintypes.BOOL


def send_e_key(down: bool) -> None:
    """Wysyla jedno zdarzenie down/up klawisza E po skan-kodzie."""
    flags = KEYEVENTF_SCANCODE if down else (KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP)
    inp = INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTUNION(ki=KEYBDINPUT(0, E_SCANCODE, flags, 0, 0)),
    )
    sent = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


# ---------------------------------------------------------------------------
# Wyszukiwanie / aktywacja okna po nazwie procesu (np. "RobloxPlayerBeta.exe")
# ---------------------------------------------------------------------------

_PROCESS_QUERY_INFO = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ


def find_window_by_process(exe_name: str) -> int | None:
    """Zwraca HWND pierwszego widocznego, zatytulowanego okna nalezacego
    do procesu o podanej nazwie pliku .exe, albo None jesli nie znaleziono."""
    exe_name_lower = exe_name.lower()
    matches: list[int] = []

    def _enum_handler(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            hproc = win32api.OpenProcess(_PROCESS_QUERY_INFO, False, pid)
        except Exception:
            return
        try:
            path = win32process.GetModuleFileNameEx(hproc, 0)
        except Exception:
            path = None
        finally:
            win32api.CloseHandle(hproc)
        if path and os.path.basename(path).lower() == exe_name_lower:
            matches.append(hwnd)

    win32gui.EnumWindows(_enum_handler, None)
    return matches[0] if matches else None


def is_window_foreground(hwnd: int) -> bool:
    return win32gui.GetForegroundWindow() == hwnd


def activate_window(hwnd: int) -> bool:
    """Probuje uczynic okno aktywnym (foreground). Zwraca True jesli sie udalo."""
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass

    if is_window_foreground(hwnd):
        return True

    current_thread = win32api.GetCurrentThreadId()
    target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
    attached = False
    try:
        if target_thread and target_thread != current_thread:
            attached = bool(_user32.AttachThreadInput(current_thread, target_thread, True))
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        # SendInput dostarcza klawisze do okna z fokusem klawiatury (GetFocus),
        # nie tylko do aktywnej aplikacji pierwszego planu - bez tego niektore
        # gry/okna moga nie otrzymac wcisniec mimo ze sa "aktywne".
        win32gui.SetFocus(hwnd)
    except Exception:
        pass
    finally:
        if attached:
            _user32.AttachThreadInput(current_thread, target_thread, False)

    return is_window_foreground(hwnd)


# ---------------------------------------------------------------------------
# Ciemny pasek tytulu + zaokraglone rogi okna (Windows 10/11)
# ---------------------------------------------------------------------------

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2


def apply_dark_titlebar(hwnd: int) -> None:
    """Wlacza ciemny pasek tytulu i zaokraglone rogi. Bezpiecznie ignoruje
    blad na starszych wersjach Windows, ktore tego nie wspieraja."""
    try:
        value = ctypes.c_int(1)
        _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
        corner = ctypes.c_int(_DWMWCP_ROUND)
        _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner), ctypes.sizeof(corner)
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Globalny skrot Esc (dziala nawet gdy nasze okno nie jest aktywne) -
# rejestrowany tylko na czas trwania sekwencji, patrz main.py.
# ---------------------------------------------------------------------------

ESC_HOTKEY_ID = 1
_MOD_NOREPEAT = 0x4000
_VK_ESCAPE = 0x1B
WM_HOTKEY = 0x0312


def register_global_hotkey(hwnd: int) -> bool:
    return bool(_user32.RegisterHotKey(wintypes.HWND(hwnd), ESC_HOTKEY_ID, _MOD_NOREPEAT, _VK_ESCAPE))


def unregister_global_hotkey(hwnd: int) -> None:
    _user32.UnregisterHotKey(wintypes.HWND(hwnd), ESC_HOTKEY_ID)
