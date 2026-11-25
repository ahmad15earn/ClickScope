# ClickScope 2.0 — Feature Audit Report

Date: 25 November 2026  
Build audited: portable `dist\ClickScope.exe` (33.2 MB) and `installer_output\ClickScope-Setup.exe` (34.9 MB)  
Environment: Windows, Python 3.13.17, Tk 8.6, Pillow 13, SQLite FTS5

## How this was audited

- Ran every local engine test as a plain script.
- Ran `tests\ui_probe.py`, which builds all six pages in a real Tk window, searches the
  index, protects and unprotects a file, opens the website dialog, saves a site, changes
  search filters, runs the floating Universal Search bar, captures a new shortcut in Settings,
  toggles notification settings, creates a backup, opens and clicks through the notification
  panel, and follows `clickscope:` page targets.
- Built and smoke-started the packaged executable.
- Built the Inno Setup installer.
- Captured the shipped screenshots from a seeded synthetic PC (`C:\Users\TECH ZONE\ClickScopeShots`).
- Read the code paths for the rules that a UI probe cannot prove, then added tests where a
  rule was not covered.

## Status at a glance

| Feature | Status | Notes |
| --- | --- | --- |
| Local name index and search | Complete | Full local-drive scan, filters, Enter/Ctrl+Enter, background updates |
| File Protection | Complete | Checked before cleanup; protected items never suggested; rename re-match only when unique |
| Installer cleanup | Complete | `.exe`/`.msi`, 30-day default, version duplicates, large & old flag, safe picks, Recycle Bin |
| Blueprint | Complete | Snapshot, wallpaper, `.clickdna`, validation, missing folders only, no overwrite |
| Website Memory | Complete | Add/edit/search/categories, Firefox import, JSON export/import, duplicate detection |
| Notifications | Complete in app; Windows toast best-effort | No destructive action; click opens the related section. Manual toast click-through still unverified |
| Universal Search | Complete | One configurable global shortcut, floating bar over any app, files/folders/Start Menu apps, no keyboard hook |
| File colours | Partial by design | Colour marks in ClickScope only; Explorer has no supported per-file colour API |
| External drives | Complete | Missing roots pruned from view, reconnect adds them back |
| Settings, storage, persistence | Complete, except encrypted backup | Custom location, backup/restore data, startup, notification types, rebuild/remove index |
| Privacy | Complete | No network imports, no file content, cookies or passwords |
| Reliability | Complete | Corrupt DB rebuild with preserved bad copy, atomic JSON writes, hardened `.clickdna` import |
| Packaging | Complete | Portable EXE and Setup EXE both built; no MSI package |
| Documentation | Complete | README, TRUST, screenshots, this report |

## Feature details

### 1. Search index

Verified: first full scan of fixed and removable local drives, name search, result opening,
Explorer reveal, `name`/`location`/`size`/`date`/`type` filters, FTS fallback for short
queries, background watcher, index rebuild/removal, external-drive prune and reconnect, and
corrupt-database recovery.

Remaining: system folders, `AppData`, junctions and reparse points are intentionally skipped
so the scan cannot loop or index the operating system. This is the audit's definition of a
"whole PC" file-name index.

Tests: `tests/test_filesearch.py` (including filters, drive disconnect/reconnect and corrupt DB).

### 2. File Protection

Verified: files and folders can be protected from search, the Protection page and installer
results. Protection is consulted before duplicate matching, safe picks and deletion. If a
protected path is somehow submitted to the remover, it is blocked. A protected item is never
presented as a cleanup suggestion.

A rename is followed only when exactly one candidate matches. Files are matched by name plus
size and modified-time fingerprint; folders only by exact name. Ambiguous matches are left
alone rather than guessed.

Removing protection requires confirmation and never touches the file.

Tests: `tests/test_protection.py`, `tests/test_installers.py`.

### 3. Installer cleanup

Verified: `.exe` and `.msi` discovery, 30-day default with 3-month/1-year choices, system
installer exclusions, duplicate versions (name + version aware), "large & old" flag
(over 1 year and at least 100 MB), protected-file exclusion, ignored-file persistence,
"Select safe picks", explicit confirmation, and Recycle Bin-only removal.

