; ============================================================
; holdE.ahk - trzyma klawisz E, puszcza na 1s, N razy (Roblox)
;
; Wymaga AutoHotkey v2: https://www.autohotkey.com/
; Dwuklik na ten plik, zeby uruchomic.
;
; F5  = Start (uzywa wartosci wpisanych w oknie)
; Esc = Stop  (natychmiast puszcza E i przerywa)
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force

SendMode "Input"
SetKeyDelay -1, -1
#UseHook true

ROBLOX_EXE := "RobloxPlayerBeta.exe"
E_SC := "sc012"     ; skan-kod klawisza E - czesto bardziej niezawodne dla gier niz {e}

HOLD_MS := 21000
GAP_MS  := 1000
STEP_MS := 100

; ---------------- Paleta (dark mode) ----------------
COL_BG            := 0x18181B   ; tlo okna
COL_CARD          := 0x212126   ; panel ustawien
COL_FIELD         := 0x2A2A31   ; tlo pol edycji
COL_BORDER        := 0x2D2D33   ; linie / obwodki
COL_ACCENT        := 0x5865F2   ; indigo - start / odliczanie
COL_ACCENT_HOVER  := 0x6C76F5
COL_SUCCESS       := 0x3DDC84   ; zielony - trzymanie E
COL_WARN          := 0xF5A623   ; bursztynowy - przerwa
COL_DANGER        := 0xE74C3C   ; czerwony - stop
COL_STOP_BG       := 0x2A2A31
COL_STOP_BG_HOVER := 0x35353D
COL_TEXT          := 0xF2F2F2
COL_TEXT_DIM      := 0x9A9A9F
COL_TEXT_FAINT    := 0x6E6E73
COL_TRACKBG       := 0x232328

running := false
stopRequested := false
eIsDown := false
hoverStart := false
hoverStop := false

; ---------------- GUI ----------------
MyGui := Gui("+AlwaysOnTop -MaximizeBox", "Roblox Auto E")
try {
    DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", MyGui.Hwnd, "Int", 20, "Int*", 1, "Int", 4)   ; dark titlebar
    DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", MyGui.Hwnd, "Int", 33, "Int*", 2, "Int", 4)   ; rounded corners
}
MyGui.MarginX := 28
MyGui.MarginY := 24
MyGui.BackColor := Hex6(COL_BG)

CARD_W := 304

; ---- Naglowek: znaczek + tytul ----
Badge := MyGui.AddText("xm ym w48 h48 Center 0x200 Background" . Hex6(COL_ACCENT), "E")
Badge.SetFont("s20 Bold cFFFFFF", "Segoe UI")
RoundCtrl(Badge, 14)

MyGui.SetFont("s14 Bold c" . Hex6(COL_TEXT), "Segoe UI")
MyGui.AddText("x+14 yp+2", "Roblox Auto E")
MyGui.SetFont("s9 c" . Hex6(COL_TEXT_DIM) . " Norm", "Segoe UI")
MyGui.AddText("x+0 y+2", "Automatyczne przytrzymywanie klawisza")

MyGui.AddText("xm y+22 w" . CARD_W . " h1 Background" . Hex6(COL_BORDER), "")

MyGui.SetFont("s8 Bold c" . Hex6(COL_TEXT_FAINT), "Segoe UI")
MyGui.AddText("xm y+18", "USTAWIENIA")

; ---- Karta ustawien (tlo rysowane pod polami) ----
CardY := 0
CardCtrl := MyGui.AddText("xm y+8 w" . CARD_W . " h116 Background" . Hex6(COL_CARD), "")
CardCtrl.GetPos(&cardX, &cardY)
RoundCtrl(CardCtrl, 12)

padX := cardX + 18
row1Y := cardY + 16
row2Y := cardY + 66

