"""ClickScope core: local storage, labeling and suggestions.

Privacy by design: only aggregated counters are stored (per day / app / site and
per day / hour). No timestamps of individual clicks, no cursor positions,
no keystrokes, no screenshots.
"""
import csv
import datetime
import os
import re
import sqlite3
import sys
import threading

ANALYSIS_DAYS = 30
MIN_ACTIVE_DAYS = 7
APP_NAME = "ClickScope"
APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)


def resource_path(rel):
    """Locate bundled files both in dev and inside the PyInstaller EXE."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ----------------------------------------------------------------- labeling
BROWSERS = {
    "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox", "brave.exe": "Brave", "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi", "arc.exe": "Arc",
}
BROWSER_LABELS = set(BROWSERS.values())

SYSTEM_LABELS = {"Other / system", "Start & Taskbar menus", "File Explorer & Desktop"}

FRIENDLY = {
    **BROWSERS,
    "explorer.exe": "File Explorer & Desktop",
    "searchhost.exe": "Start & Taskbar menus",
    "startmenuexperiencehost.exe": "Start & Taskbar menus",
    "shellexperiencehost.exe": "Start & Taskbar menus",
    "code.exe": "VS Code", "winword.exe": "Word", "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint", "outlook.exe": "Outlook", "onenote.exe": "OneNote",
    "teams.exe": "Microsoft Teams", "ms-teams.exe": "Microsoft Teams",
    "slack.exe": "Slack", "discord.exe": "Discord", "telegram.exe": "Telegram",
    "whatsapp.exe": "WhatsApp", "spotify.exe": "Spotify", "notepad.exe": "Notepad",
    "notepad++.exe": "Notepad++", "windowsterminal.exe": "Terminal",
    "cmd.exe": "Command Prompt", "powershell.exe": "PowerShell",
    "photoshop.exe": "Photoshop", "figma.exe": "Figma", "notion.exe": "Notion",
    "zoom.exe": "Zoom", "obs64.exe": "OBS Studio", "vlc.exe": "VLC",
    "steam.exe": "Steam", "taskmgr.exe": "Task Manager", "mspaint.exe": "Paint",
    "claude.exe": "Claude", "python.exe": "Python", "pythonw.exe": "Python",
}


def app_label(exe, title=""):
    e = (exe or "").lower()
    if not e:
        return "Other / system"
    if e == "applicationframehost.exe":  # Store/UWP apps (Calculator, Settings...)
        return (title or "").strip()[:40] or "Windows app"
    if e in FRIENDLY:
        return FRIENDLY[e]
    base = e[:-4] if e.endswith(".exe") else e
    base = re.sub(r"[-_.]+", " ", base).strip()
    return base.title() or "Other / system"


KNOWN_SITES = [
    ("youtube", "YouTube"), ("gmail", "Gmail"), ("facebook", "Facebook"),
    ("messenger", "Messenger"), ("whatsapp", "WhatsApp Web"), ("instagram", "Instagram"),
    ("linkedin", "LinkedIn"), ("github", "GitHub"), ("reddit", "Reddit"),
    ("twitter", "X (Twitter)"), ("chatgpt", "ChatGPT"), ("claude", "Claude"),
    ("notion", "Notion"), ("figma", "Figma"), ("canva", "Canva"),
    ("netflix", "Netflix"), ("amazon", "Amazon"), ("wikipedia", "Wikipedia"),
    ("google docs", "Google Docs"), ("google sheets", "Google Sheets"),
    ("google slides", "Google Slides"), ("google drive", "Google Drive"),
    ("google meet", "Google Meet"), ("google calendar", "Google Calendar"),
    ("google search", "Google Search"), ("outlook", "Outlook Web"),
    ("telegram", "Telegram Web"), ("spotify", "Spotify Web"),
    ("vercel", "Vercel"), ("supabase", "Supabase"), ("stack overflow", "Stack Overflow"),
]

_BROWSER_SUFFIX = re.compile(
    r"\s[-\u2013\u2014]\s(Google Chrome|Chromium|Microsoft.{0,2}Edge|Mozilla Firefox|"
    r"Firefox|Brave|Opera|Vivaldi|Arc)(\s[-\u2013\u2014]\s.+)?$", re.I)
_SPLIT = re.compile(r"\s[-\u2013\u2014|\u00b7\u2022]\s|\s/\s")


def site_label(title):
    """Turn a browser window title into a short site name (never a full URL)."""
    t = (title or "").strip()
    t = _BROWSER_SUFFIX.sub("", t).strip()
    t = re.sub(r"^\(\d+\)\s*", "", t)  # "(3) Facebook" -> "Facebook"
    if not t:
        return None
    parts = [p.strip() for p in _SPLIT.split(t) if p.strip()]
    name = parts[-1] if parts else t
    low = name.lower()
    if low == "x":
        return "X (Twitter)"
    for kw, pretty in KNOWN_SITES:
        if kw in low:
            return pretty
    return name[:40]


def fmt_hour(h):
    if h is None:
        return "\u2013"
    return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"


# ------------------------------------------------------------------ storage
SCHEMA = """
CREATE TABLE IF NOT EXISTS clicks(day TEXT, kind TEXT, name TEXT, n INTEGER,
    PRIMARY KEY(day, kind, name));
