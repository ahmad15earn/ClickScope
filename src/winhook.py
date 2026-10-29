"""Windows click tracker (pure ctypes, no third-party packages).

What it reads on each click: which window was clicked (process name, plus the
window title only for browsers, to guess the site name). The cursor position
is used for that one lookup and is never stored.
"""
import ctypes
import os
import queue
import threading
from ctypes import wintypes

from core import BROWSERS, app_label, site_label

WH_MOUSE_LL = 14
WM_QUIT = 0x0012
CLICK_DOWN = (0x0201, 0x0204, 0x0207)  # left, right, middle button down
GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def _exe_name(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None  # e.g. elevated (admin) apps
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return None
    finally:
        kernel32.CloseHandle(h)


def _title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


class Tracker:
    def __init__(self, store):
        self.store = store
        self.q = queue.Queue(maxsize=2000)
        self.paused = False
        self.running = False
        self.click_count = 0
        self._tid = None
        self._proc = None

    # -- hook thread: must stay tiny and fast
    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code >= 0 and not self.paused and w_param in CLICK_DOWN:
                info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not (info.flags & 0x01):  # ignore software-generated clicks
                    self.q.put_nowait((info.pt.x, info.pt.y))
        except Exception:
            pass
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _hook_thread(self):
        self._tid = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._callback)
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)

    # -- worker thread: resolves what was clicked and stores the count
    def _resolve(self, x, y):
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        if not hwnd:
            return None, None
        root = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(root, ctypes.byref(pid))
        if pid.value == os.getpid():
            return None, None  # don't count clicks inside ClickScope itself
        exe = _exe_name(pid.value)
        title = _title(root) if (exe in BROWSERS or exe == "applicationframehost.exe") else ""
        app = app_label(exe, title)
        site = None
        if exe in BROWSERS and self.store.get("track_sites", "1") == "1":
            site = site_label(title)
        return app, site

    def _worker(self):
        while self.running:
            try:
                x, y = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                app, site = self._resolve(x, y)
                if app:
                    self.store.add_click(app, site)
                    self.click_count += 1
            except Exception:
                pass

    def start(self):
        self.running = True
        threading.Thread(target=self._hook_thread, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    def stop(self):
        self.running = False
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