MyGui.SetFont("s9 c" . Hex6(COL_TEXT_DIM) . " Norm", "Segoe UI")
MyGui.AddText("x" . padX . " y" . row1Y, "Liczba powtorzen")
MyGui.SetFont("s11 c" . Hex6(COL_TEXT) . " Norm", "Segoe UI")
EditReps := MyGui.AddEdit("x" . padX . " y+6 w110 h30 -0x200 Center Background" . Hex6(COL_FIELD) . " c" . Hex6(COL_TEXT), "1")
MyGui.AddUpDown("Range1-999", 1)

MyGui.SetFont("s9 c" . Hex6(COL_TEXT_DIM) . " Norm", "Segoe UI")
MyGui.AddText("x" . padX . " y" . row2Y, "Czas trzymania (s)")
MyGui.SetFont("s11 c" . Hex6(COL_TEXT) . " Norm", "Segoe UI")
EditHold := MyGui.AddEdit("x" . padX . " y+6 w110 h30 -0x200 Center Background" . Hex6(COL_FIELD) . " c" . Hex6(COL_TEXT), "21")
MyGui.AddUpDown("Range1-999", 21)

; ---- Przyciski ----
MyGui.SetFont("s11 Bold cFFFFFF", "Segoe UI")
BtnStart := MyGui.AddText("xm y+22 w146 h44 Center 0x200 Background" . Hex6(COL_ACCENT), "‣  Start   F5")
RoundCtrl(BtnStart, 10)

MyGui.SetFont("s11 Bold c" . Hex6(COL_TEXT_DIM), "Segoe UI")
BtnStop := MyGui.AddText("x+12 yp w146 h44 Center 0x200 Background" . Hex6(COL_STOP_BG), "■  Stop   Esc")
RoundCtrl(BtnStop, 10)

ProgBar := MyGui.AddProgress("xm y+22 w" . CARD_W . " h8", 0)

MyGui.SetFont("s9 c" . Hex6(COL_TEXT_DIM) . " Norm", "Segoe UI")
StatusDot := MyGui.AddText("xm y+16 w10 h10 Center 0x200 Background" . Hex6(COL_TEXT_FAINT), "")
RoundCtrl(StatusDot, 5)
TextStatus := MyGui.AddText("x+8 yp-2 w270", "Gotowy.")

MyGui.Show("Hide")
InitProgressBar()
if !DllCall("AnimateWindow", "Ptr", MyGui.Hwnd, "UInt", 300, "UInt", 0x00080000) {
    MyGui.Show()
}

BtnStart.OnEvent("Click", StartSequence)
BtnStop.OnEvent("Click", StopSequence)
MyGui.OnEvent("Close", (*) => ExitApp())

SetTimer(HoverCheck, 40)

; F5 dziala tylko gdy aktywne jest okno tej aplikacji - zeby przypadkowy
; F5 w innym programie (np. odswiezenie w przegladarce) nie uruchamial
; trzymania klawisza w Robloxie w tle.
#HotIf WinActive("ahk_id " . MyGui.Hwnd)
F5::StartSequence()
#HotIf

; Esc zostaje globalny - to "bezpiecznik" awaryjny, ktory musi zadzialac
; nawet gdy w danym momencie aktywne jest okno Robloxa, a nie nasza aplikacja.
; StopSequence i tak nic nie robi, jesli sekwencja nie jest uruchomiona.
Esc::StopSequence()

