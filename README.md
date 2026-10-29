# ClickScope

Counts how many times you click in each desktop app and website, then shows
statistics, graphs and (after 30 days) suggestions. It counts clicks, not time.
Light theme, local data, no internet access. Uses your logo (transparent PNG).

## 1. Get the EXE (pick one)

### Option A: no tools on your PC (GitHub builds it for you, ~3 minutes)
1. Make a free account at github.com and create a **new private repository**.
2. **Add file > Upload files**, drag in the *contents* of this ZIP
   (so `src`, `assets`, `.github` ... are at the top level) and commit.
   If the hidden `.github` folder doesn't upload, use **Add file > Create new file**,
   name it `.github/workflows/build-windows.yml` and paste in that file's contents.
3. **Actions** tab > **Build ClickScope EXE** > **Run workflow**.
4. When it finishes, open the run and download **ClickScope-Windows** (a ZIP with
   `ClickScope.exe`). Unzip, double-click, done.

### Option B: build on your own PC
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Double-click `build.bat`. Your app appears in `dist\ClickScope.exe`.

## 2. See it in 10 seconds: demo mode
Double-click `ClickScope-Demo.bat` (put it next to `ClickScope.exe`), or use
**Settings > Preview with sample data**. You get 30 days of sample activity so you
can explore every graph and the unlocked suggestions. Your real data is untouched
and nothing is tracked in demo mode.

## 3. What's new in this version
- **Fixed:** the donut chart turning fully pink with many small slices (rings are now drawn as polygons).
- **Inventory (new tab) and star:** clicks measure habit, not importance. Tap the star next to an app in
  Overview, answer the weekly check-in, or add an app by name (e.g. your backup tool). Export a
  recovery checklist (.txt) of what to reinstall first. Kept apps are never suggested for removal.
- **No dead month:** during the first 30 days you get a weekly check-in ("You used 8 apps regularly this
  week. Which belong in your recovery inventory?") and early insights. Full suggestions still unlock after
  30 days AND at least 7 active days.
- **Back up / restore** your data (Settings), for a new PC or after reinstalling Windows.
- **Close = keep running:** the X button minimizes; use *Quit ClickScope* in the sidebar to exit.
- **Ignore list:** right-click a row in Overview to stop counting an app or website.

## 4. Using ClickScope
- **Overview**: total clicks (with change vs. the previous period), apps used,
  websites, busiest hour, an activity chart (hover for exact numbers) and Most/Least
  lists for apps and websites. Switch Today / 7 days / 30 days / All time.
- **Graphs**: donut chart of where your clicks go (apps or websites), busiest
  weekdays, and busiest hours of the day.
- **Suggestions**: ClickScope first learns from **30 days** of your activity. Until
  then you see a progress ring ("Day 4 of 30") and the unlock date. After day 30 you
  get tips based on your last 30 days. *Clear all data* restarts the 30 days.
- **Settings**: website tracking on/off, start with Windows, export CSV, open data
  folder, preview with sample data, clear all data.
- **Minimize** keeps tracking in the background. **Closing** the window quits.
  **Pause** stops counting until you press Resume. The green dot pulses on every click.
- Motion follows Windows: if "Show animations" is off, ClickScope skips the animations.

## 5. Privacy
- Counts mouse clicks only. No keystrokes, screenshots, cursor paths or screen content.
- Saves only daily totals per app / website and per hour of day, in
  `%APPDATA%\ClickScope\clickscope.db`. Nothing is ever sent anywhere.
- Websites come from the browser's **tab title** ("... - YouTube" becomes "YouTube"),
  never the URL. Turn this off in Settings if you prefer.
- Clicks inside ClickScope and software-generated clicks are ignored.

## 6. Known limits
- Windows 10/11 only. Apps running as Administrator show as "Other / system".
- The EXE is unsigned: SmartScreen may warn ("More info > Run anyway") and some
  antivirus tools may flag the mouse hook (false positive). All source is in `src/`.
- No system-tray icon yet (minimize to the taskbar instead).

## 7. Project layout
```
src/main.py      entry point (flags: --minimized, --demo)
src/ui.py        pages: Overview, Graphs, Suggestions, Settings
src/widgets.py   custom-drawn cards, charts, controls, sidebar
src/motion.py    spring animation engine (interruptible, reduced-motion aware)
src/theme.py     colours and fonts
src/winhook.py   Windows mouse hook + window lookup (ctypes, no dependencies)
src/core.py      local storage, labeling, suggestion rules, demo data
assets/          logo.png (transparent), app.ico, UI logos
docs/            preview screenshots
tests/           python tests/test_core.py ; tests/render.py (headless screenshots)
build.bat        builds dist\ClickScope.exe
.github/         optional cloud build (Option A)
```
Run from source: `python src\main.py` (Python 3.10+, no extra packages).
