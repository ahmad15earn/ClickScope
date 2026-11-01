# Don't trust us. Verify.

ClickScope watches which apps you click so it can find the software you rely on. That is sensitive, so the
promise is simple and **checkable**:

**Your click data never leaves your PC.**

## What the tracker does
- Counts mouse clicks and notes which program was clicked (and, for browsers, a site name from the tab title).
- Stores only daily totals per app / site / hour in a local SQLite file: `%APPDATA%\ClickScope\clickscope.db`.
- Never records keystrokes, screenshots, cursor paths, page content or full URLs.

## What can leave your PC (only if you sign in)
Your **recovery list** only: installed-app names, apps and sites you chose to keep, and your recovery selection.
Never click counts. The code that does this is the single file `src/cloud.py`.

## Verify it yourself (2 minutes)
The tracking engine is two files and neither contains any network code:

| File | Job |
|------|-----|
| `src/winhook.py` | Windows mouse hook, finds which window was clicked |
| `src/core.py`    | Local storage and analysis |

1. Open them and search for `socket`, `urllib`, `http`, `requests`, `smtplib`: you will find none.
2. Run `python tests/test_no_network.py`. It reads the source and **fails if either file ever imports a network
   module**, so a future change cannot quietly add one.
3. Watch it live: Windows Firewall or Resource Monitor > Network shows ClickScope silent unless you press
   *Sign in* or *Sync now*.

The whole project is MIT licensed (see `LICENSE`): read it, audit it, build it yourself.
