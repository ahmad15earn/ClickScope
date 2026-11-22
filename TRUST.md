# Don't trust us. Verify.

ClickScope is a local utility. It has no account, no cloud, no telemetry and no click tracking.
The promise is simple and checkable:

**Nothing about your PC leaves your PC.**

## What ClickScope stores

All data is in `%APPDATA%\ClickScope\` (or `%CLICKSCOPE_HOME%` if you set it):

- **Search index** — file names, folder paths, sizes, dates and file kinds. Never file contents.
- **Blueprints** — folder names and, if you include it, a copy of your current wallpaper picture.
- **Settings** — a few choices such as installer age and start-with-Windows.

## What ClickScope never does

- No network requests, background uploads or crash reporting.
- No keystrokes, screenshots, cursor paths or browser history.
- No permanent deletion: old installers are moved to the Recycle Bin, and only after you confirm.
- No document copying in a blueprint: restore creates empty folders only.

## Verify it yourself

1. Search the source for `socket`, `ssl`, `urllib`, `http`, `requests`, `httpx`, `aiohttp`, `smtplib`
   or `webbrowser` — the app modules contain none.
2. Run:

   ```bat
   python tests\test_no_network.py
   ```

   It parses the app's modules and fails if a network import is ever added.

3. Run `python src\main.py --demo`, or watch Resource Monitor → Network. ClickScope stays silent.

The app is plain Python and Tkinter. Build it yourself with `build.bat` and read every line.
MIT licensed — see `LICENSE`.
