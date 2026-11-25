"""A local list of the apps in this account's Start Menu.

Universal Search needs app names, not a Windows API. Reading Start Menu
shortcuts is quick, read-only and stays on this PC. Nothing is executed here;
opening a result is always an explicit user action.
"""
import os
import threading
import time

_CLUTTER = ("uninstall", "readme", "read me", "help", "manual", "license", "release notes",
            "website", "documentation", "changelog")


class AppIndex:
    def __init__(self):
        self.items = []
        self.lock = threading.RLock()
        self.built_at = 0.0
        self._refresh_lock = threading.Lock()

    # ------------------------------------------------------------------ build
    def start_refresh(self):
        threading.Thread(target=self.refresh, daemon=True, name="ClickScopeApps").start()

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False):
            return False
        try:
            rows, seen = [], set()
            for root, weight in self._roots():
                self._walk(root, weight, rows, seen, depth=0)
            rows.sort(key=lambda r: (r["weight"], r["name"].lower()))
            with self.lock:
                self.items = rows
                self.built_at = time.time()
            return True
        finally:
            self._refresh_lock.release()

    def refresh_if_stale(self, seconds=600):
        if time.time() - self.built_at < seconds:
            return False
        return self.refresh()

    def _roots(self):
        roots = []
        appdata = os.environ.get("APPDATA") or ""
        programdata = os.environ.get("ProgramData") or ""
        for base in (appdata, programdata):
            if base:
                roots.append((os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"), 0))
        local = os.environ.get("LOCALAPPDATA") or ""
        if local:
            # App execution aliases (winget, Terminal, Store apps) live here.
            roots.append((os.path.join(local, "Microsoft", "WindowsApps"), 1))
        return [(r, w) for r, w in roots if r and os.path.isdir(r)]

    def _walk(self, folder, weight, rows, seen, depth):
        if depth > 4:
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    self._walk(entry.path, weight, rows, seen, depth + 1)
                    continue
            except OSError:
                continue
            name = os.path.splitext(entry.name)[0].strip()
            ext = os.path.splitext(entry.name)[1].lower()
            if ext not in (".lnk", ".exe") or not name:
                continue
            low = name.lower()
            if low in seen or any(word in low for word in _CLUTTER):
                continue
            seen.add(low)
            rows.append(dict(name=name, path=entry.path, kind="app", is_dir=False,
                             weight=weight, source="Start Menu" if ext == ".lnk" else "Windows"))

    # ----------------------------------------------------------------- search
    def search(self, query, limit=4):
        q = (query or "").strip().lower()
        if not q:
            return []
        out = []
        with self.lock:
            items = list(self.items)
        for item in items:
            name = item["name"].lower()
            if name == q:
                score = 0
            elif name.startswith(q):
                score = 1
            elif q in name:
                score = 2
            else:
                words = name.replace("-", " ").replace("_", " ").split()
                if not any(w.startswith(q) for w in words):
                    continue
                score = 3
            out.append((score + item["weight"], item))
        out.sort(key=lambda pair: (pair[0], pair[1]["name"].lower()))
        return [dict(item) for _, item in out[:limit]]
