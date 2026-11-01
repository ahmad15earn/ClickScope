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
4. When it finishes, open the run and download **ClickScope-Setup** (the installer). Run it:
   it asks which folder to install to, offers a desktop shortcut and "start with Windows",
   and adds an uninstaller. **ClickScope-Portable** is the plain `ClickScope.exe` if you prefer.

### Option B: build on your own PC
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Double-click `build.bat`. Your app appears in `dist\ClickScope.exe`.
   For the installer too, install Inno Setup 6 (free, jrsoftware.org) first; it appears in `installer_output\`.

## 2. See it in 10 seconds: demo mode
Double-click `ClickScope-Demo.bat` (put it next to `ClickScope.exe`), or use
**Settings > Preview with sample data**. You get 30 days of sample activity so you
can explore every graph and the unlocked suggestions. Your real data is untouched
and nothing is tracked in demo mode.

## 3. First run: guided setup
On first launch a small blue triangle cursor, separate from your mouse, moves around the screen by itself,
shows where to click, performs example clicks and narrates each step (like someone showing you around):
1. ClickScope scans installed programs (and Start Menu shortcuts) by itself, no folder opening needed.
2. You tick the apps you can't live without; they go into your recovery inventory.
3. You choose which browsers it may read, once, locally. It lists your most-visited and bookmarked
   **domains** and you tick the favourites. (Only domain names are saved.)
4. A thank-you screen, then click counting starts (and the 30-day learning window with it).
The full scan is saved too, and **Export recovery checklist** writes everything to a .txt file.
Re-run any time: Inventory > *Scan this PC*, or Settings > *Run setup guide*.

## 3a. Software recovery (new tab)
Pick the apps (your inventory is pre-selected) and a folder; ClickScope downloads each app's official
installer in the background into `<folder>\<App name>\`, shows live progress, lets you **Retry** any failure
with one click, and writes `RECOVERY.txt` as an index. Nothing is installed automatically.
- Uses Windows Package Manager (**winget**, built into Windows 10/11 as "App Installer"), so downloads come
  from its official, hash-checked repository. If winget is missing, ClickScope tells you how to get it.
- Apps without a winget source (paid, Store-only, niche) are marked *Manual*, with a **Search web** link.
- After the setup guide, the cursor gives a short tour of every tab (replay: Settings > *Replay tour*).

## 3b. What's new in this version
- **Recovery-first redesign:** Home now shows recovery readiness instead of click totals; the Graphs tab and
  vanity stats (busiest hour/day) are gone. Insights became recovery-centred (unprotected apps, unused software
  and disk space, subscription reminders).
- **Privacy up front:** the welcome screen states it plainly; `TRUST.md` + an automated check let anyone verify it.
- **Resource-friendly:** Settings > *Count clicks in the background* can switch tracking off completely.

- **Fixed:** the donut chart turning fully pink with many small slices (rings are now drawn as polygons).
- **Inventory (new tab) and star:** clicks measure habit, not importance. Tap the star next to an app in
  Overview, answer the weekly check-in, or add an app by name (e.g. your backup tool). Export a
  recovery checklist (.txt) of what to reinstall first. Kept apps are never suggested for removal.
- **No dead month:** during the first 30 days you get a weekly check-in ("You used 8 apps regularly this
  week. Which belong in your recovery inventory?") and early insights. Full suggestions still unlock after
  30 days AND at least 7 active days.
- **Back up / restore** your data (Settings), for a new PC or after reinstalling Windows.
- **Always on:** the X button hides the window; ClickScope keeps running and starts with Windows.
- **Ignore list:** right-click a row in Overview to stop counting an app or website.

## 3c. Account and cloud backup (Account tab)
Create an account (email + password) and your **recovery list** (installed-app list, must-keep apps and sites, recovery
selection) is backed up to Supabase and syncs automatically. On a new PC: install ClickScope, choose
**Restore with Google** on the welcome screen (or Account > Sign in), and it opens Recovery with everything
ready to download. **Clicks are never uploaded.** Data is protected by Row Level Security (only you can read it).

**Sign-in method:** email + password (works with just Supabase, no Google account setup or credit card needed).
Google sign-in is optional and off by default (`GOOGLE_ENABLED` in `src/cloud_config.py`).

Already done for you: the Supabase project `clickscope` exists, `supabase/schema.sql` is applied (Row Level
Security on), and `src/cloud_config.py` points to it.

One step left for you (1 minute): Supabase dashboard > project **clickscope** > Authentication > Sign In / Providers
> Email: switch **Confirm email** OFF, so new accounts can sign in immediately (you can turn it back on later).
The sign-in session is stored in ClickScope's local database; *Sign out* removes it.

Optional Google sign-in (needs a Google Cloud OAuth client): create a Web OAuth client with redirect URI
`https://<project-ref>.supabase.co/auth/v1/callback`, enable Supabase > Authentication > Providers > Google,
add `http://127.0.0.1:*/**` to Redirect URLs, then set `GOOGLE_ENABLED = True`.