Remaining: there is no permanent delete path. Files that Windows refuses to recycle are
reported as failed rather than force-deleted.

Tests: `tests/test_installers.py`.

### 4. Blueprint

Verified: folder snapshot, wallpaper save, `.clickdna` export/import, zip path-traversal and
oversized-entry rejection, version rejection, import validation before writing, missing-folder
creation only, wallpaper restore, and no overwrite of existing folders or files.

Remaining: deleting a blueprint removes ClickScope's own snapshot folder from its own data
area after confirmation. User files are not involved.

Tests: `tests/test_blueprint.py`.

### 5. Website Memory

Verified: name, URL and category storage; local search; category counts; add/edit/delete
dialogs; duplicate URL detection after normalization; JSON export/import with duplicate and
invalid-entry counts; Firefox `places.sqlite` reading from a temporary copy; and opening a
site with the Windows shell rather than a network library.

Remaining: Chromium bookmark reading exists in the engine, but the visible button is Firefox
only, which matches the requested scope. Page content, cookies and passwords are never read.

Tests: `tests/test_websites.py`.

### 6. Notifications

Verified: local history, unread badge, enable/disable, Windows toast switch, seven type
switches (index, installers, duplicates, protection, blueprint, websites, errors), history
clear, capped history, corrupt-history preservation, and click-through to the matching page.

The notification panel never deletes or moves a file. Its only actions are opening a section,
marking items read, and clearing its own history.

Remaining: the Windows toast is created through a best-effort PowerShell
`ToastNotificationManager` call with a registered `clickscope:` protocol. The code and the
protocol registration were checked, but a human still needs to click a real toast to confirm
the click-through on this PC.

Tests: `tests/test_notifications.py`, plus panel and target checks in `tests/ui_probe.py`.

### 7. File colours

Verified: ZIP, PDF, image, video and audio files have distinct tints in the search list;
folders keep the folder treatment; EXE/MSI tiles keep the app treatment rather than a document
colour. A readable colour legend sits beside the filters.

Limitation: Windows Explorer has no supported API for colouring individual files. ClickScope
does not install a shell extension and does not change file associations or default apps, so
Explorer's own icons and double-click behaviour remain untouched. The safe alternative is the
in-app colour system plus the legend.

### 8. External drives

Verified: local fixed and removable drives are discovered; a root that disappears is pruned
from the visible index; a reconnected root is added back and indexed without duplicating rows
or dropping the rest of the index. The app checks drive state on startup and every 45 seconds;
a reconnect starts a background scan of just the returning root while the current index stays
usable. Drive labels do not break the index when the drive letter is reused.

Tests: `tests/test_filesearch.py` (disconnect/reconnect with a second root preserved) and the
external-drive stand-in in `tests/ui_probe.py`.

### 9. Universal Search

Verified: a floating, always-on-top bar opens from one registered Windows shortcut (default
`Ctrl+Alt+Space`) while ClickScope is running, including when its main window is minimised. It
searches the same local file index (files and folders) and a local Start Menu app list, groups
results as apps and files/folders, and supports `Up`/`Down`, `Enter`, `Ctrl+Enter` and `Esc`.
Clicking a result opens it; nothing is deleted, moved or uploaded. The bar is positioned on the
monitor under the mouse.

The shortcut can be changed in **Settings → Universal search** with a capture dialog that requires
Ctrl, Alt or Win plus one key. Invalid combinations are rejected before saving; a combination
already owned by Windows or another app is reported, and the previous working shortcut is kept.
Choosing a shortcut temporarily releases ClickScope's registration so the current combination can
be captured. The feature can also be switched off entirely.

Privacy: the shortcut uses `RegisterHotKey` for one combination only. There is no keyboard hook,
no `GetAsyncKeyState` polling and no key logging. The app list is read from Start Menu `.lnk` files
and kept in memory; only the chosen shortcut is written to `state.json`.

Tests: `tests/test_hotkey.py` (parsing, rejection, real registration, restart, message delivery),
`tests/test_apps.py` (local Start Menu list and ranking), and the floating-bar plus shortcut-dialog
checks in `tests/ui_probe.py`.

