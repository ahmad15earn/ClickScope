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
"""


class Store:
    def __init__(self, path=None):
        if path is None:
            os.makedirs(APP_DIR, exist_ok=True)
            path = os.path.join(APP_DIR, "clickscope.db")
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass
        self.db.executescript(SCHEMA)
        self.db.commit()

    # --- writing
    def add_click(self, app, site=None, when=None):
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
        with self.lock:
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
            self.db.commit()

    def clear(self):
        with self.lock:
            self.db.execute("DELETE FROM clicks")
            self.db.execute("DELETE FROM hours")
            self.db.commit()

    # --- reading
    @staticmethod
    def since(rng):
        today = datetime.date.today()
        if rng == "today":
            return today.strftime("%Y-%m-%d")
        if rng == "7d":
            return (today - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
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

    def export_csv(self, path):
        with self.lock:
            rows = self.db.execute("SELECT day, kind, name, n FROM clicks ORDER BY day, kind, n DESC").fetchall()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["date", "type", "name", "clicks"])
            w.writerows(rows)


# -------------------------------------------------------------- suggestions
def build_suggestions(store, rng):
    total = store.total(rng)
    if total < 30:
        return [dict(level="info", title="Keep ClickScope running",
                     text="Suggestions appear once there are a few dozen clicks to learn from. "
                          "Use your PC as usual, then come back, or switch the range to \u201c7 days\u201d.")]
    apps = store.top("app", rng)
    sites = store.top("site", rng)
    out = []

    # 1. One app dominates
    name, n = apps[0]
    share = n / total
    if share >= 0.35 and len(apps) > 1:
        out.append(dict(level="tip", title=f"{name} is your main workspace",
                        text=f"{share:.0%} of your clicks happen here. Learning its keyboard shortcuts "
                             f"(and pinning it to the taskbar) is the quickest way to save clicks."))

    # 2. Browser-heavy
    browser = sum(c for a, c in apps if a in BROWSER_LABELS)
    if browser / total >= 0.6:
        out.append(dict(level="tip", title="Most of your clicking happens in the browser",
                        text=f"{browser / total:.0%} of clicks. Pin your top tabs, use the bookmarks bar, "
                             "and try Ctrl+L (address bar) and Ctrl+Tab (switch tabs) to click less."))

    # 3. One site dominates
    if sites:
        s_total = sum(c for _, c in sites)
        sname, sn = sites[0]
        if s_total >= 30 and sn / s_total >= 0.4:
            out.append(dict(level="tip", title=f"{sname} dominates your browsing",
                            text=f"{sn / s_total:.0%} of your website clicks. Pin it as a tab, or install it as "
                                 "an app window so it is one click away."))

    # 4. Rarely used apps
    if total >= 150:
        rare = [a for a, c in reversed(apps)
                if c <= 3 and c / total <= 0.02 and a not in SYSTEM_LABELS][:3]
        if rare:
            out.append(dict(level="info", title="Rarely used apps",
                            text=f"{', '.join(rare)} barely get any clicks. Consider unpinning or "
                                 "uninstalling them to declutter your taskbar and Start menu."))

    # 5. Many apps
    active = [a for a, c in apps if c >= 10 and a not in SYSTEM_LABELS]
    if len(active) >= 10:
        out.append(dict(level="info", title=f"You juggle {len(active)} apps",
                        text="Try virtual desktops (Win+Ctrl+D) to group apps by task, and Win+Tab to move between them."))

    # 6. Busiest hour
    ph = store.busiest_hour(rng)
    if ph is not None and total >= 100:
        out.append(dict(level="info", title=f"Your busiest hour is {fmt_hour(ph)}",
                        text="Plan demanding, click-heavy work around it, and take a short break right after."))

    # 7. Busier than usual today
    if rng == "today":
        today = datetime.date.today().strftime("%Y-%m-%d")
        daily = store.daily_totals()
        prev = [v for d, v in daily.items() if d != today]
        if len(prev) >= 3:
            avg = sum(prev) / len(prev)
            if avg > 0 and total >= avg * 1.4:
                out.append(dict(level="warn", title="Busier than usual today",
                                text=f"{total:,} clicks vs. a typical {avg:,.0f}. A good moment for a stretch break."))

    # 8. Heavy mouse use
    days = max(1, store.days_with_data(rng))
    if total / days >= 6000:
        out.append(dict(level="warn", title="Heavy mouse day",
                        text=f"About {total // days:,} clicks per day. Keyboard shortcuts and short breaks "
                             "can ease the load on your hand."))

    if not out:
        out.append(dict(level="good", title="Nothing stands out",
                        text="Your click activity looks balanced. Check back after a few more days of data."))
    return out[:5]