## 4. Using ClickScope
ClickScope is a **recovery tool**. Click counting runs quietly in the background and is only used to discover
which apps you rely on. There are no productivity graphs or vanity stats.
- **Home**: how ready your PC is to recover (4 steps: scan, choose must-keep apps, back up, download
  installers), what is protected, what is worth adding, and a list of your most-used apps with a star to protect them.
- **Inventory**: your recovery list of apps and favourite websites; add by scan or by name; export a checklist.
- **Recovery**: download official installers for your list into one folder, with progress and retry.
- **Insights**: after 30 days, a few useful nudges: heavily used apps missing from your list (one-click *Add*),
  installed apps that look unused and the disk space they could free, and paid subscriptions you have not opened.
  Before day 30: a weekly check-in and early insights.
- **Account**: optional email sign-in; backs up only your recovery list.
- **Settings**: turn background counting off to save resources, start with Windows, backup/restore, ignore list,
  setup guide, tour, export, clear data.
- **Always on:** ClickScope runs quietly in the background and starts with Windows. The window's X just tucks it
  into the taskbar; click its taskbar icon to open the dashboard again. There is no Quit button. To stop counting,
  turn off *Count clicks in the background* in Settings, or use the uninstaller (it stops the app first).
- Right-click a row to stop counting an app.

## 5. Privacy
**Your click data never leaves your PC.** No keystrokes, no screenshots, nothing uploaded unless you sign in,
and then only your recovery list. Don't take our word for it: see `TRUST.md` (the tracking code has no network
code, and `python tests/test_no_network.py` proves it). MIT licensed. Details:
- Saves only daily totals per app / website / hour in `%APPDATA%\ClickScope\clickscope.db`.
- Websites are named from the browser's tab title, never the URL (the one-time browser-favourites import in the
  setup guide, if you choose it, saves domain names only).
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
src/scanner.py   installed-app + browser-favourites scan (local, one-time)
src/onboarding.py first-run guided setup
src/guide.py     the blue triangle ghost cursor (guide + tour)
src/cloud.py     email sign-in (+ optional Google) and recovery backup/restore via Supabase
src/cloud_config.py  Supabase URL + publishable key
supabase/schema.sql  tables, Row Level Security, sync function
src/recovery.py  winget-based installer downloader with progress and retry
installer/       Inno Setup script (folder-choosing installer)
src/winhook.py   Windows mouse hook + window lookup (ctypes, no dependencies)
src/core.py      local storage, labeling, suggestion rules, demo data
assets/          logo.png (transparent), app.ico, UI logos
docs/            preview screenshots
tests/           python tests/test_core.py ; tests/render.py (headless screenshots)
build.bat        builds dist\ClickScope.exe
.github/         optional cloud build (Option A)
```
Run from source: `python src\main.py` (Python 3.10+, no extra packages).