### 10. Settings, storage and privacy

Verified: rebuild and remove index, start with Windows, keep-running choice, stored-data size
and file count, custom storage location (`location.txt` pointer, data copied, old folder left
alone, index rebuilt), reset to default, verified ZIP backup excluding the rebuildable index,
notification settings, and persistence across a fresh `State`/`Notifications` instance.

Privacy: no network imports in the app modules, no file contents, cookies or passwords;
Firefox import reads only bookmark titles and URLs from a temporary copy.

Remaining: the backup ZIP is integrity-checked but not encrypted or password-protected. If
"backup security" means encryption at rest, that part is not implemented; the current design
relies on the local Windows account and file permissions.

Tests: `tests/test_appdata.py`, `tests/test_no_network.py`.

### 11. Reliability

Verified: corrupt SQLite index is moved aside and rebuilt; the damaged file is preserved;
JSON stores use atomic replace and keep a `.bak` for protection; corrupt notification and
protection files do not crash startup; `.clickdna` imports are validated and leave no folder
behind when rejected.

Background work runs in the existing job/queue model. No new busy loop or polling of the disk
was added; the 45-second drive check is a cheap directory-existence test, and a reconnected
drive is scanned in the background only when it returns.

### 12. Packaging and documentation

Verified: `python -m PyInstaller ...` produced `dist\ClickScope.exe` and the executable starts
and exits cleanly with `--demo --smoke` (the installed 1.x app was already holding the
single-instance mutex, so the smoke run used the separate demo identity). `ISCC.exe` produced
`installer_output\ClickScope-Setup.exe`. Both artifacts include the icon/asset pack and the new
Universal Search modules.

The build script now finds Inno Setup in `Program Files`, `Program Files (x86)` and the
per-user `%LOCALAPPDATA%\Programs\Inno Setup 6` location.

`README.md`, `TRUST.md`, the GitHub workflow and the screenshots were updated for the six-page
app plus the floating Universal Search bar.

## Bugs found and fixed during this audit

1. **Toast crash.** `Toast` had a `show()` method but call sites used `app.toast(...)`. Any
   confirmation toast raised `TypeError: 'Toast' object is not callable`. Added `__call__`.
2. **Search colour legend.** Labels were anchored to the wrong edge, so the ZIP/PDF/Image/
   Video/Audio/App legend overlapped itself. Anchoring was corrected.
3. **Empty backup destination.** `backup_data("")` resolved to the current directory and tried
   to replace a folder. Empty paths and folders are now rejected, and `.zip` is appended when
   missing.
4. **Protection rename matching.** A renamed file is now re-matched by size and modified time
   when the name no longer matches, but only when the match is unique.
5. **Tests accidentally registering the protocol / showing toasts.** The UI probe now disables
   Windows toasts before any action; the user's protocol registration was restored to the
   built executable.

## Test evidence

```text
filesearch tests OK
installers tests OK
blueprint tests OK
protection tests OK
websites tests OK
notifications tests OK
appdata tests OK
hotkey tests OK
apps tests OK
no-network check OK
UI probe OK

dist\ClickScope.exe --demo --smoke      exit 0
installer_output\ClickScope-Setup.exe   built successfully
```

Screenshots: `docs/search.png`, `search-results.png`, `universal-search.png`, `protection.png`,
`websites.png`, `notifications.png`, `installers.png`, `blueprint.png`, `settings.png`,
`settings-storage.png`, `confirm.png`.

## Remaining manual check

1. Click a real Windows toast and confirm it opens the related ClickScope page. The protocol
   and target parsing are in place; only the operating-system click has not been exercised by
   an automated test.
2. Press the real `Ctrl+Alt+Space` keys on the desktop, with ClickScope minimised, and confirm the
   floating bar receives typing focus straight away. Registration, message delivery and the bar
   itself are tested; this last step checks a physical key press in the active desktop session.
3. Change the shortcut in Settings to a combination another app owns; confirm the inline error and
   that the previous shortcut still works.
