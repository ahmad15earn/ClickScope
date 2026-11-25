"""Global Windows shortcut, without a window or an extra dependency.

ClickScope only asks Windows to tell it when one exact key combination is
pressed (RegisterHotKey). It never installs a keyboard hook, never sees any
other key press, and never reads what you type.

The registration and its message loop live on a small daemon thread, so the
interface keeps its normal Tk main loop. The callback runs on that thread:
post the result to the UI thread before touching any widget.
"""
import ctypes
import sys
import threading

IS_WINDOWS = sys.platform == "win32"

DEFAULT_SHORTCUT = "Ctrl+Alt+Space"
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_MODS = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_MOD_ALIASES = {
    "ctrl": "Ctrl", "control": "Ctrl",
    "alt": "Alt", "option": "Alt",
    "shift": "Shift",
    "win": "Win", "windows": "Win", "meta": "Win", "cmd": "Win",
}
_MOD_BY_NAME = dict(_MODS)

# lowercase name -> (display name, virtual-key code)
_KEYS = {}
for _i in range(10):
    _KEYS[str(_i)] = (str(_i), 0x30 + _i)
for _i in range(26):
    _c = chr(65 + _i)
    _KEYS[_c.lower()] = (_c, 0x41 + _i)
for _i in range(1, 25):
    _KEYS[f"f{_i}"] = (f"F{_i}", 0x6F + _i)
_KEYS.update({
    "space": ("Space", 0x20),
    "tab": ("Tab", 0x09),
    "enter": ("Enter", 0x0D),
    "return": ("Enter", 0x0D),
    "escape": ("Esc", 0x1B),
    "esc": ("Esc", 0x1B),
    "backspace": ("Backspace", 0x08),
    "insert": ("Insert", 0x2D),
    "ins": ("Insert", 0x2D),
    "delete": ("Delete", 0x2E),
    "del": ("Delete", 0x2E),
    "home": ("Home", 0x24),
    "end": ("End", 0x23),
    "pageup": ("PageUp", 0x21),
    "pgup": ("PageUp", 0x21),
    "pagedown": ("PageDown", 0x22),
    "pgdn": ("PageDown", 0x22),
    "left": ("Left", 0x25),
    "up": ("Up", 0x26),
    "right": ("Right", 0x27),
    "down": ("Down", 0x28),
    "printscreen": ("PrintScreen", 0x2C),
    "prtsc": ("PrintScreen", 0x2C),
})


def parse_shortcut(spec):
    """'ctrl + alt + k' -> (mods, vk, 'Ctrl+Alt+K'). Raises ValueError."""
    text = str(spec or "").strip()
    if not text:
        raise ValueError("Choose a shortcut first.")
    parts = [p.strip().lower() for p in text.split("+")]
    if any(not p for p in parts):
        raise ValueError("That shortcut isn't complete.")
    if len(parts) < 2:
        raise ValueError("Add Ctrl, Alt or Win to another key.")
    mods, names = 0, []
    key = None
    for part in parts:
        name = _MOD_ALIASES.get(part)
        if name:
            if name in names:
                continue
            names.append(name)
            mods |= _MOD_BY_NAME[name]
            continue
        if key is not None:
            raise ValueError("Use one key, with Ctrl, Alt or Win.")
        key = part
    if key is None or key in _MOD_ALIASES:
        raise ValueError("Add a key after the modifier.")
    if not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        raise ValueError("Use Ctrl, Alt or Win so typing stays normal.")
    if key not in _KEYS:
        raise ValueError("That key can't be used. Try a letter, a number, Space or an F-key.")
    display, vk = _KEYS[key]
    order = [name for name, _ in _MODS if name in names]
    return mods, vk, "+".join(order + [display])


def normalize_shortcut(spec):
    """Store form, e.g. 'Ctrl+Alt+Space'. Raises ValueError with a friendly reason."""
    return parse_shortcut(spec)[2]


def pretty_shortcut(spec):
    """Display form for buttons and hints, e.g. 'Ctrl + Alt + Space'."""
    try:
        return normalize_shortcut(spec).replace("+", " + ")
    except ValueError:
        return str(spec or "")


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint), ("pt", _POINT)]


class GlobalHotkey:
    """Register one system-wide shortcut on a background thread."""

    def __init__(self, callback=None):
        self.callback = callback
        self._thread = None
        self._tid = 0
        self._ready = threading.Event()
        self._ok = False
        self._error = ""
        self._spec = ""
        self._lock = threading.RLock()

    # ------------------------------------------------------------- public
    def start(self, spec):
        """Register `spec`. Returns (ok, message); false leaves nothing registered."""
        with self._lock:
            self.stop()
            if not IS_WINDOWS:
                self._error = "Global shortcuts need Windows."
                return False, self._error
            try:
                mods, vk, canon = parse_shortcut(spec)
            except ValueError as e:
                self._error = str(e)
                return False, self._error
            self._ready.clear()
            self._ok = False
            self._error = ""
            self._thread = threading.Thread(target=self._run, args=(mods, vk, canon),
                                            daemon=True, name="ClickScopeHotkey")
            self._thread.start()
            self._ready.wait(2.0)
            if self._ok:
                self._spec = canon
                return True, ""
            self._thread = None
            self._error = self._error or "Windows would not accept that shortcut."
            return False, self._error

    def stop(self):
        with self._lock:
            thread, tid = self._thread, self._tid
            self._thread = None
            if thread is None or not thread.is_alive():
                return
            try:
                ctypes.windll.user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            except Exception:
                pass
            thread.join(timeout=1.5)
            self._tid = 0
            self._ok = False

    @property
    def active(self):
        return self._ok

    @property
    def shortcut(self):
        return self._spec

    @property
    def error(self):
        return self._error

    # ------------------------------------------------------------- thread
    def _run(self, mods, vk, canon):
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
            if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
                code = ctypes.get_last_error()
                if code == ERROR_HOTKEY_ALREADY_REGISTERED:
                    self._error = "That shortcut is already used by Windows or another app."
                else:
                    self._error = "That shortcut is already used or not allowed."
                self._ready.set()
                return
            self._ok = True
            self._spec = canon
            self._ready.set()
            msg = _MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and self.callback is not None:
                    try:
                        self.callback()
                    except Exception:
                        pass
            user32.UnregisterHotKey(None, 1)
        except Exception as e:
            self._error = str(e) or "Windows would not accept that shortcut."
            self._ready.set()
        finally:
            self._ok = False
