"""One-time, local scan of installed software and browser favourites (Windows).

Nothing leaves the PC. Websites: only domain names + visit counts are kept, never full URLs or titles.
Pure helpers (clean_apps, domain_of, aggregate_domains) are platform independent and unit-tested.
"""
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from urllib.parse import urlparse

NOISE = re.compile(
    r"(update for|security update|hotfix|\bKB\d{6,}|redistributable|runtime|\.net |\.net$|visual c\+\+|"
    r"windows sdk|windows driver|webview2|language pack|microsoft update health|vcredist|"
    r"windows software development kit|application verifier)", re.I)


def clean_apps(raw):
    """raw: [(name, version, publisher)] -> sorted unique [(name, detail)] without runtimes/updates."""
    seen, out = set(), []
    for name, version, publisher in raw:
        name = (name or "").strip()
        if not name or NOISE.search(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        bits = [b for b in (publisher, f"v{version}" if version else "") if b]
        out.append((name, "  \u00b7  ".join(bits)))
    return sorted(out, key=lambda t: t[0].lower())


def domain_of(url):
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host or host == "localhost" or re.fullmatch(r"[\d.:]+", host) or "." not in host:
        return None
    return host[4:] if host.startswith("www.") else host


def aggregate_domains(rows, limit=25):
    """rows: [(url, visit_count)] -> [(domain, visits)] most visited first."""
    tot = {}
    for url, n in rows:
        d = domain_of(url)
        if d:
            tot[d] = tot.get(d, 0) + int(n or 0)
    return sorted(tot.items(), key=lambda t: -t[1])[:limit]


# ------------------------------------------------------------------ apps
def scan_apps():
    """Installed programs from the registry + Start Menu shortcuts (portable / Store apps)."""
    if sys.platform != "win32":
        return []
    import winreg
    raw = []
    roots = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]

    def val(k, name):
        try:
            return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None

    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                            if val(sk, "SystemComponent") == 1 or val(sk, "ParentKeyName") or \
                                    val(sk, "ReleaseType") in ("Update", "Hotfix", "Security Update"):
                                continue
                            raw.append((val(sk, "DisplayName"), val(sk, "DisplayVersion"), val(sk, "Publisher")))
                    except OSError:
                        continue
        except OSError:
            continue
    apps = clean_apps(raw)
    known = [n.lower() for n, _ in apps]
    menus = [os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    extra = []
    for base in menus:
        for root, _, files in os.walk(base):
            for f in files:
                stem, ext = os.path.splitext(f)
                low = stem.lower()
                if ext.lower() != ".lnk" or re.search(r"uninstall|readme|help|website|documentation|license|release notes", low):
                    continue
                if any(low in k or k in low for k in known) or low in [e.lower() for e, _ in extra]:
                    continue
                extra.append((stem, "Start Menu"))
    return sorted(apps + extra, key=lambda t: t[0].lower())


# -------------------------------------------------------------- browsers
def _chromium_dirs():
    local = os.environ.get("LOCALAPPDATA", "")
    return [("Google Chrome", os.path.join(local, "Google", "Chrome", "User Data")),
            ("Microsoft Edge", os.path.join(local, "Microsoft", "Edge", "User Data")),
            ("Brave", os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data")),
            ("Vivaldi", os.path.join(local, "Vivaldi", "User Data")),
            ("Opera", os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera Stable"))]


def detect_browsers():
    """[(label, kind, profile_dir)] for browsers that have a profile on this PC."""
    out = []
    for label, base in _chromium_dirs():
        prof = os.path.join(base, "Default")
        if os.path.isdir(prof):
            out.append((label, "chromium", prof))
        elif label == "Opera" and os.path.isdir(base):
            out.append((label, "chromium", base))
    for p in glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles", "*")):
        if os.path.exists(os.path.join(p, "places.sqlite")):
            out.append(("Firefox", "firefox", p))
            break
    return out


def _query_copy(db_path, sql):
    """Browsers lock their history while running, so read a temporary copy."""
    tmp = os.path.join(tempfile.mkdtemp(), "h.db")
    try:
        shutil.copy2(db_path, tmp)
        con = sqlite3.connect(tmp)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return []
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)


def _bookmark_urls(path):
    urls = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "url" and node.get("url"):
                urls.append(node["url"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    try:
        with open(path, encoding="utf-8") as f:
            walk(json.load(f).get("roots", {}))
    except (OSError, ValueError):
        pass
    return urls


def read_sites(kind, profile_dir, limit=25):
    """Most visited + bookmarked domains for one browser profile: [(domain, detail)]."""
    if kind == "firefox":
        rows = _query_copy(os.path.join(profile_dir, "places.sqlite"),
                           "SELECT url, visit_count FROM moz_places WHERE visit_count>0 ORDER BY visit_count DESC LIMIT 1500")
        marks = []
    else:
        rows = _query_copy(os.path.join(profile_dir, "History"),
                           "SELECT url, visit_count FROM urls ORDER BY visit_count DESC LIMIT 1500")
        marks = _bookmark_urls(os.path.join(profile_dir, "Bookmarks"))
    visits = dict(aggregate_domains(rows, 500))
    out = [(d, f"{n:,} visits") for d, n in sorted(visits.items(), key=lambda t: -t[1])[:limit]]
    have = {d for d, _ in out}
    for d in dict.fromkeys(domain_of(u) for u in marks):
        if d and d not in have and len(out) < limit + 10:
            out.append((d, "bookmarked"))
            have.add(d)
    return out