CREATE TABLE IF NOT EXISTS hours(day TEXT, hour INTEGER, n INTEGER,
    PRIMARY KEY(day, hour));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS catalog(kind TEXT, name TEXT, detail TEXT, size_mb INTEGER DEFAULT 0, PRIMARY KEY(kind, name));
"""


SUBSCRIPTION_HINTS = ["adobe", "creative cloud", "microsoft 365", "office 365", "canva", "figma", "grammarly",
                      "dropbox", "spotify", "evernote", "nordvpn", "expressvpn", "surfshark", "1password",
                      "lastpass", "dashlane", "jetbrains", "pycharm", "intellij", "webstorm", "notion", "camtasia",
                      "filmora", "wondershare", "autodesk", "sketch", "zoom workplace", "slack"]
ALIASES = {"vscode": ["visualstudiocode"], "word": ["microsoftword", "microsoft365", "office"],
           "excel": ["microsoftexcel", "microsoft365", "office"], "powerpoint": ["microsoftpowerpoint", "microsoft365", "office"],
           "googlechrome": ["chrome"], "microsoftedge": ["edge"], "terminal": ["windowsterminal"]}
SYSTEM_HINTS = ["windows", "microsoft edge", "onedrive", "driver", "nvidia", "intel", "realtek", "amd ", "bluetooth", "touchpad"]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def same_app(label, name):
    """Does a tracked window label (e.g. 'VS Code') belong to this installed app (e.g. 'Visual Studio Code')?"""
    a, b = _norm(label), _norm(name)
    if not a or not b:
        return False
    if a == b or (len(a) >= 4 and (a in b or b in a)):
        return True
    return any(al in b for al in ALIASES.get(a, []))


def is_system_app(name):
    low = name.lower()
    return any(h in low for h in SYSTEM_HINTS)


class Store:
    def __init__(self, path=None):
        if path is None:
            os.makedirs(APP_DIR, exist_ok=True)
            path = os.path.join(APP_DIR, "clickscope.db")
        self.path = path
        self.cloud_dirty = False
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self.db.executescript(SCHEMA)
        try:  # databases created by older versions
            self.db.execute("ALTER TABLE catalog ADD COLUMN size_mb INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        self.db.commit()

    # --- writing
    # --- ignore list (apps / websites the user does not want counted)
    def ignored(self):
        import json
        try:
            return set(json.loads(self.get("ignored", "[]")))
        except ValueError:
            return set()

    def add_ignore(self, kind, name):
        import json
        s = self.ignored()
        s.add(f"{kind}:{name.lower()}")
        self.set("ignored", json.dumps(sorted(s)))
        with self.lock:  # also forget what was already counted for it
            self.db.execute("DELETE FROM clicks WHERE kind=? AND lower(name)=?", (kind, name.lower()))
            self.db.commit()

    def clear_ignored(self):
        self.set("ignored", "[]")

    # --- recovery inventory: apps the user marked as must-keep (clicks do not measure importance)
    def kept(self):
        import json
        try:
            return list(json.loads(self.get("kept", "[]")))
        except ValueError:
            return []

    def toggle_keep(self, name):
        import json
        k = self.kept()
        now = name not in k
        if now:
            k.append(name)
        else:
            k.remove(name)
        self.set("kept", json.dumps(k))
        return now

    # --- full scanned catalog (everything installed / favourite sites), kept for recovery
    def set_catalog(self, kind, items):
        """items: (name, detail) or (name, detail, size_mb). Existing sizes are kept for 2-tuples."""
        self.cloud_dirty = True
        old = self.catalog_sizes(kind)
        rows = [(kind, it[0], it[1], int(it[2]) if len(it) > 2 else old.get(it[0], 0)) for it in items]
        with self.lock:
            self.db.execute("DELETE FROM catalog WHERE kind=?", (kind,))
            self.db.executemany("INSERT OR REPLACE INTO catalog(kind,name,detail,size_mb) VALUES(?,?,?,?)", rows)
            self.db.commit()

    def catalog_sizes(self, kind="app"):
        with self.lock:
            return dict(self.db.execute("SELECT name, COALESCE(size_mb,0) FROM catalog WHERE kind=?", (kind,)).fetchall())

    def catalog(self, kind):
        with self.lock:
            return self.db.execute("SELECT name, detail FROM catalog WHERE kind=? ORDER BY lower(name)", (kind,)).fetchall()

    def kept_sites(self):
        import json
        try:
            return list(json.loads(self.get("kept_sites", "[]")))
        except ValueError:
            return []

    def toggle_keep_site(self, name, force=None):
        import json
        k = self.kept_sites()
        now = (name not in k) if force is None else force
        if now and name not in k:
            k.append(name)
        elif not now and name in k:
            k.remove(name)
        self.set("kept_sites", json.dumps(k))
        return now

    def set_keep(self, name, on=True):
        if (name in self.kept()) != on:
            self.toggle_keep(name)

    def keep_sites_info(self):
        det = dict(self.catalog("site"))
        return [(n, det.get(n, "added manually")) for n in self.kept_sites()]

    def reset_first_run(self):
        self.set("first_run", datetime.date.today().strftime("%Y-%m-%d"))

    def keep_info(self):
        """[(name, total_clicks, last_day_or_None)] for every kept app."""
        out = []
        with self.lock:
            for name in self.kept():
                r = self.db.execute("SELECT COALESCE(SUM(n),0), MAX(day) FROM clicks WHERE kind='app' AND lower(name)=?",
                                    (name.lower(),)).fetchone()
                out.append((name, int(r[0]), datetime.date.fromisoformat(r[1]) if r[1] else None))
        return out

    def export_inventory(self, path):
        info = self.keep_info()
        kept = {n.lower() for n, _, _ in info}
        lines = [f"ClickScope recovery checklist  -  {datetime.date.today():%Y-%m-%d}", "",
                 "Reinstall these first (you marked them as must-keep):", ""]
        for name, n, last in info:
            seen = f"last clicked {last:%Y-%m-%d}" if last else "not seen yet (added manually)"
            lines.append(f"[ ] {name}  ({n:,} clicks, {seen})")
        if not info:
            lines.append("(nothing marked yet)")
        sites = self.keep_sites_info()
        if sites:
            lines += ["", "Favourite websites to open again:", ""] + [f"[ ] {n}  ({d})" for n, d in sites]
        more = [(a, n) for a, n in self.top("app", "all", 15) if a.lower() not in kept and a not in SYSTEM_LABELS]
        if more:
            lines += ["", "Also used a lot:", ""] + [f"[ ] {a}  ({n:,} clicks)" for a, n in more]
        rest = [(a, d) for a, d in self.catalog("app") if a.lower() not in kept]
        if rest:
            lines += ["", f"Everything else that was installed ({len(rest)}):", ""] + [f"- {a}" + (f"  ({d})" if d else "") for a, d in rest]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # --- backup / restore (e.g. before reinstalling Windows or moving to a new PC)
    def backup_to(self, path):
        dst = sqlite3.connect(path)
        with self.lock:
            self.db.backup(dst)
        dst.close()

    def restore_from(self, path):
        src = sqlite3.connect(path)
        with self.lock:
            src.backup(self.db)
            self.db.executescript(SCHEMA)
            self.db.commit()
        src.close()

    def add_click(self, app, site=None, when=None):
        ign = self.ignored()
        if f"app:{app.lower()}" in ign:
            return
        if site and f"site:{site.lower()}" in ign:
            site = None
        when = when or datetime.datetime.now()
        day = when.strftime("%Y-%m-%d")
        up = ("INSERT INTO clicks(day,kind,name,n) VALUES(?,?,?,1) "
              "ON CONFLICT(day,kind,name) DO UPDATE SET n=n+1")
        with self.lock:
            self.db.execute(up, (day, "app", app))
            if site:
                self.db.execute(up, (day, "site", site))
            self.db.execute(
                "INSERT INTO hours(day,hour,n) VALUES(?,?,1) "
                "ON CONFLICT(day,hour) DO UPDATE SET n=n+1", (day, when.hour))
            self.db.commit()

    def get(self, key, default=None):
        with self.lock:
            r = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def set(self, key, value):
        if key in ("kept", "kept_sites", "recovery_apps", "winget_ids"):
            self.cloud_dirty = True
        with self.lock:
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
            self.db.commit()

    def clear(self):
        with self.lock:
            self.db.execute("DELETE FROM clicks")
            self.db.execute("DELETE FROM hours")
            self.db.execute("DELETE FROM settings WHERE key='first_run'")
            self.db.commit()

    # --- reading
    @staticmethod
    def since(rng):
        today = datetime.date.today()
        if rng == "today":
            return today.strftime("%Y-%m-%d")
        if rng == "7d":
            return (today - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
        if rng == "30d":
            return (today - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
        return "0000-00-00"

    def total(self, rng):
        with self.lock:
            r = self.db.execute("SELECT COALESCE(SUM(n),0) FROM clicks WHERE kind='app' AND day>=?",
                                (self.since(rng),)).fetchone()
        return r[0]

    def count(self, kind, rng):
        with self.lock:
            r = self.db.execute("SELECT COUNT(DISTINCT name) FROM clicks WHERE kind=? AND day>=?",
                                (kind, self.since(rng))).fetchone()
        return r[0]

    def top(self, kind, rng, limit=None, desc=True):
        q = ("SELECT name, SUM(n) s FROM clicks WHERE kind=? AND day>=? GROUP BY name "
             f"ORDER BY s {'DESC' if desc else 'ASC'}, name")
        args = [kind, self.since(rng)]
        if limit:
            q += " LIMIT ?"
            args.append(limit)
        with self.lock:
            return [(n, int(s)) for n, s in self.db.execute(q, args).fetchall()]

    def hours(self, rng):
        out = [0] * 24
        with self.lock:
            for h, s in self.db.execute("SELECT hour, SUM(n) FROM hours WHERE day>=? GROUP BY hour",
                                        (self.since(rng),)):
                out[h] = int(s)
        return out

    def busiest_hour(self, rng):
        hrs = self.hours(rng)
        return hrs.index(max(hrs)) if max(hrs) > 0 else None

    def daily_totals(self):
        with self.lock:
            return {d: int(s) for d, s in self.db.execute(
                "SELECT day, SUM(n) FROM clicks WHERE kind='app' GROUP BY day")}

    def days_with_data(self, rng):
        with self.lock:
            return self.db.execute("SELECT COUNT(DISTINCT day) FROM clicks WHERE day>=?",
                                   (self.since(rng),)).fetchone()[0]

    def total_between(self, d1, d2):
        with self.lock:
            return self.db.execute(
                "SELECT COALESCE(SUM(n),0) FROM clicks WHERE kind='app' AND day>=? AND day<=?",
                (d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d"))).fetchone()[0]

    def daily_series(self, n):
        """[(date, total)] for the last n days, oldest first, zeros included."""
        daily = self.daily_totals()
        today = datetime.date.today()
        out = []
        for i in range(n - 1, -1, -1):
            d = today - datetime.timedelta(days=i)
            out.append((d, daily.get(d.strftime("%Y-%m-%d"), 0)))
        return out

    def weekday_totals(self, rng):
        """Clicks per weekday, Monday first."""
        out = [0] * 7
        with self.lock:
            for w, s in self.db.execute(
                    "SELECT strftime('%w', day), SUM(n) FROM clicks WHERE kind='app' AND day>=? GROUP BY 1",
                    (self.since(rng),)):
                out[(int(w) - 1) % 7] = int(s)
        return out

    def first_data_day(self):
        with self.lock:
            r = self.db.execute("SELECT MIN(day) FROM clicks").fetchone()[0]
        return datetime.date.fromisoformat(r) if r else None

    # --- the 30-day learning window
    def first_run(self):
        v = self.get("first_run")
        if not v:
            v = datetime.date.today().strftime("%Y-%m-%d")
            self.set("first_run", v)
        return datetime.date.fromisoformat(v)

    def active_days(self):
        """Days with a meaningful amount of activity (>= 20 clicks)."""
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM (SELECT day FROM clicks WHERE kind='app' "
                                   "GROUP BY day HAVING SUM(n) >= 20)").fetchone()[0]

    def analysis_progress(self):
        """(day_number 1..30, ready, unlock_date).
        Suggestions unlock after 30 days AND at least MIN_ACTIVE_DAYS days of real activity,
        so a PC that was mostly switched off does not produce suggestions from thin data."""
        first = self.first_run()
        elapsed = (datetime.date.today() - first).days
        ready = elapsed >= ANALYSIS_DAYS and self.active_days() >= MIN_ACTIVE_DAYS
        return (min(ANALYSIS_DAYS, elapsed + 1), ready, first + datetime.timedelta(days=ANALYSIS_DAYS))

    # --- recovery-centred analysis (clicks are only a discovery tool)
    def tracked_days(self):
        return (datetime.date.today() - self.first_run()).days + 1

    def _last_days(self):
        with self.lock:
            return {n: d for n, d in self.db.execute("SELECT name, MAX(day) FROM clicks WHERE kind='app' GROUP BY name")}

    def last_used(self, name, last_days=None):
        """Most recent day a tracked app label matches this installed app's name (or None)."""
        last_days = last_days if last_days is not None else self._last_days()
        best = None
        for label, day in last_days.items():
            if same_app(label, name) and (best is None or day > best):
                best = day
        return datetime.date.fromisoformat(best) if best else None

    def frequent_unprotected(self, limit=5, rng="30d"):
        kept = self.kept()
        return [(a, n) for a, n in self.top("app", rng)
                if not any(same_app(a, k) for k in kept) and a not in SYSTEM_LABELS and n >= 20][:limit]

    def unused_apps(self, days=30):
        """Installed apps (not in the recovery list) with no clicks for `days` days: [(name, size_mb, last_date)]."""
        if self.tracked_days() < days:
            return []
        kept = {k.lower() for k in self.kept()}
        sizes, ld = self.catalog_sizes("app"), self._last_days()
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        out = []
        for name, _ in self.catalog("app"):
            if name.lower() in kept or is_system_app(name):
                continue
            last = self.last_used(name, ld)
            if last is None or last < cutoff:
                out.append((name, sizes.get(name, 0), last))
        return sorted(out, key=lambda t: -t[1])

    def subscription_alerts(self, days=30):
        """Installed apps that are usually paid subscriptions and have not been opened for `days` days."""
        if self.tracked_days() < days:
            return []
        ld = self._last_days()
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        out = []
        for name, _ in self.catalog("app"):
            if any(h in name.lower() for h in SUBSCRIPTION_HINTS):
                last = self.last_used(name, ld)
                if last is None or last < cutoff:
                    out.append((name, (datetime.date.today() - last).days if last else None))
        return out

    def export_csv(self, path):
        with self.lock:
            rows = self.db.execute("SELECT day, kind, name, n FROM clicks ORDER BY day, kind, n DESC").fetchall()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "type", "name", "clicks"])
            w.writerows(rows)


