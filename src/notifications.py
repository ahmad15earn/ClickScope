"""Quiet notifications for finished work, never for destructive decisions.

Notifications can open the matching section, and they are recorded in a local
history, but they can never delete, move or change a file. Turning them off
never affects protection or safety checks: those keep running either way.
"""
import html
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

from appdata import APP_DIR, IS_WINDOWS, NO_WINDOW, ensure_url_protocol

NOTIFICATIONS_PATH = os.path.join(APP_DIR, "notifications.json")

TYPES = (
    ("index", "Index", "Indexing finished"),
    ("installers", "Installers", "Old installers found"),
    ("duplicates", "Duplicates", "Possible duplicate files"),
    ("protection", "Protected", "Protected items kept out of cleanup"),
    ("blueprint", "Blueprint", "Blueprint saved, exported or imported"),
    ("websites", "Websites", "Website memory changes"),
    ("errors", "Errors", "A scan or task failed"),
)
TYPE_KEYS = tuple(t[0] for t in TYPES)

# The AUMID Windows PowerShell already uses for toasts; a plain desktop process
# is not registered with the toast platform, but this app id is.
PS_APPID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

TOAST_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$toast = $doc.CreateElement('toast')
$toast.SetAttribute('activationType', 'protocol')
$toast.SetAttribute('launch', 'clickscope:' + $env:CS_TARGET)
$visual = $doc.CreateElement('visual')
$binding = $doc.CreateElement('binding')
$binding.SetAttribute('template', 'ToastGeneric')
foreach ($v in @($env:CS_TITLE, $env:CS_BODY)) {
  if ($v) {
    $t = $doc.CreateElement('text')
    $t.InnerText = $v
    $binding.AppendChild($t) | Out-Null
  }
}
$visual.AppendChild($binding) | Out-Null
$toast.AppendChild($visual) | Out-Null
$doc.AppendChild($toast) | Out-Null
$n = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CS_APPID).Show($n)
"""


def windows_toast_supported():
    return IS_WINDOWS and shutil.which("powershell") is not None


def windows_toast(title, body="", target=""):
    """Best-effort Windows toast. Clicking it opens ClickScope on `target`."""
    if not windows_toast_supported():
        return False
    try:
        ensure_url_protocol()
        env = os.environ.copy()
        env["CS_TITLE"] = str(title or "ClickScope")[:120]
        env["CS_BODY"] = str(body or "")[:200]
        env["CS_TARGET"] = str(target or "search")[:40]
        env["CS_APPID"] = PS_APPID
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                          "-Command", TOAST_SCRIPT], env=env, creationflags=NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


class Notifications:
    """Settings + a capped local history. Never performs a file operation."""

    def __init__(self, path=None, windows=None):
        self.path = path or NOTIFICATIONS_PATH
        self.lock = threading.RLock()
        self.enabled = True
        self.windows = bool(windows) if windows is not None else True
        self._force_windows = windows
        self.types = {key: True for key in TYPE_KEYS}
        self.items = []
        self.on_new = None
        self._load()

    # ------------------------------------------------------------------ disk
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError):
            try:
                if os.path.isfile(self.path):
                    os.replace(self.path, self.path + ".corrupt-%d" % int(time.time()))
            except OSError:
                pass
            data = {}
        if not isinstance(data, dict):
            data = {}
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
        self.enabled = bool(settings.get("enabled", data.get("enabled", True)))
        if self._force_windows is not None:
            self.windows = bool(self._force_windows)
        else:
            self.windows = bool(settings.get("windows", True))
        raw_types = settings.get("types") or data.get("types") or {}
        if isinstance(raw_types, dict):
            for key in TYPE_KEYS:
                if key in raw_types:
                    self.types[key] = bool(raw_types[key])
        for raw in data.get("items") or []:
            if not isinstance(raw, dict) or not raw.get("title"):
                continue
            self.items.append(dict(
                id=str(raw.get("id") or ("n-" + uuid.uuid4().hex[:10])),
                type=str(raw.get("type") or "index"), title=str(raw.get("title"))[:160],
                body=str(raw.get("body") or "")[:300], target=str(raw.get("target") or ""),
                ts=int(raw.get("ts") or 0), read=bool(raw.get("read", False))))
        self.items.sort(key=lambda i: i["ts"], reverse=True)
        self.items = self.items[:120]

    def _write(self):
        data = dict(format="clickscope-notifications", version=1,
                    settings=dict(enabled=self.enabled, windows=self.windows, types=dict(self.types)),
                    items=self.items[:120])
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
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

    # -------------------------------------------------------------- settings
    def set_enabled(self, on):
        with self.lock:
            self.enabled = bool(on)
            self._write()

    def set_windows(self, on):
        with self.lock:
            self.windows = bool(on)
            if self.windows:
                ensure_url_protocol()
            self._write()

    def set_type(self, key, on):
        if key not in self.types:
            return
        with self.lock:
            self.types[key] = bool(on)
            self._write()

    def is_enabled(self, key=None):
        with self.lock:
            return self.enabled and (key is None or bool(self.types.get(key, True)))

    def settings(self):
        with self.lock:
            return dict(enabled=self.enabled, windows=self.windows, types=dict(self.types))

    # ----------------------------------------------------------------- events
    def emit(self, ntype, title, body="", target="", toast=True):
        """Record a notification. Returns None when this type is switched off."""
        if not self.is_enabled(ntype):
            return None
        item = dict(id="n-" + uuid.uuid4().hex[:10], type=ntype, title=str(title)[:160],
                    body=str(body or "")[:300], target=str(target or ""),
                    ts=int(time.time()), read=False)
        with self.lock:
            self.items.insert(0, item)
            self.items = self.items[:120]
            self._write()
            windows = self.windows and toast
        if windows:
            windows_toast(item["title"], item["body"], item["target"])
        if self.on_new:
            try:
                self.on_new(dict(item))
            except Exception:
                pass
        return dict(item)

    def recent(self, limit=20, unread_only=False):
        with self.lock:
            rows = [dict(i) for i in self.items if not unread_only or not i["read"]]
        return rows[:limit]

    def unread_count(self):
        with self.lock:
            return sum(1 for i in self.items if not i["read"])

    def mark_read(self, item_id=None):
        with self.lock:
            changed = False
            for item in self.items:
                if (item_id is None or item["id"] == item_id) and not item["read"]:
                    item["read"] = True
                    changed = True
            if changed:
                self._write()

    def clear(self):
        """Clear the notification history only. Files and protection are untouched."""
        with self.lock:
            self.items = []
            self._write()

    def summary(self):
        with self.lock:
            return dict(total=len(self.items), unread=sum(1 for i in self.items if not i["read"]),
                        enabled=self.enabled, windows=self.windows)