StartSequence(*) {
    global running, stopRequested, HOLD_MS, GAP_MS, STEP_MS, COL_ACCENT, COL_SUCCESS, COL_WARN, COL_DANGER, COL_TEXT_FAINT

    if (running) {
        return
    }

    savedReps := EditReps.Value
    if !IsInteger(savedReps) || Integer(savedReps) <= 0 {
        MsgBox("Podaj dodatnia liczbe calkowita powtorzen.", "Blad", "Iconx")
        return
    }
    reps := Integer(savedReps)

    savedHold := EditHold.Value
    if !IsNumber(savedHold) || Number(savedHold) <= 0 {
        MsgBox("Podaj dodatni czas trzymania w sekundach.", "Blad", "Iconx")
        return
    }
    HOLD_MS := Round(Number(savedHold) * 1000)

    running := true
    stopRequested := false

    ; Daj czas na przelaczenie sie do okna Robloxa, zanim zaczniemy wysylac E
    SetBarColor(COL_ACCENT)
    SetStatus("Start za 3s... kliknij w okno Robloxa!", COL_ACCENT, "Bold")
    if (!WaitOrStop(3000, STEP_MS)) {
        running := false
        SetBarColor(COL_DANGER)
        SetStatus("Zatrzymano.", COL_DANGER, "Bold")
        stopRequested := false
        return
    }

    Loop reps {
        if (stopRequested) {
            break
        }
        cycleNum := A_Index

        if (!EnsureRobloxActive()) {
            break
        }

        SetBarColor(COL_SUCCESS)
        SetStatus("Cykl " . cycleNum . "/" . reps . " - trzymanie E", COL_SUCCESS, "Bold")
        holdTime := HOLD_MS + Random(-150, 150)
        if (!HoldE(holdTime)) {
            break
        }
        PressE(false)

        if (stopRequested) {
            break
        }
        SetBarColor(COL_WARN)
        SetStatus("Cykl " . cycleNum . "/" . reps . " - przerwa", COL_WARN, "Norm")
        gapTime := GAP_MS + Random(-100, 100)
        if (!WaitOrStop(gapTime, STEP_MS)) {
            break
        }
    }

    PressE(false)
    running := false

    if (stopRequested) {
        SetBarColor(COL_DANGER)
        SetStatus("Zatrzymano.", COL_DANGER, "Bold")
    } else {
        SetBarColor(COL_SUCCESS)
        UpdateProgress(100)
        SetStatus("Zakonczono (" . reps . " cykli).", COL_SUCCESS, "Bold")
    }
    stopRequested := false
}

StopSequence(*) {
    global running, stopRequested
    if (running) {
        stopRequested := true
    }
}

; Upewnia sie, ze Roblox jest aktywnym oknem - probuje go aktywowac,
; a jesli sie nie da (np. zamkniety), czeka na uzytkownika.
EnsureRobloxActive() {
    global stopRequested, ROBLOX_EXE, COL_DANGER

    if (WinActive("ahk_exe " . ROBLOX_EXE)) {
        return true
    }

    if WinExist("ahk_exe " . ROBLOX_EXE) {
        WinActivate("ahk_exe " . ROBLOX_EXE)
        WinWaitActive("ahk_exe " . ROBLOX_EXE, , 2)
    }

    while (!WinActive("ahk_exe " . ROBLOX_EXE)) {
        if (stopRequested) {
            return false
        }
        SetStatus("Roblox nie jest aktywnym oknem! Kliknij w Roblox - czekam...", COL_DANGER, "Bold")
        Sleep(200)
    }
    return true
}

WaitOrStop(totalMs, stepMs) {
    global stopRequested
    elapsed := 0
    while (elapsed < totalMs) {
        if (stopRequested) {
            return false
        }
        remaining := totalMs - elapsed
        thisStep := (remaining < stepMs) ? remaining : stepMs
        Sleep(thisStep)
        elapsed += thisStep
        UpdateProgress(elapsed / totalMs * 100)
    }
    return true
}

PressE(down) {
    global eIsDown, E_SC
    if (down && !eIsDown) {
        Send("{" . E_SC . " down}")
        eIsDown := true
    } else if (!down && eIsDown) {
        Send("{" . E_SC . " up}")
        eIsDown := false
    }
}

