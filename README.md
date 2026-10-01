# Visual Novel RPC

Show the visual novel you're reading on your **Discord profile**: game name, current chapter or route, time read and cover.

![Preview](image/preview.png)

Windows tray app. It reads the title of the VN's window, so it works with most engines without any setup.

## Features

- **Auto-detects the VN** you're playing (Ren'Py, KiriKiri, Siglus, Unity, …), or lets you pick the window by hand.
- **Shows where you are**: prologue, chapter, route, ending… read straight from the window title (EN / FR / JP).
- **Tracks time read** per VN, saved between sessions.
- **Covers** from VNDB, an image URL or a local file, with a built-in crop tool.
- **Steam names**: installed Steam games get their proper name automatically.
- **Library** of every VN you've played, with time read and a Play button.
- **Share stats**: a "My week / my month in visual novels" card (covers, time read, VNs finished), copied as an image to paste on Discord.
- **Japanese locale**: set a VN to start through Locale Emulator or NTLEA, and Play launches it that way.
- **Screenshots**: press Print Screen while reading to capture the game's window. Each VN gets its own folder, and its page in the Library shows them; the gallery copies, opens or deletes them.
- **Idle mode** (optional): when the VN stays in the background, your Discord status clears and the timers stop until you go back to it.
- **Export / import your data** (settings, Library, time read, custom covers) as one file, e.g. to move to another PC.
- **Privacy per game**: Full, Partial (no chapter), Private (just "Visual Novel") or Off.
- NSFW covers are blurred and never sent to Discord unless you allow it.
- Optional **launch at Windows startup**.

## Screenshots

<p align="center"><img src="image/main.png" width="680" alt="Main window: the VN being read and a preview of the Discord status"></p>

**Library** — every VN you've read, and a page per VN with its status, VNDB rating, reading history and screenshots.

<p align="center"><img src="image/library.png" width="680" alt="Library"></p>
<p align="center"><img src="image/vn-page.png" width="820" alt="A VN's page in the Library"></p>

**Screenshots** — press Print Screen in game; browse, copy or delete them in the gallery.

<p align="center"><img src="image/gallery.png" width="820" alt="Screenshot gallery"></p>

**Share your week** — a card to paste on Discord.

<p align="center"><img src="image/share-card.png" width="720" alt="My week in visual novels card"></p>

**Themes** — Dark, Light, Sakura, a few presets, or your own colors.

<p align="center"><img src="image/themes.png" width="900" alt="The main window in the Dark, Sakura and Lilac themes"></p>

## Install

Download `VisualNovelRPC.exe` and run it. Nothing else is needed.

Discord desktop must be open, with **Settings → Activity Privacy → Share your detected activities** turned on.

The app checks for a new release each time it starts and offers to update itself (you can turn that off in **Settings → App**).

## Use your own Discord app (optional)

The app already works out of the box. If you want your own name and default image on Discord:

1. Create an application at <https://discord.com/developers/applications>.
2. Paste its **Application ID** in the app under **Settings → Discord Application ID**.
3. In **Rich Presence → Art Assets**, upload an image named `vn_cover`. It's shown when a cover can't be displayed on Discord (local files and cropped images).

## Run from source

Python 3.10+ on Windows.

```
pip install -r requirements.txt
python -m vnrpc
```

## Build the .exe

```
pip install -r requirements-dev.txt
python build.py
```

The result is `dist\VisualNovelRPC.exe`. Close the app before building.

## Publish a release

1. Bump `__version__` in `vnrpc/__init__.py` (e.g. `1.2.1`) and build.
2. Create a GitHub release tagged `v1.2.1` (or `1.2.1`) and attach `dist\VisualNovelRPC.exe`.

Copies already installed see the newer tag at their next launch, download the attached .exe and restart on it.

## Tests

```
python -m pytest -q
python tools/fake_vn_window.py --title "Grisaia no Kajitsu - Yumiko Route - Chapter 4"
```

`fake_vn_window.py` opens a dummy window so you can test detection without a real VN.

## Where settings are saved

Everything is in `%APPDATA%\VisualNovelRPC\`:

| File | What |
|---|---|
| `config.yaml` | app settings |
| `games\<title>.yaml` | one file per VN (safe to edit or rename) |
| `cache\` | VNDB results, covers and screenshot thumbnails |

Screenshots go to `Pictures\Visual Novel RPC\<VN title>\` (you can pick another folder in Settings).
