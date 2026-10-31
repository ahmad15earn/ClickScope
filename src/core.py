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
CREATE TABLE IF NOT EXISTS catalog(kind TEXT, name TEXT, detail TEXT, PRIMARY KEY(kind, name));
"""


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
        self.cloud_dirty = True
        with self.lock:
            self.db.execute("DELETE FROM catalog WHERE kind=?", (kind,))
            self.db.executemany("INSERT OR REPLACE INTO catalog(kind,name,detail) VALUES(?,?,?)",
                                [(kind, n, d) for n, d in items])
            self.db.commit()

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

    def export_csv(self, path):
        with self.lock:
            rows = self.db.execute("SELECT day, kind, name, n FROM clicks ORDER BY day, kind, n DESC").fetchall()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "type", "name", "clicks"])
            w.writerows(rows)


# -------------------------------------------------------------- suggestions
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def build_suggestions(store, rng="30d"):
    """Rule-based tips from the last 30 days. Called only once the learning window is over."""
    total = store.total(rng)
    if total < 30:
        return [dict(level="info", title="Not enough activity yet",
                     text="ClickScope saw very few clicks in the last 30 days, so there is nothing "
                          "reliable to suggest. Keep it running while you work.")]
    apps = store.top("app", rng)
    sites = store.top("site", rng)
    out = []

    name, n = apps[0]
    if n / total >= 0.35 and len(apps) > 1:
        out.append(dict(level="tip", title=f"{name} is your main workspace",
                        text=f"{n / total:.0%} of your clicks happen here. Learning its keyboard shortcuts "
                             f"and pinning it to the taskbar is the quickest way to save clicks."))

    browser = sum(c for a, c in apps if a in BROWSER_LABELS)
    if browser / total >= 0.6:
        out.append(dict(level="tip", title="Most of your clicking happens in the browser",
                        text=f"{browser / total:.0%} of clicks. Pin your top tabs, use the bookmarks bar, "
                             "and try Ctrl+L (address bar) and Ctrl+Tab (switch tabs) to click less."))

    if sites:
        s_total = sum(c for _, c in sites)
        sname, sn = sites[0]
        if s_total >= 30 and sn / s_total >= 0.4:
            out.append(dict(level="tip", title=f"{sname} dominates your browsing",
                            text=f"{sn / s_total:.0%} of your website clicks. Pin it as a tab, or install it as "
                                 "an app window so it is one click away."))

    keep = set(store.kept())
    rare = [a for a, c in reversed(apps) if c <= 5 and c / total <= 0.02 and a not in SYSTEM_LABELS and a not in keep][:3]
    if rare and total >= 150:
        out.append(dict(level="info", title="Rarely used apps",
                        text=f"{', '.join(rare)} barely got any clicks in 30 days. Consider unpinning or "
                             "uninstalling them to declutter your taskbar and Start menu."))

    active = [a for a, c in apps if c >= 10 and a not in SYSTEM_LABELS]
    if len(active) >= 10:
        out.append(dict(level="info", title=f"You juggle {len(active)} apps",
                        text="Try virtual desktops (Win+Ctrl+D) to group apps by task, and Win+Tab to move between them."))

    ph = store.busiest_hour(rng)
    if ph is not None and total >= 100:
        out.append(dict(level="info", title=f"Your busiest hour is {fmt_hour(ph)}",
                        text="Plan demanding, click-heavy work around it, and take a short break right after."))

    wd = store.weekday_totals(rng)
    if sum(wd) >= 100:
        avg = sum(wd) / 7
        best = max(range(7), key=lambda i: wd[i])
        if wd[best] >= avg * 1.35:
            out.append(dict(level="info", title=f"{WEEKDAYS[best]} is your busiest day",
                            text=f"You click about {wd[best] / avg - 1:.0%} more than on an average day. "
                                 "Keep it lighter on meetings and admin if you can."))

    daily = store.daily_series(30)
    last7 = sum(v for _, v in daily[-7:])
    prev = [v for _, v in daily[:-7]]
    prev_avg7 = (sum(prev) / len(prev)) * 7 if prev else 0
    if prev_avg7 > 100:
        if last7 >= prev_avg7 * 1.25:
            out.append(dict(level="warn", title="You are clicking more lately",
                            text=f"The last 7 days are {last7 / prev_avg7 - 1:.0%} above your usual pace. "
                                 "A good moment to stretch and rest your hand."))
        elif last7 <= prev_avg7 * 0.75:
            out.append(dict(level="good", title="A calmer week",
                            text=f"The last 7 days are {1 - last7 / prev_avg7:.0%} below your usual pace."))

    quiet = [n for n, c, _ in store.keep_info() if c <= 5]
    if quiet:
        out.append(dict(level="good", title="Rarely clicked, still important",
                        text=f"{', '.join(quiet[:3])} barely get clicks, but they are in your recovery inventory, "
                             "so ClickScope will never suggest removing them. Clicks measure habit, not importance."))

    days = max(1, store.days_with_data(rng))
    if total / days >= 6000:
        out.append(dict(level="warn", title="Heavy mouse use",
                        text=f"About {total // days:,} clicks per active day. Keyboard shortcuts and short "
                             "breaks can ease the load on your hand."))

    if not out:
        out.append(dict(level="good", title="Nothing stands out",
                        text="Your click activity looks balanced over the last 30 days."))
    return out[:6]


def quick_insights(store):
    """Small early insights shown during the 30-day learning window."""
    total = store.total("all")
    if total < 50:
        return ["First insights appear after about 50 clicks. Use your PC as usual."]
    apps = store.top("app", "all")
    out = [f"{apps[0][0]} gets {apps[0][1] / total:.0%} of your clicks so far."]
    ph = store.busiest_hour("all")
    if ph is not None:
        out.append(f"Your busiest hour so far is {fmt_hour(ph)}.")
    return out


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
            ("Word", 7), ("Figma", 6), ("Terminal", 5), ("Zoom", 3), ("Spotify", 2)]
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
    store.set("first_run", (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d"))