; Trzyma E przez durationMs, dosylajac powtorzone sygnaly "down"
; (jak prawdziwa klawiatura w trybie auto-repeat: ~500ms opoznienia,
; potem co ~33ms) - niektore gry licza trzymanie po powtarzanych KEYDOWN,
; nie tylko po stanie klawisza.
HoldE(durationMs) {
    global stopRequested, E_SC
    PressE(true)

    elapsed := 0
    nextRepeat := 500
    repeatInterval := 33
    step := 15

    while (elapsed < durationMs) {
        if (stopRequested) {
            return false
        }
        remaining := durationMs - elapsed
        thisStep := (remaining < step) ? remaining : step
        Sleep(thisStep)
        elapsed += thisStep
        UpdateProgress(elapsed / durationMs * 100)

        if (elapsed >= nextRepeat) {
            Send("{" . E_SC . " down}")
            nextRepeat += repeatInterval
        }
    }
    return true
}

SetStatus(msg, dotColor := 0x6E6E73, weight := "Norm") {
    global TextStatus, StatusDot, COL_TEXT_DIM
    TextStatus.SetFont("c" . Hex6(COL_TEXT_DIM) . " " . weight, "Segoe UI")
    TextStatus.Text := msg
    StatusDot.Opt("Background" . Hex6(dotColor))
}

; ---------------- Hover na przyciskach ----------------
HoverCheck() {
    global MyGui, BtnStart, BtnStop, hoverStart, hoverStop
    global COL_ACCENT, COL_ACCENT_HOVER, COL_STOP_BG, COL_STOP_BG_HOVER

    MouseGetPos(&mx, &my, &winId, &ctrlHwnd, 2)
    isOverStart := (winId = MyGui.Hwnd && ctrlHwnd = BtnStart.Hwnd)
    isOverStop  := (winId = MyGui.Hwnd && ctrlHwnd = BtnStop.Hwnd)

    if (isOverStart != hoverStart) {
        hoverStart := isOverStart
        BtnStart.Opt("Background" . Hex6(hoverStart ? COL_ACCENT_HOVER : COL_ACCENT))
    }
    if (isOverStop != hoverStop) {
        hoverStop := isOverStop
        BtnStop.Opt("Background" . Hex6(hoverStop ? COL_STOP_BG_HOVER : COL_STOP_BG))
    }
}

; ---------------- Zaokraglone rogi kontrolek ----------------
RoundCtrl(ctrl, radius) {
    ctrl.GetPos(, , &w, &h)
    hRgn := DllCall("CreateRoundRectRgn", "Int", 0, "Int", 0, "Int", w + 1, "Int", h + 1, "Int", radius, "Int", radius, "Ptr")
    DllCall("SetWindowRgn", "Ptr", ctrl.Hwnd, "Ptr", hRgn, "Int", true)
}

; ---------------- Pasek postepu (kolorowy, dark mode) ----------------
InitProgressBar() {
    global ProgBar, COL_TRACKBG, COL_ACCENT
    DllCall("uxtheme\SetWindowTheme", "Ptr", ProgBar.Hwnd, "Str", "", "Str", "")
    DllCall("SendMessage", "Ptr", ProgBar.Hwnd, "UInt", 0x2001, "Ptr", 0, "Ptr", ToColorRef(COL_TRACKBG)) ; PBM_SETBKCOLOR
    SetBarColor(COL_ACCENT)
}

SetBarColor(colorHex) {
    global ProgBar
    DllCall("SendMessage", "Ptr", ProgBar.Hwnd, "UInt", 0x409, "Ptr", 0, "Ptr", ToColorRef(colorHex)) ; PBM_SETBARCOLOR
}

UpdateProgress(percent) {
    global ProgBar
    if (percent < 0) {
        percent := 0
    }
    if (percent > 100) {
        percent := 100
    }
    ProgBar.Value := Round(percent)
}

ToColorRef(rrggbb) {
    r := (rrggbb >> 16) & 0xFF
    g := (rrggbb >> 8) & 0xFF
    b := rrggbb & 0xFF
    return (b << 16) | (g << 8) | r
}

Hex6(n) {
    return Format("{:06X}", n)
}
