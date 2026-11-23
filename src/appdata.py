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
import zipfile

APP_NAME = "ClickScope"
VERSION = "2.0"
DEFAULT_APP_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
LOCATION_FILE = os.path.join(DEFAULT_APP_DIR, "location.txt")


def _saved_location():
    """Read the user's chosen storage folder, if it still exists."""
    try:
        with open(LOCATION_FILE, encoding="utf-8") as f:
            path = f.read().strip()
        if path and os.path.isdir(path):
            return os.path.abspath(path)
    except OSError:
        pass
    return ""


APP_DIR = os.environ.get("CLICKSCOPE_HOME") or _saved_location() or DEFAULT_APP_DIR
INDEX_PATH = os.path.join(APP_DIR, "index.db")
STATE_PATH = os.path.join(APP_DIR, "state.json")
SNAPSHOT_DIR = os.path.join(APP_DIR, "blueprints")
WALLPAPER_DIR = os.path.join(APP_DIR, "wallpapers")
DATA_FILES = ("state.json", "websites.json", "protection.json", "notifications.json")
DATA_DIRS = ("blueprints", "wallpapers")

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def ensure_dirs():
    for d in (APP_DIR, SNAPSHOT_DIR, WALLPAPER_DIR):
        os.makedirs(d, exist_ok=True)
    try:
        os.makedirs(DEFAULT_APP_DIR, exist_ok=True)
    except OSError:
        pass


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

    def storage_location(self):
        return self.get("storage_location") or APP_DIR


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


def local_drives(include_removable=True):
    """Local fixed disks, plus USB drives when asked, e.g. ['C:\\\\', 'E:\\\\']."""
    if not IS_WINDOWS:
        return []
    try:
        k32 = ctypes.windll.kernel32
        mask = k32.GetLogicalDrives()
        kinds = {2, 3} if include_removable else {3}  # DRIVE_REMOVABLE, DRIVE_FIXED
        out = []
        for i in range(26):
            if not (mask >> i) & 1:
                continue
            root = chr(65 + i) + ":\\"
            if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) in kinds:
                out.append(root)
        return out
    except Exception:
        return []


# ------------------------------------------------------------ storage & backup
def _copy_data_tree(src_dir, dst_dir):
    copied, errors = 0, []
    for name in DATA_FILES:
        src = os.path.join(src_dir, name)
        if os.path.isfile(src):
            try:
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, os.path.join(dst_dir, name))
                copied += 1
            except OSError as e:
                errors.append(f"{name}: {e}")
    for name in DATA_DIRS:
        src = os.path.join(src_dir, name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(dst_dir, name)
        try:
            if os.path.isdir(dst):
                for root, _, files in os.walk(src):
                    rel = os.path.relpath(root, src)
                    target = dst if rel == "." else os.path.join(dst, rel)
                    os.makedirs(target, exist_ok=True)
                    for f in files:
                        shutil.copy2(os.path.join(root, f), os.path.join(target, f))
                        copied += 1
            else:
                shutil.copytree(src, dst)
                for root, _, files in os.walk(dst):
                    copied += len(files)
        except OSError as e:
            errors.append(f"{name}: {e}")
    return copied, errors


def relocate_storage(new_dir):
    """Copy ClickScope's data to another folder and remember it for next launch.

    The search index is intentionally left behind: it only holds file names and
    is rebuilt in seconds, so copying a live SQLite database is never worth the
    corruption risk. Nothing in the old folder is deleted.
    """
    new_dir = os.path.abspath(os.path.expanduser(new_dir or ""))
    if not new_dir:
        return dict(ok=False, error="Choose a folder first.", copied=0)
    cur = os.path.abspath(APP_DIR)
    if os.path.normcase(new_dir) == os.path.normcase(cur):
        return dict(ok=False, error="ClickScope already stores its data there.", copied=0)
    if os.path.normcase(new_dir).startswith(os.path.normcase(cur) + os.sep):
        return dict(ok=False, error="Choose a folder outside the current data folder.", copied=0)
    try:
        os.makedirs(new_dir, exist_ok=True)
        probe = os.path.join(new_dir, ".clickscope-write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return dict(ok=False, error=f"That folder is not writable: {e}", copied=0)
    copied, errors = _copy_data_tree(cur, new_dir)
    try:
        os.makedirs(DEFAULT_APP_DIR, exist_ok=True)
        tmp = LOCATION_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_dir)
        os.replace(tmp, LOCATION_FILE)
    except OSError as e:
        return dict(ok=False, error=f"Could not remember the new folder: {e}", copied=copied,
                    errors=errors)
    return dict(ok=True, error="", copied=copied, errors=errors, path=new_dir)


def reset_storage_location():
    """Forget the custom folder. Data already copied there is left untouched."""
    try:
        if os.path.isfile(LOCATION_FILE):
            os.remove(LOCATION_FILE)
        return True
    except OSError:
        return False


def storage_usage():
    """(bytes, files) used by ClickScope's own data folder."""
    total = files = 0
    for root, _, names in os.walk(APP_DIR):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(root, name))
                files += 1
            except OSError:
                pass
    return total, files


def backup_data(destination):
    """One zip with settings, protection, websites, notifications and blueprints.

    The search index is excluded on purpose: it is rebuildable and can be large.
    The zip is verified before it is reported as a success.
    """
    destination = os.path.abspath(os.path.expanduser(destination or ""))
    if not destination:
        raise ValueError("Choose where to save the backup.")
    tmp = destination + ".tmp"
    written = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            manifest = dict(format="clickscope-backup", version=1,
                            created=datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
                            app_version=VERSION)
            z.writestr("backup.json", json.dumps(manifest, indent=2))
            for name in DATA_FILES:
                p = os.path.join(APP_DIR, name)
                if os.path.isfile(p):
                    z.write(p, name)
                    written += 1
            for name in DATA_DIRS:
                base = os.path.join(APP_DIR, name)
                if not os.path.isdir(base):
                    continue
                for root, _, files in os.walk(base):
                    for f in files:
                        p = os.path.join(root, f)
                        try:
                            z.write(p, os.path.relpath(p, APP_DIR))
                            written += 1
                        except OSError:
                            pass
        with zipfile.ZipFile(tmp) as z:
            if z.testzip() is not None:
                raise ValueError("The backup did not verify.")
        os.replace(tmp, destination)
        return dict(path=destination, files=written, size=os.path.getsize(destination),
                    size_text=human_size(os.path.getsize(destination)))
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ------------------------------------------------------ notification protocol
def _protocol_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --open "%1"'
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.isfile(pythonw):
        exe = pythonw
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}" --open "%1"'


def ensure_url_protocol():
    """Register clickscope:// for toast click-through. HKCU only, best effort."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        base = r"Software\Classes\clickscope"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:ClickScope")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command", 0,
                                winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _protocol_command())
        return True
    except Exception:
        return False


def protocol_installed():
    if not IS_WINDOWS:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Classes\clickscope\shell\open\command") as k:
            winreg.QueryValueEx(k, "")
        return True
    except Exception:
        return False


def write_open_request(target):
    """Ask an already-running ClickScope to switch pages."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        path = os.path.join(APP_DIR, "open_request.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(page=target, ts=datetime.datetime.now().timestamp()), f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def take_open_request():
    """Return a pending page request once, then remove it."""
    path = os.path.join(APP_DIR, "open_request.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        os.remove(path)
        return str(data.get("page") or "") if isinstance(data, dict) else ""
    except (OSError, ValueError):
        try:
            os.remove(path)
        except OSError:
            pass
        return ""


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
