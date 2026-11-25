# Don't trust us. Verify.

ClickScope is a local utility. It has no account, no cloud, no telemetry and no click tracking.
The promise is simple and checkable:

**Nothing about your PC leaves your PC.**

## What ClickScope stores

All data is in `%APPDATA%\ClickScope\` (or `%CLICKSCOPE_HOME%`, or a folder you choose in Settings):

- **Search index** — file names, folder paths, sizes, dates and file kinds. Never file contents.
- **Protection** — the names, locations and size/date fingerprints of files and folders you mark.
- **Website memory** — only the name, address and category of sites you add or import.
- **Notifications** — a short local history and which types you want to see.
- **Blueprints** — folder names and, if you include it, a copy of your current wallpaper picture.
- **Settings** — a few choices such as installer age, startup, notification types and storage location.
- **Universal Search** — the one shortcut you choose, in `state.json`. The Start Menu app list is read
  at launch and kept in memory only.

## What ClickScope never does

- No network requests, background uploads or crash reporting.
- No keystrokes, screenshots, cursor paths or browsing activity. The global shortcut asks Windows about
  one exact combination; there is no keyboard hook, no `GetAsyncKeyState` polling and no key logging.
- No file contents, documents, cookies or passwords, even during a Firefox import — only bookmark
  titles and addresses are read, from a temporary copy. Universal Search reads Start Menu shortcut
  names only; it never launches anything without your `Enter` or click.
- No permanent deletion: old installers are moved to the Recycle Bin, and only after you confirm.
- No document copying in a blueprint: restore creates empty folders only and never overwrites files.
- No Explorer shell extension and no change to file associations or default apps. File colours are
  shown inside ClickScope only.
- No automatic cleanup and no automatic choice made from age or size alone.

## Verify it yourself

1. Search the source for `socket`, `ssl`, `urllib`, `http`, `requests`, `httpx`, `aiohttp`, `smtplib`
   or `webbrowser` — the app modules contain none.
2. Run:

   ```bat
   python tests\test_no_network.py
   ```

   It parses the app's modules and fails if a network import is ever added.

3. Open a protection, website or notification data file after using each feature. They are readable
   JSON and contain no document text.
4. Run `python tests\test_hotkey.py` and `python tests\test_apps.py` to check shortcut parsing,
   registration and the Start Menu list without touching your own shortcuts.
5. Run `python src\main.py --demo`, or watch Resource Monitor → Network. ClickScope stays silent.

The app is plain Python and Tkinter. Build it yourself with `build.bat` and read every line.
MIT licensed — see `LICENSE`.