# -------------------------------------------------------------- suggestions
def build_suggestions(store, rng="30d"):
    """Recovery-centred insights. Clicks are only used to discover what matters; there are no vanity stats.
    Each item may carry an 'action' the UI turns into a button."""
    out = []
    for name, n in store.frequent_unprotected(2, rng):
        out.append(dict(level="tip", title=f"{name} isn't in your recovery list",
                        text=f"You use it a lot ({n:,} clicks in 30 days). If your PC failed you would want it back first. "
                             "Add it to your list?",
                        action={"label": "Add to recovery list", "kind": "keep", "name": name}))

    unused = store.unused_apps(30)
    if unused:
        mb = sum(s for _, s, _ in unused)
        names = ", ".join(n for n, _, _ in unused[:3]) + (f" and {len(unused) - 3} more" if len(unused) > 3 else "")
        size = f" Removing them could free about {mb / 1024:.1f} GB." if mb >= 200 else ""
        out.append(dict(level="info", title=f"{len(unused)} installed apps look unused",
                        text=f"ClickScope has not seen {names} opened in the last 30 days.{size} "
                             "Matching is by name, so double-check before you uninstall."))

    subs = store.subscription_alerts(30)
    if subs:
        names = ", ".join(n for n, _ in subs[:3]) + (f" and {len(subs) - 3} more" if len(subs) > 3 else "")
        out.append(dict(level="warn", title=f"Still paying for {subs[0][0]}?" if len(subs) == 1 else f"Still paying for {len(subs)} subscriptions?",
                        text=f"Not opened in the last 30 days: {names}. If any of these are paid plans, cancelling could "
                             "save you money. Keep only what you still use."))

    quiet = [n for n, c, _ in store.keep_info() if c <= 5]
    if quiet:
        out.append(dict(level="good", title="Rarely clicked, still protected",
                        text=f"{', '.join(quiet[:3])} barely get clicks, but they are in your recovery list, so "
                             "ClickScope will never suggest removing them. Clicks measure habit, not importance."))
    if not out:
        out.append(dict(level="good", title="Your recovery list looks healthy",
                        text="The apps you use most are protected and nothing looks unused. Check back next month."))
    return out[:5]


