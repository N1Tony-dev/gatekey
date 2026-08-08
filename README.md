# Gatekey

Desktopowa aplikacja (Windows, PySide6) z bramka dostepu przez Discord:
uzytkownik laczy konto Discord, aplikacja sprawdza czy ma wymagana role na
skonfigurowanym serwerze, i dopiero wtedy odblokowuje narzedzie "Roblox
Auto E" (automatyczne przytrzymywanie klawisza E z przerwami).

Aplikacja aktualizuje sie sama - przy kazdym starcie sprawdza GitHub
Releases tego repo i jesli jest nowsza wersja, pobiera ja i restartuje sie
automatycznie, bez potrzeby recznego pobierania nowej wersji ze strony.

## Uruchomienie w trybie deweloperskim

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
copy device_binding_secret.py.example device_binding_secret.py
```

Uzupelnij `.env` (patrz sekcja "Konfiguracja Discorda" ponizej) i
`device_binding_secret.py` (token opisany w tym pliku), potem:

```
.venv\Scripts\python.exe main.py
```

## Konfiguracja Discorda

1. https://discord.com/developers/applications -> New Application
2. OAuth2 -> General: skopiuj **Client ID** / **Client Secret** -> `.env`
3. OAuth2 -> General -> Redirects: dodaj `http://localhost:47624/callback`
4. Bot -> Reset Token -> skopiuj **Bot Token** -> `.env`
5. OAuth2 -> URL Generator -> zaznacz tylko scope `bot`, permissions zostaw
   puste -> otworz wygenerowany link -> dodaj bota na docelowy serwer
6. W Discordzie wlacz Tryb dewelopera (Ustawienia -> Zaawansowane), skopiuj
   ID serwera i ID wymaganej roli -> `.env`

## Testy

```
.venv\Scripts\python.exe -m pytest tests\ -v
```

Wszystkie testy dzialaja na w pelni zamockowanym Win32/Discord/GitHub API -
zaden test nigdy nie wysyla prawdziwych klawiszy ani nie laczy sie z
prawdziwym Discordem/GitHubem.

## Budowanie .exe

```
.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name Gatekey --icon icon.ico main.py
```

Wynik: `dist\Gatekey.exe`. Plik `.env` musi lezec **obok** `.exe` (nie jest
wbudowany w plik wykonywalny - kazda instalacja ma wlasna konfiguracje).

`device_binding_secret.py` to co innego - MUSI istniec lokalnie **przed**
budowaniem, zeby PyInstaller wbudowal token w `.exe` (ten token jest
wspolny dla wszystkich instalacji, sluzy do wiazania kont Discord z
komputerami - patrz `device_binding.py`). Nigdy nie trafia do gita.

## Wydawanie nowej wersji (auto-update)

Aplikacja porownuje wlasny numer wersji (`version.py`) z tagiem najnowszego
Release na GitHubie. Zeby wypuscic aktualizacje:

1. Podbij numer w `version.py`, np. `__version__ = "1.1.0"`
2. Zbuduj: `.venv\Scripts\python.exe -m PyInstaller --onefile --windowed --name Gatekey --icon icon.ico main.py`
3. Opublikuj release z tagiem **dokladnie** w formacie `vX.Y.Z` i zalacznikiem
   `Gatekey.exe`:
   ```
   gh release create v1.1.0 dist/Gatekey.exe --title "v1.1.0" --notes "Opis zmian"
   ```

Wszystkie dzialajace kopie aplikacji same wykryja nowa wersje przy
najblizszym uruchomieniu, pobiora ja i zrestartuja sie automatycznie.

## Struktura

- `main.py` - GUI (PySide6): ekran bramki Discord + ekran sterowania Roblox Auto E
- `worker.py` - logika sekwencji trzymania klawisza E
- `input_sim.py` - warstwa Win32 (SendInput, wyszukiwanie/aktywacja okna, ciemny motyw, globalny hotkey)
- `discord_gate.py` - logowanie OAuth2 + sprawdzenie roli przez token bota
- `device_binding.py` - twarda blokada "jedno konto Discord = jeden komputer" (repo gatekey-devices)
- `session.py` - lokalny cache zweryfikowanej sesji na danym komputerze
- `config.py` - wczytywanie/walidacja `.env`
- `updater.py` - sprawdzanie i pobieranie aktualizacji z GitHub Releases
- `version.py` - numer wersji
- `holdE.ahk` - pierwotna wersja narzedzia w AutoHotkey (referencja, nieuzywana)
