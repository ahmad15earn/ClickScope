# ClickScope (MVP)

Counts how many times you click in each desktop app and website, then shows
simple stats and suggestions. Counts clicks only, not time. Light theme, local
data, no internet access.

## 1. Get the EXE (pick one)

### Option A: no tools on your PC (GitHub builds it for you, ~3 minutes)
1. Make a free account at github.com and create a **new private repository**.
2. Click **Add file > Upload files**, drag in the *contents* of this ZIP
   (so `src`, `assets`, `.github` etc. are at the top level) and commit.
   (If the hidden `.github` folder doesn't upload by dragging, use
   **Add file > Create new file**, name it `.github/workflows/build-windows.yml`
   and paste the contents of that file.)
3. Open the **Actions** tab > **Build ClickScope EXE** > **Run workflow**.
4. When it finishes, open the run and download **ClickScope-Windows**
   (a ZIP holding `ClickScope.exe`). Unzip, double-click, done.

### Option B: build on your own PC
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Double-click `build.bat`.
3. Your app appears in `dist\ClickScope.exe`.

## 2. Using ClickScope
- Open `ClickScope.exe`. Tracking starts immediately.
- **Overview**: total clicks, apps used, websites, busiest hour, plus most/least
  used apps and websites. Switch between Today / 7 days / All time.
- **Suggestions**: tips based on your click patterns.
- **Settings**: website tracking on/off, start with Windows, export CSV,
  open data folder, clear all data.
- **Minimize** the window to keep tracking in the background.
  **Closing** the window quits the app and stops tracking.
- **Pause** stops counting until you press Resume.

## 3. Privacy
- Counts mouse clicks only. No keystrokes, screenshots, cursor paths or screen content.
- Saves only daily totals per app / website and per hour of day, in
  `%APPDATA%\ClickScope\clickscope.db` (SQLite). Nothing is ever sent anywhere.
- Websites are guessed from the browser's **tab title** (e.g. "... - YouTube"
  becomes "YouTube"), never the URL. Known sites get clean names; for unknown
  pages the last part of the title is used. Turn this off in Settings if you prefer.
- Clicks inside ClickScope itself and software-generated clicks are ignored.

## 4. Known limits of this MVP
- Windows 10/11 only. Apps running as Administrator can't be identified and
  show up as "Other / system" (unless ClickScope is also run as admin).
- The EXE is unsigned, so Windows SmartScreen may warn on first run
  ("More info > Run anyway"). Because ClickScope uses a mouse hook, some
  antivirus tools may also flag it; that is a false positive. You can read every
  line in `src/`.
- No system-tray icon yet (minimize to the taskbar instead).

## 5. Project layout
```
src/main.py      app entry point
src/ui.py        light, minimalist Tkinter interface
src/winhook.py   Windows mouse hook + window lookup (ctypes, no dependencies)
src/core.py      local storage, labeling, suggestion rules
assets/          logo + app icon (app.ico)
tests/           logic tests (python tests/test_core.py)
build.bat        builds dist\ClickScope.exe
.github/         optional cloud build (Option A)
```
Run from source without building: `python src\main.py` (Python 3.10+, no extra packages).