def quick_insights(store):
    """Small early insights shown during the 30-day learning window (recovery-centred)."""
    apps = store.catalog("app")
    total = store.total("all")
    out = []
    if apps:
        out.append(f"{len(apps)} apps found on this PC, {len(store.kept())} in your recovery list.")
    if total < 50:
        out.append("As you work, ClickScope spots the apps you rely on. First results appear after about 50 clicks.")
        return out[:2]
    fu = store.frequent_unprotected(5, "all")
    if fu:
        out.append(f"{len(fu)} apps you use often aren't protected yet, such as {fu[0][0]}.")
    else:
        out.append("Everything you use often is already in your recovery list.")
    return out[:2]


def weekly_apps(store):
    """Apps used regularly (10+ clicks) in the last 7 days, for the weekly check-in."""
    return [a for a, n in store.top("app", "7d") if n >= 10 and a not in SYSTEM_LABELS][:8]


# ---------------------------------------------------------------- demo data
def seed_demo(store):
    """Fill a throw-away database with 30 days of plausible activity (used by --demo)."""
    import random
    rnd = random.Random(7)
    store.clear()
    today = datetime.date.today()
    now = datetime.datetime.now()
    apps = [("Google Chrome", 62), ("VS Code", 22), ("Slack", 9), ("File Explorer & Desktop", 8),
            ("Word", 7), ("Figma", 12), ("Terminal", 5), ("Spotify", 2), ("Git", 1)]
    sites = [("YouTube", 46), ("Gmail", 18), ("GitHub", 14), ("ChatGPT", 12), ("Facebook", 8),
             ("Google Docs", 6), ("Reddit", 4), ("Wikipedia", 3)]
    hour_w = [0, 0, 0, 0, 0, 0, 1, 3, 7, 10, 11, 9, 5, 7, 10, 11, 10, 8, 5, 4, 5, 4, 2, 1]
    with store.lock:
        for back in range(30, -1, -1):
            d = today - datetime.timedelta(days=back)
            day = d.strftime("%Y-%m-%d")
            base = 1900 if d.weekday() < 5 else 800
            total = base * rnd.uniform(0.7, 1.3) * (1 + (30 - back) * 0.004) * (1.4 if back <= 6 else 1)
            hw = list(hour_w)
            if back == 0:
                hw = [w if h <= max(now.hour, 9) else 0 for h, w in enumerate(hw)]
                total *= 0.5
            hs = sum(hw)
            hour_counts = [int(total * w / hs * rnd.uniform(0.85, 1.15)) for w in hw]
            day_total = sum(hour_counts)
            for h, n in enumerate(hour_counts):
                if n:
                    store.db.execute("INSERT INTO hours(day,hour,n) VALUES(?,?,?)", (day, h, n))
            raw = [w * rnd.uniform(0.75, 1.25) for _, w in apps]
            chrome = 0
            for (name, _), r in zip(apps, raw):
                n = int(day_total * r / sum(raw))
                if n:
                    store.db.execute("INSERT INTO clicks(day,kind,name,n) VALUES(?,?,?,?)", (day, "app", name, n))
                if name == "Google Chrome":
                    chrome = n
            sraw = [w * rnd.uniform(0.7, 1.3) for _, w in sites]
            for (name, _), r in zip(sites, sraw):
                n = int(chrome * 0.9 * r / sum(sraw))
                if n:
                    store.db.execute("INSERT INTO clicks(day,kind,name,n) VALUES(?,?,?,?)", (day, "site", name, n))
        for name, n in (("Paint", 3), ("Calculator", 5), ("Notepad", 4)):  # rarely used apps
            store.db.execute("INSERT INTO clicks(day,kind,name,n) VALUES(?,?,?,?)",
                             ((today - datetime.timedelta(days=9)).strftime("%Y-%m-%d"), "app", name, n))
        store.db.commit()
    store.set_catalog("app", [
        ("Google Chrome", "Google LLC  \u00b7  v126.0", 600), ("Visual Studio Code", "Microsoft  \u00b7  v1.94", 420),
        ("Slack", "Slack Technologies", 380), ("Figma", "Figma, Inc.", 310), ("Zoom Workplace", "Zoom Video", 450),
        ("Spotify", "Spotify AB", 350), ("7-Zip", "Igor Pavlov  \u00b7  v23.01", 5), ("Git", "Git Community  \u00b7  v2.46", 330),
        ("Adobe Creative Cloud", "Adobe Inc.", 1700), ("Adobe Premiere Pro 2025", "Adobe Inc.", 8400),
        ("Cyberpunk 2077", "CD PROJEKT RED", 62000), ("Backup Tool Pro", "Acme  \u00b7  v4.1", 90),
        ("VLC media player", "VideoLAN", 160), ("OBS Studio", "OBS Project", 280), ("Notion", "Notion Labs", 240)])
    for n in ("Visual Studio Code", "Backup Tool Pro"):
        store.set_keep(n, True)
    store.set_catalog("site", [("github.com", "301 visits"), ("youtube.com", "412 visits"), ("mail.google.com", "250 visits")])
    store.toggle_keep_site("github.com")
    store.set("first_run", (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
