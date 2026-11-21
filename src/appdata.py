"""Shared local paths, settings and small platform helpers.

ClickScope keeps everything in one folder. Nothing here talks to the network.
Set CLICKSCOPE_HOME to use another folder (tests, screenshots, portable use).
"""
import ctypes
import datetime
import json
import os
import shutil
import subprocess
import sys
import threading

APP_NAME = "ClickScope"
VERSION = "2.0"
APP_DIR = os.environ.get("CLICKSCOPE_HOME") or os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
INDEX_PATH = os.path.join(APP_DIR, "index.db")
STATE_PATH = os.path.join(APP_DIR, "state.json")
SNAPSHOT_DIR = os.path.join(APP_DIR, "blueprints")
WALLPAPER_DIR = os.path.join(APP_DIR, "wallpapers")

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def ensure_dirs():
    for d in (APP_DIR, SNAPSHOT_DIR, WALLPAPER_DIR):
        os.makedirs(d, exist_ok=True)


def resource_path(rel):
    """Locate bundled files both in dev and inside the PyInstaller EXE."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ------------------------------------------------------------------ settings
class State:
    """Tiny JSON settings store. Writes are atomic so a crash never truncates it."""

    def __init__(self, path=None):
        ensure_dirs()
        self.path = path or STATE_PATH
        self.lock = threading.RLock()
        self.data = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            self._write()

    def update(self, **kw):
        with self.lock:
            self.data.update(kw)
            self._write()

    def _write(self):
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ----- convenience
    def ignored_installers(self):
        v = self.get("ignored_installers", [])
        return set(v) if isinstance(v, list) else set()

    def ignore_installer(self, path, on=True):
        s = self.ignored_installers()
        if on:
            s.add(path.lower())
        else:
            s.discard(path.lower())
        self.set("ignored_installers", sorted(s))

    def index_roots(self):
        v = self.get("index_roots", [])
        return [p for p in v if isinstance(p, str)] if isinstance(v, list) else []

    def set_index_roots(self, roots):
        self.set("index_roots", list(dict.fromkeys(roots)))


# -------------------------------------------------------------------- helpers
def human_size(n):
    n = float(n or 0)
    if n >= 1024 ** 4:
        return f"{n / 1024 ** 4:.1f} TB"
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{int(n)} B" if n else "0 KB"


def human_age(ts):
    """'Today', '2 days ago', '3 months ago', '2 years ago'."""
    if not ts:
        return "unknown"
    try:
        d = datetime.datetime.fromtimestamp(ts)
    except (OSError, ValueError):
        return "unknown"
    days = (datetime.datetime.now() - d).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = max(1, days // 30)
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(1, days // 365)
    return f"{years} year{'s' if years != 1 else ''} ago"


def human_date(ts=None, fmt="%d %b %Y"):
    try:
        d = datetime.datetime.fromtimestamp(ts) if ts else datetime.datetime.now()
        return d.strftime(fmt)
    except (OSError, ValueError, TypeError):
        return ""


def human_time(ts=None):
    try:
        d = datetime.datetime.fromtimestamp(ts) if ts else datetime.datetime.now()
        return d.strftime("%H:%M")
    except (OSError, ValueError, TypeError):
        return ""


def shorten_path(path, limit=62):
    if len(path) <= limit:
        return path
    parts = path.split(os.sep)
    if len(parts) <= 3:
        return path[:limit - 1] + "\u2026"
    keep = []
    used = 0
    for p in reversed(parts[:-1]):
        if used + len(p) + 1 > limit - len(parts[-1]) - 5:
            break
        keep.append(p)
        used += len(p) + 1
    tail = os.sep.join(reversed(keep))
    return "\u2026" + os.sep + tail + os.sep + parts[-1]


def middle_ellipsis(text, limit):
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    left = (limit - 1) // 2
    right = limit - left - 1
    return text[:left] + "\u2026" + text[-right:]


def known_folders():
    """Existing everyday folders: Desktop, Downloads, Documents, Pictures, Music, Videos."""
    home = os.path.expanduser("~")
    cands = [
        ("Desktop", os.path.join(home, "Desktop")),
        ("Downloads", os.path.join(home, "Downloads")),
        ("Documents", os.path.join(home, "Documents")),
        ("Pictures", os.path.join(home, "Pictures")),
        ("Music", os.path.join(home, "Music")),
        ("Videos", os.path.join(home, "Videos")),
    ]
    # OneDrive often redirects the real folders.
    od = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if od:
        for label in ("Desktop", "Documents", "Pictures"):
            p = os.path.join(od, label)
            if os.path.isdir(p):
                cands.append((label, p))
    out, seen, seen_labels = [], set(), set()
    for label, p in cands:
        if os.path.isdir(p):
            rp = os.path.realpath(p).lower()
            if rp not in seen and label not in seen_labels:
                seen.add(rp)
                seen_labels.add(label)
                out.append((label, p))
    return out


def open_path(path):
    try:
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606 - intentional user action
        elif os.path.exists(path):
            os.startfile(path)
        return True
    except Exception:
        return False


def reveal_path(path):
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], creationflags=NO_WINDOW)
        return True
    except Exception:
        return False


def copy_text(text):
    try:
        import tkinter as tk
        r = tk._get_default_root()
        if r is not None:
            r.clipboard_clear()
            r.clipboard_append(text)
            return True
    except Exception:
        pass
    return False


def fixed_drives():
    """Letters of local fixed disks, e.g. ['C:\\\\', 'D:\\\\']."""
    if not IS_WINDOWS:
        return []
    try:
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
        out = []
        for i in range(26):
            if not (mask >> i) & 1:
                continue
            root = chr(65 + i) + ":\\"
            if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) == 3:  # DRIVE_FIXED
                out.append(root)
        return out
    except Exception:
        return []


def drive_info():
    """[{letter, label, total, free}] for fixed drives (best effort)."""
    out = []
    for root in fixed_drives():
        total = free = 0
        label = ""
        try:
            k32 = ctypes.windll.kernel32
            free_b = ctypes.c_ulonglong()
            total_b = ctypes.c_ulonglong()
            if k32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(root), ctypes.byref(free_b),
                                       ctypes.byref(total_b), None):
                free, total = free_b.value, total_b.value
            buf = ctypes.create_unicode_buffer(261)
            if k32.GetVolumeInformationW(ctypes.c_wchar_p(root), buf, 261, None, None, None, None, 0):
                label = buf.value
        except Exception:
            pass
        out.append(dict(letter=root[:2], root=root, label=label or "Local disk",
                        total=total, free=free))
    return out


def recycle_bin(paths):
    """Move files to the Windows Recycle Bin. Returns (moved, failed)."""
    paths = [p for p in paths if p]
    if not paths:
        return 0, []
    if not IS_WINDOWS:
        failed = []
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                failed.append(p)
        return len(paths) - len(failed), failed

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]

    FO_DELETE, FOF_ALLOWUNDO = 3, 0x0040
    FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI = 0x0010, 0x0004, 0x0400
    moved, failed = 0, []
    # one call per file keeps error reporting precise
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            op = SHFILEOPSTRUCTW(None, FO_DELETE, p + "\0\0", None,
                                 FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI)
            rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if rc == 0 and not op.fAnyOperationsAborted:
                moved += 1
            else:
                failed.append(p)
        except Exception:
            failed.append(p)
    return moved, failed


def rmtree_quiet(path):
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False
