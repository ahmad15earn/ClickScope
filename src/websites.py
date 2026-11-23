"""Website Memory: the addresses worth keeping, stored only on this PC.

Nothing is read from a browser except the bookmarks the user already saved, and
the browser database is copied to a temporary folder before reading so a running
Firefox is never touched or locked. ClickScope never opens cookies, passwords,
history or login information.
"""
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

from appdata import APP_DIR, human_date

WEBSITES_PATH = os.path.join(APP_DIR, "websites.json")
FORMAT = "clickscope-websites"
VERSION = 1
CATEGORIES = ("Work", "Study", "Tools", "Reading", "Fun", "Other")
DEFAULT_CATEGORY = "Other"


def _clean(text, limit=200):
    return " ".join(str(text or "").split())[:limit]


def normalize_url(url):
    """A stable key for duplicate detection (host case and trailing slash ignored)."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    scheme = (parts.scheme or "https").lower()
    if scheme not in ("http", "https"):
        return ""
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    try:
        port = parts.port
    except ValueError:
        return ""
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = parts.query
    return urlunsplit((scheme, host, path, query, ""))


def valid_url(url):
    return bool(normalize_url(url))


def display_url(url):
    raw = (url or "").strip()
    if "://" not in raw and raw:
        raw = "https://" + raw
    return raw


def _host(url):
    try:
        return (urlsplit(display_url(url)).hostname or "").replace("www.", "")
    except ValueError:
        return ""


def _item(raw, now=None):
    if not isinstance(raw, dict):
        return None
    url = display_url(raw.get("url"))
    if not valid_url(url):
        return None
    name = _clean(raw.get("name") or raw.get("title")) or _host(url) or url
    category = _clean(raw.get("category"), 32)
    if category.lower() in ("bookmarks menu", "bookmarks toolbar", "unfiled bookmarks", "mobile bookmarks"):
        category = "Bookmarks"
    category = category or DEFAULT_CATEGORY
    try:
        added = int(raw.get("added") or 0)
    except (TypeError, ValueError):
        added = 0
    if added > 10_000_000_000:  # Firefox's microseconds
        added //= 1_000_000
    added = added or int(now or time.time())
    return dict(id=str(raw.get("id") or ("w-" + uuid.uuid4().hex[:10])), name=name,
                url=url, category=category, added=added,
                updated=int(raw.get("updated") or added),
                note=_clean(raw.get("note"), 300))


class WebsiteMemory:
    """Thread-safe website list with search, JSON transfer and Firefox import."""

    def __init__(self, path=None):
        self.path = path or WEBSITES_PATH
        self.items = []
        self.recovered = False
        self._load()

    # ------------------------------------------------------------------ disk
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError):
            self.recovered = True
            try:
                if os.path.isfile(self.path):
                    os.replace(self.path, self.path + ".corrupt-%d" % int(time.time()))
            except OSError:
                pass
            data = {}
        raw = data.get("items") if isinstance(data, dict) else data
        seen = set()
        if isinstance(raw, list):
            for entry in raw:
                item = _item(entry)
                if not item:
                    continue
                key = normalize_url(item["url"])
                if key and key not in seen:
                    seen.add(key)
                    self.items.append(item)

    def _write(self):
        data = dict(format=FORMAT, version=VERSION, updated=int(time.time()),
                    items=sorted(self.items, key=lambda i: (-int(i.get("added") or 0),
                                                            i["name"].lower())))
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.isfile(self.path):
                try:
                    shutil.copy2(self.path, self.path + ".bak")
                except OSError:
                    pass
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    # ----------------------------------------------------------------- access
    def all(self):
        return [dict(i) for i in sorted(self.items, key=lambda i: i["name"].lower())]

    def find_url(self, url):
        key = normalize_url(url)
        if not key:
            return None
        for item in self.items:
            if normalize_url(item["url"]) == key:
                return dict(item)
        return None

    def add(self, name, url, category=DEFAULT_CATEGORY):
        url = display_url(url)
        if not valid_url(url):
            raise ValueError("That doesn't look like a website address.")
        existing = self.find_url(url)
        if existing:
            return None, existing
        now = int(time.time())
        item = _item(dict(name=name, url=url, category=category, added=now, updated=now))
        self.items.append(item)
        self._write()
        return dict(item), None

    def update(self, item_id, name=None, url=None, category=None, note=None):
        for item in self.items:
            if item["id"] != item_id:
                continue
            new_url = display_url(url if url is not None else item["url"])
            if not valid_url(new_url):
                raise ValueError("That doesn't look like a website address.")
            other = self.find_url(new_url)
            if other and other["id"] != item_id:
                raise ValueError(f"Already saved as \u201c{other['name']}\u201d.")
            item["name"] = _clean(name if name is not None else item["name"]) or _host(new_url)
            item["url"] = new_url
            item["category"] = _clean(category, 32) if category is not None else item["category"]
            if note is not None:
                item["note"] = _clean(note, 300)
            item["updated"] = int(time.time())
            self._write()
            return dict(item)
        raise ValueError("That website is no longer in the list.")

    def delete(self, item_id):
        before = len(self.items)
        self.items = [i for i in self.items if i["id"] != item_id]
        if len(self.items) != before:
            self._write()
            return True
        return False

    def search(self, query="", category=None):
        q = _clean(query, 80).lower()
        tokens = [t for t in q.split() if t]
        out = []
        for item in self.all():
            if category and category not in ("All", "all") and item["category"] != category:
                continue
            hay = f"{item['name']} {item['url']} {item['category']} {item.get('note', '')}".lower()
            if tokens and not all(t in hay for t in tokens):
                continue
            out.append(item)
        return out

    def categories(self):
        counts = {}
        for item in self.items:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        out = [("All", "All", len(self.items))]
        for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            out.append((name, name, n))
        return out

    # -------------------------------------------------------------- transfer
    def export_json(self, path):
        data = dict(format=FORMAT, version=VERSION, exported=human_date(),
                    items=sorted(self.items, key=lambda i: i["name"].lower()))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return len(self.items)

    def import_json(self, path):
        if os.path.getsize(path) > 10 * 1024 * 1024:
            raise ValueError("That file is too large to be a ClickScope website list.")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if data.get("format") not in (None, FORMAT):
                raise ValueError("This file isn't a ClickScope website list.")
            items = data.get("items")
        else:
            items = data
        if not isinstance(items, list):
            raise ValueError("This file doesn't contain a website list.")
        return self._merge(items, source="import")

    def _merge(self, raw_items, source=""):
        added = skipped = invalid = 0
        seen = {normalize_url(i["url"]) for i in self.items}
        now = int(time.time())
        for raw in raw_items:
            item = _item(raw, now)
            if not item:
                invalid += 1
                continue
            key = normalize_url(item["url"])
            if not key or key in seen:
                skipped += 1
                continue
            seen.add(key)
            item["note"] = item.get("note") or (f"Imported from {source}" if source else "")
            self.items.append(item)
            added += 1
        if added:
            self._write()
        return dict(added=added, skipped=skipped, invalid=invalid, total=len(raw_items))

    # --------------------------------------------------------------- Firefox
    @staticmethod
    def firefox_profiles():
        """places.sqlite files from every Firefox profile on this account."""
        appdata = os.environ.get("APPDATA") or ""
        local = os.environ.get("LOCALAPPDATA") or ""
        roots = [os.path.join(appdata, "Mozilla", "Firefox", "Profiles"),
                 os.path.join(local, "Mozilla", "Firefox", "Profiles")]
        found = []
        for base in roots:
            try:
                names = os.listdir(base)
            except OSError:
                continue
            for name in names:
                db = os.path.join(base, name, "places.sqlite")
                if os.path.isfile(db) and db not in found:
                    found.append(db)
        return found

    def _read_places(self, places_path):
        """Read a *copy* so Firefox can keep running with its database locked."""
        temp = tempfile.mkdtemp(prefix="clickscope-firefox-")
        try:
            copy = os.path.join(temp, "places.sqlite")
            shutil.copy2(places_path, copy)
            for ext in ("-wal", "-shm"):
                src = places_path + ext
                if os.path.isfile(src):
                    try:
                        shutil.copy2(src, copy + ext)
                    except OSError:
                        pass
            con = sqlite3.connect(copy, timeout=8)
            con.row_factory = sqlite3.Row
            try:
                folders = {}
                for row in con.execute("SELECT id, title FROM moz_bookmarks WHERE type=2"):
                    folders[row["id"]] = _clean(row["title"], 40)
                rows = con.execute(
                    "SELECT b.title AS title, p.url AS url, b.parent AS parent, "
                    "b.dateAdded AS added FROM moz_bookmarks b "
                    "JOIN moz_places p ON p.id=b.fk "
                    "WHERE b.type=1 AND p.url IS NOT NULL "
                    "ORDER BY b.dateAdded DESC").fetchall()
            finally:
                con.close()
            out = []
            for row in rows:
                url = row["url"] or ""
                if not url.lower().startswith(("http://", "https://")):
                    continue
                category = folders.get(row["parent"]) or "Bookmarks"
                out.append(dict(name=_clean(row["title"]) or _host(url), url=url,
                                category=category, added=row["added"] or 0))
            return out
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def import_firefox(self, places_paths=None, limit=5000):
        paths = list(places_paths or self.firefox_profiles())
        items, errors = [], []
        for path in paths:
            try:
                items.extend(self._read_places(path))
            except (OSError, sqlite3.Error, ValueError) as e:
                errors.append(f"{os.path.basename(os.path.dirname(path)) or path}: {e}")
            if len(items) >= limit:
                break
        items = items[:limit]
        result = self._merge(items, source="Firefox")
        result.update(profiles=paths, errors=errors, found=len(items))
        return result

    @staticmethod
    def chromium_bookmarks():
        """Bookmark files for Chrome/Edge/Brave, used only with explicit import."""
        local = os.environ.get("LOCALAPPDATA") or ""
        roots = [os.path.join(local, vendor, browser, "User Data", "Default", "Bookmarks")
                 for vendor, browser in (("Google", "Chrome"), ("Microsoft", "Edge"),
                                         ("BraveSoftware", "Brave-Browser"))]
        return [p for p in roots if os.path.isfile(p)]

    def import_chromium(self, paths=None, limit=5000):
        items, errors = [], []
        for path in (paths or self.chromium_bookmarks()):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                def walk(node, folder=""):
                    if len(items) >= limit:
                        return
                    if node.get("type") == "url" and str(node.get("url", "")).lower().startswith(
                            ("http://", "https://")):
                        items.append(dict(name=node.get("name") or _host(node.get("url")),
                                          url=node.get("url"), category=folder or "Bookmarks",
                                          added=(node.get("date_added") or 0)))
                    for child in node.get("children") or []:
                        walk(child, node.get("name") if node.get("type") == "folder" else folder)

                for root in (data.get("roots") or {}).values():
                    if isinstance(root, dict):
                        walk(root, root.get("name") or "Bookmarks")
            except (OSError, ValueError) as e:
                errors.append(f"{os.path.basename(os.path.dirname(path))}: {e}")
        result = self._merge(items[:limit], source="browser")
        result.update(profiles=list(paths or []), errors=errors, found=len(items[:limit]))
        return result
