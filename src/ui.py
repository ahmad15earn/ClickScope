"""ClickScope: a quiet Windows utility built around four everyday jobs.

Search finds files instantly, Installers clears old setup files safely,
Blueprint remembers the shape of the PC, and Settings keeps everything local.
"""
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk

import appdata as A
import notifications as N
import pages
import protection as P
import theme as T
import websites as W
from motion import Motion, clamp, mix, reduced_motion
from uikit import (NavRail, circle, draw_glyph, draw_icon, ellipsize, measure, photo, rr)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _plate(c, x1, y1, x2, y2, r, fill):
    """A solid rounded rectangle drawn from rectangles and discs.

    Tk's smoothed-polygon fills can leave a hairline at the edge; over a stippled
    scrim that hairline reads as ragged teeth, so dialogs use this instead.
    """
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="")
    c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="")
    for cx, cy in ((x1 + r, y1 + r), (x2 - r, y1 + r), (x1 + r, y2 - r), (x2 - r, y2 - r)):
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="")


# ------------------------------------------------------------------ autostart
def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "ClickScope")
        return True
    except Exception:
        return False


def set_autostart(on):
    import winreg
    if getattr(sys, "frozen", False):
        cmd = f'"{sys.executable}" --minimized'
    else:
        exe = sys.executable
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pythonw):
            exe = pythonw
        cmd = f'"{exe}" "{os.path.abspath(sys.argv[0])}" --minimized'
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "ClickScope", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "ClickScope")
            except FileNotFoundError:
                pass


# ----------------------------------------------------------------- back jobs
class Jobs:
    """Runs slow work off the Tk thread and returns results through one queue."""

    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.closed = False
        self.root.after(40, self._drain)

    def run(self, fn, on_done=None, on_error=None):
        def work():
            try:
                result = fn()
            except Exception as e:
                if on_error:
                    self.post(lambda e=e: on_error(e))
            else:
                if on_done:
                    self.post(lambda: on_done(result))
        threading.Thread(target=work, daemon=True, name="ClickScopeJob").start()

    def post(self, fn):
        if not self.closed:
            self.q.put(fn)

    def _drain(self):
        if self.closed:
            return
        for _ in range(30):
            try:
                fn = self.q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                pass
        try:
            self.root.after(40, self._drain)
        except tk.TclError:
            pass

    def close(self):
        self.closed = True


# --------------------------------------------------------------------- toast
class Toast:
    """A small dark confirmation pill that fades in above the taskbar."""

    KEY = "#F70FF7"

    def __init__(self, root):
        self.root = root
        self.top = None
        self.canvas = None
        self._after = []
        self._alpha = 1.0
        self._transparent = True

    def __call__(self, text, tone="good"):
        self.show(text, tone)

    def show(self, text, tone="good"):
        if self.root.state() == "iconic":
            return
        self._clear()
        colors = {"good": T.GREEN, "warn": T.AMBER, "error": T.RED, "info": T.ACCENT}
        icons = {"good": "check", "warn": "warning", "error": "warning", "info": "info"}
        color = colors.get(tone, T.GREEN)
        icon = icons.get(tone, "check")
        width = T.s(470)
        height = T.s(54)
        try:
            top = tk.Toplevel(self.root)
            top.withdraw()
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            try:
                top.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            try:
                top.attributes("-transparentcolor", self.KEY)
                bg = self.KEY
                self._transparent = True
            except tk.TclError:
                bg = T.INK
                self._transparent = False
            top.configure(bg=bg)
            c = tk.Canvas(top, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
            c.pack()
            if self._transparent:
                rr(c, 1, 1, width - 1, height - 3, T.s(15), fill="#000000", outline="")
                rr(c, 1, 0, width - 1, height - 4, T.s(15), fill=T.INK, outline="")
            else:
                c.create_rectangle(0, 0, width, height, fill=T.INK, outline="")
            circle(c, T.s(27), height / 2 - T.s(2), T.s(11), fill=color, outline="")
            draw_glyph(c, icon, T.s(27), height / 2 - T.s(2), "#FFFFFF", T.s(13), width=T.s(2.0))
            avail = width - T.s(52) - T.s(20)
            c.create_text(T.s(48), height / 2 - T.s(2), text=ellipsize(text, 9, "bold", avail),
                          font=T.F(9, "bold"), fill="#FFFFFF", anchor="w")
            self.top, self.canvas = top, c
            self._alpha = 0.0
            self._place()
            top.deiconify()
            tk.Misc.tkraise(top)
            self._fade_in(0)
            self._after.append(self.root.after(3900, self._fade_out))
        except tk.TclError:
            self.top = None

    def _place(self):
        if not self.top:
            return
        self.root.update_idletasks()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        w, h = self.canvas.winfo_reqwidth(), self.canvas.winfo_reqheight()
        x = rx + (rw - w) // 2
        y = ry + rh - h - T.s(28)
        self.top.geometry(f"{w}x{h}+{x}+{y}")

    def _fade_in(self, i):
        if not self.top:
            return
        steps = 8
        alpha = (i + 1) / steps
        try:
            self.top.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if i + 1 < steps:
            self._after.append(self.root.after(14, lambda: self._fade_in(i + 1)))

    def _fade_out(self):
        if not self.top:
            return
        self._fade_step(0)

    def _fade_step(self, i):
        if not self.top:
            return
        steps = 7
        alpha = 1.0 - (i + 1) / steps
        try:
            self.top.attributes("-alpha", max(0.0, alpha))
        except tk.TclError:
            self._clear()
            return
        if i + 1 < steps:
            self._after.append(self.root.after(18, lambda: self._fade_step(i + 1)))
        else:
            self._clear()

    def _clear(self):
        for after in self._after:
            try:
                self.root.after_cancel(after)
            except Exception:
                pass
        self._after = []
        if self.top is not None:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
        self.top, self.canvas = None, None

    def close(self):
        self._clear()


# -------------------------------------------------------------- confirm sheet
def _wrap(text, size, weight, width):
    words = str(text).split()
    lines, line = [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if measure(trial, size, weight) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class ConfirmSheet:
    """An in-window modal sheet. Dims the app, keeps focus, and never scrolls."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.canvas = None
        self.hits = []
        self.hover = ""
        self.on_confirm = None

    def ask(self, title, body, detail="", confirm="Continue", cancel="Cancel", tone="primary", on_confirm=None):
        self.close()
        self.on_confirm = on_confirm
        self.title, self.body, self.detail = title, body, detail
        self.confirm, self.cancel, self.tone = confirm, cancel, tone
        c = tk.Canvas(self.root, bg=T.BG, highlightthickness=0, bd=0, takefocus=1)
        c.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(c)
        self.canvas = c
        self.hover = ""
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<ButtonPress-1>", self._click)
        c.bind("<Motion>", self._move)
        c.bind("<Leave>", lambda e: self._set_hover(""))
        c.bind("<Escape>", lambda e: self.close())
        c.bind("<Return>", lambda e: self._confirm())
        c.focus_set()
        self._draw()

    def _geometry(self):
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        cw = min(T.s(520), max(T.s(360), W - T.s(80)))
        pad = T.s(28)
        title_lh = T.s(24)
        body_lines = _wrap(self.body, 10, "normal", cw - pad * 2)
        body_h = len(body_lines) * T.s(17)
        detail_h = T.s(26) if self.detail else 0
        ch = pad + title_lh + T.s(10) + body_h + detail_h + T.s(26) + T.s(38) + T.s(24)
        ch = max(T.s(210), ch)
        x = (W - cw) / 2
        y = max(T.s(30), (H - ch) / 2)
        return W, H, cw, ch, x, y, pad, title_lh, body_lines, body_h

    def _draw(self):
        c = self.canvas
        if not c:
            return
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 40:
            return
        c.create_rectangle(0, 0, W, H, fill="#2B2B31", stipple="gray50", outline="")
        W, H, cw, ch, x, y, pad, title_lh, body_lines, body_h = self._geometry()
        # Solid plate: a smoothed polygon leaves a hairline of the stippled scrim
        # along its edge, which shows up as ragged teeth. Rects + discs never do.
        _plate(c, x, y, x + cw, y + ch, T.s(18), T.CARD)
        c.create_text(x + pad, y + pad, text=self.title, font=T.F(16, "bold"), fill=T.TEXT, anchor="nw",
                      width=cw - pad * 2)
        by = y + pad + title_lh + T.s(10)
        c.create_text(x + pad, by, text=self.body, font=T.F(10), fill=T.SUB, anchor="nw",
                      width=cw - pad * 2, justify="left")
        dy = by + body_h + T.s(8)
        if self.detail:
            rr(c, x + pad, dy, x + cw - pad, dy + T.s(26), T.s(8), fill=T.TRACK, outline="")
            c.create_text(x + pad + T.s(12), dy + T.s(13), text=ellipsize(self.detail, 9, "bold",
                                                                          cw - pad * 2 - T.s(24)),
                          font=T.F(9, "bold"), fill=T.SUB, anchor="w")
        bh = T.s(38)
        by2 = y + ch - T.s(24) - bh
        cancel_w = measure(self.cancel, 9, "bold") + T.s(30)
        confirm_w = measure(self.confirm, 9, "bold") + T.s(34)
        cx2 = x + cw - pad
        confirm_box = (cx2 - confirm_w, by2, cx2, by2 + bh)
        cancel_box = (confirm_box[0] - T.s(10) - cancel_w, by2, confirm_box[0] - T.s(10), by2 + bh)
        self.hits = [("confirm",) + confirm_box, ("cancel",) + cancel_box]
        hover_c = self.hover == "confirm"
        hover_x = self.hover == "cancel"
        if self.tone == "danger":
            base, hov = T.RED, "#C22E39"
        else:
            base, hov = T.INK, "#34343A"
        rr(c, *confirm_box, T.s(9), fill=mix(base, hov, 1 if hover_c else 0), outline="")
        c.create_text((confirm_box[0] + confirm_box[2]) / 2, (confirm_box[1] + confirm_box[3]) / 2,
                      text=self.confirm, font=T.F(9, "bold"), fill="#FFFFFF", anchor="center")
        rr(c, *cancel_box, T.s(9), fill=T.TRACK if hover_x else T.CARD, outline=T.LINE2)
        c.create_text((cancel_box[0] + cancel_box[2]) / 2, (cancel_box[1] + cancel_box[3]) / 2,
                      text=self.cancel, font=T.F(9, "bold"), fill=T.TEXT, anchor="center")

    def _hit(self, x, y):
        for name, x1, y1, x2, y2 in self.hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return ""

    def _move(self, e):
        self._set_hover(self._hit(e.x, e.y))

    def _set_hover(self, name):
        if name != self.hover:
            self.hover = name
            self.canvas.configure(cursor="hand2" if name else "")
            self._draw()

    def _click(self, e):
        name = self._hit(e.x, e.y)
        W, H, cw, ch, x, y, *_ = self._geometry()
        if name == "confirm":
            self._confirm()
        elif name == "cancel" or not (x <= e.x <= x + cw and y <= e.y <= y + ch):
            self.close()

    def _confirm(self):
        callback = self.on_confirm
        self.close()
        if callback:
            self.root.after(40, callback)

    def close(self):
        if self.canvas is not None:
            try:
                self.canvas.destroy()
            except tk.TclError:
                pass
        self.canvas = None
        self.hits = []


# --------------------------------------------------------------- notifications
class NotificationPanel:
    """A small floating history. Clicking a row opens its section, never a file."""

    TYPE_COLORS = {"index": T.ACCENT, "installers": T.AMBER, "duplicates": T.AMBER,
                   "protection": T.GREEN, "blueprint": T.VIDEO_INK, "websites": T.ACCENT,
                   "errors": T.RED}
    TYPE_ICONS = {"index": "info", "installers": "installers", "duplicates": "installers",
                  "protection": "protection", "blueprint": "blueprint", "websites": "globe",
                  "errors": "warning"}

    def __init__(self, app):
        self.app = app
        self.top = None
        self.canvas = None
        self.rows = []
        self.clear_box = None
        self.close_box = None

    def toggle(self):
        if self.top is not None:
            self.close()
        else:
            self.show()

    def show(self):
        self.close()
        items = self.app.notifications.recent(30)
        self.app.notifications.mark_read()
        self.app.refresh_unread()
        width = T.s(392)
        row_h = T.s(64)
        height = min(T.s(474), max(T.s(196), T.s(84) + len(items) * row_h + T.s(54)))
        try:
            top = tk.Toplevel(self.app.root)
            top.withdraw()
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(bg=T.BG)
            c = tk.Canvas(top, width=width, height=height, bg=T.BG, highlightthickness=0, bd=0)
            c.pack()
            self.top, self.canvas = top, c
            self._draw(items, width, height, row_h)
            rx, ry = self.app.root.winfo_rootx(), self.app.root.winfo_rooty()
            rw = self.app.root.winfo_width()
            x = rx + rw - width - T.s(14)
            y = ry + T.s(16)
            top.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
            c.bind("<ButtonPress-1>", self._click)
            c.bind("<Motion>", self._move)
            c.bind("<Leave>", lambda e: c.configure(cursor=""))
            top.bind("<Escape>", lambda e: self.close())
            top.deiconify()
            tk.Misc.tkraise(top)
            c.focus_set()
        except tk.TclError:
            self.close()

    def _draw(self, items, width, height, row_h):
        c = self.canvas
        if not c:
            return
        c.delete("all")
        rr(c, 1, 1, width - 1, height - 2, T.s(16), fill=T.CARD, outline=T.LINE2)
        c.create_text(T.s(20), T.s(24), text="Notifications", font=T.F(13, "bold"), fill=T.TEXT,
                      anchor="w")
        c.create_text(T.s(20), T.s(45), text=f"{len(items)} recent  \u00b7  click one to open its section",
                      font=T.F(8), fill=T.FAINT, anchor="w")
        self.close_box = (width - T.s(34), T.s(12), width - T.s(12), T.s(34))
        c.create_line(width - T.s(23), T.s(18), width - T.s(17), T.s(24), fill=T.SUB,
                      width=T.s(1.5), capstyle="round")
        c.create_line(width - T.s(17), T.s(18), width - T.s(23), T.s(24), fill=T.SUB,
                      width=T.s(1.5), capstyle="round")
        c.create_line(T.s(14), T.s(60), width - T.s(14), T.s(60), fill=T.LINE)
        self.rows = []
        if not items:
            cy = height / 2 - T.s(6)
            circle(c, width / 2, cy, T.s(22), fill=T.TRACK, outline="")
            draw_glyph(c, "info", width / 2, cy, T.FAINT, T.s(19), width=T.s(1.8))
            c.create_text(width / 2, cy + T.s(38), text="Nothing new right now",
                          font=T.F(11, "bold"), fill=T.TEXT, anchor="center")
            c.create_text(width / 2, cy + T.s(57),
                          text="Finished scans, imports and protection changes appear here.",
                          font=T.F(8), fill=T.SUB, anchor="center")
            self.clear_box = None
            return
        y0 = T.s(66)
        for i, item in enumerate(items):
            y = y0 + i * row_h
            if y + row_h > height - T.s(46):
                break
            box = (T.s(8), y, width - T.s(8), y + row_h - T.s(4))
            self.rows.append((box, item))
            kind = item.get("type") or "index"
            col = self.TYPE_COLORS.get(kind, T.ACCENT)
            circle(c, T.s(28), y + T.s(26), T.s(15), fill=T.TRACK, outline="")
            draw_icon(c, self.TYPE_ICONS.get(kind, "info"), T.s(28), y + T.s(26), T.s(14), col)
            title_w = width - T.s(70)
            c.create_text(T.s(52), y + T.s(15), text=ellipsize(item.get("title", ""), 9, "bold",
                                                              title_w),
                          font=T.F(9, "bold"), fill=T.TEXT, anchor="w")
            body = item.get("body") or ""
            if body:
                c.create_text(T.s(52), y + T.s(33), text=ellipsize(body, 8, "normal", title_w),
                              font=T.F(8), fill=T.SUB, anchor="w")
            c.create_text(width - T.s(18), y + T.s(14), text=A.human_age(item.get("ts")),
                          font=T.F(7), fill=T.FAINT, anchor="e")
            if not item.get("read", True):
                circle(c, width - T.s(18), y + T.s(32), T.s(3), fill=T.ACCENT, outline="")
            if i < len(items) - 1:
                c.create_line(T.s(52), y + row_h - T.s(4), width - T.s(18), y + row_h - T.s(4),
                              fill=T.LINE)
        c.create_line(T.s(14), height - T.s(42), width - T.s(14), height - T.s(42), fill=T.LINE)
        self.clear_box = (width - T.s(96), height - T.s(36), width - T.s(14), height - T.s(8))
        c.create_text(width - T.s(20), height - T.s(22), text="Clear history",
                      font=T.F(8, "bold"), fill=T.SUB, anchor="e")

    def _row_at(self, x, y):
        for box, item in self.rows:
            x1, y1, x2, y2 = box
            if x1 <= x <= x2 and y1 <= y <= y2:
                return item
        return None

    def _hit(self, box, x, y):
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def _move(self, e):
        hot = bool(self._row_at(e.x, e.y)) or self._hit(self.clear_box, e.x, e.y) or \
            self._hit(self.close_box, e.x, e.y)
        self.canvas.configure(cursor="hand2" if hot else "")

    def _click(self, e):
        if self._hit(self.close_box, e.x, e.y):
            self.close()
            return
        if self._hit(self.clear_box, e.x, e.y):
            self.app.notifications.clear()
            self.app.refresh_unread()
            self.close()
            self.app.toast("Notification history cleared.", "good")
            return
        item = self._row_at(e.x, e.y)
        if item:
            self.app.open_notification(item)

    def close(self):
        if self.top is not None:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
        self.top, self.canvas = None, None
        self.rows = []
        self.clear_box = self.close_box = None


# ----------------------------------------------------------------------- app
class App:
    def __init__(self, root, state, index, on_quit=None, initial_page=None):
        self.root, self.state, self.index = root, state, index
        self.on_quit_cb = on_quit
        self._closing = False
        self._watcher_started = False
        self._watch_after = None
        self._drive_after = None
        self._open_poll = None
        self.current = None
        A.ensure_dirs()
        self.motion = Motion(root, enabled=not reduced_motion())
        self.jobs = Jobs(root)
        self.toast = Toast(root)
        self.sheet = ConfirmSheet(self)
        try:
            self.protection = P.Protection()
        except Exception:
            self.protection = P.Protection(path=os.path.join(A.APP_DIR, "protection.json"))
        try:
            self.websites = W.WebsiteMemory()
        except Exception:
            self.websites = W.WebsiteMemory(path=os.path.join(A.APP_DIR, "websites.json"))
        self.notifications = N.Notifications(windows=bool(state.get("windows_notifications", True)))
        self.notifications.on_new = self._notification_event
        self.notification_panel = NotificationPanel(self)

        root.title("ClickScope")
        root.configure(bg=T.BG)
        try:
            root.iconbitmap(A.resource_path("assets/app.ico"))
        except tk.TclError:
            pass

        self.logo = None
        try:
            self.logo = tk.PhotoImage(file=A.resource_path("assets/logo_40.png"))
        except tk.TclError:
            pass
        self.sidebar = NavRail(root, self.motion, self.show, logo=self.logo,
                               on_notify=self.toggle_notifications)
        self.sidebar.configure(width=T.s(224))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.main = tk.Frame(root, bg=T.BG)
        self.main.pack(side="left", fill="both", expand=True)

        self.search = pages.SearchPage(self.main, self)
        self.installers = pages.InstallersPage(self.main, self)
        self.protection_page = pages.ProtectionPage(self.main, self)
        self.websites_page = pages.WebsitesPage(self.main, self)
        self.blueprint = pages.BlueprintPage(self.main, self)
        self.settings = pages.SettingsPage(self.main, self)
        self.pages = {"search": self.search, "installers": self.installers,
                      "protection": self.protection_page, "websites": self.websites_page,
                      "blueprint": self.blueprint, "settings": self.settings}
        for page in self.pages.values():
            page.place(x=0, y=0, relwidth=1, relheight=1)

        self.show(initial_page if initial_page in self.pages else "search")
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(80, self.refresh_status)
        root.after(650, self.start_watcher)
        root.after(1200, self._sync_drives)
        self._poll_open_request()

    # ---------------------------------------------------------------- chrome
    def _bind_keys(self):
        self.root.bind_all("<Control-k>", self._key_search)
        self.root.bind_all("<Control-K>", self._key_search)
        order = ("search", "installers", "protection", "websites", "blueprint", "settings")
        for i, key in enumerate(order, start=1):
            self.root.bind_all(f"<Control-Key-{i}>", lambda e, k=key: self.show(k))
        self.root.bind_all("<Control-q>", lambda e: self.quit())

    def _key_search(self, e=None):
        self.show("search")
        self.search.after(80, self.search._focus_field)
        return "break"

    def show(self, key):
        page = self.pages.get(key)
        if page is None or self._closing:
            return
        if self.current and self.current != key:
            try:
                self.pages[self.current].on_hide()
            except Exception:
                pass
        self.notification_panel.close()
        for p in self.pages.values():
            p.lower()
        tk.Misc.tkraise(page)
        self.sidebar.select(key, notify=False)
        self.current = key
        try:
            page.on_show()
        except Exception:
            pass

    # ----------------------------------------------------------- notifications
    def notify(self, ntype, title, body="", target=""):
        """Record a notification and show a Windows toast when allowed."""
        if self._closing:
            return None
        if threading.current_thread() is not threading.main_thread():
            self.jobs.post(lambda: self.notify(ntype, title, body, target))
            return None
        try:
            item = self.notifications.emit(ntype, title, body, target)
        except Exception:
            item = None
        self.refresh_unread()
        return item

    def _notification_event(self, item):
        if threading.current_thread() is not threading.main_thread():
            self.jobs.post(self.refresh_unread)
        else:
            self.refresh_unread()

    def refresh_unread(self):
        if self._closing:
            return
        try:
            self.sidebar.set_unread(self.notifications.unread_count())
        except Exception:
            pass

    def toggle_notifications(self):
        if self._closing:
            return
        self.notification_panel.toggle()

    def open_notification(self, item):
        self.notification_panel.close()
        try:
            self.notifications.mark_read(item.get("id"))
        except Exception:
            pass
        self.refresh_unread()
        target = str(item.get("target") or "search")
        self.open_target(target)

    def open_target(self, target):
        target = str(target or "").strip()
        if target.lower().startswith("clickscope:"):
            target = target.split(":", 1)[1]
        target = target.strip("/ ").lower()
        if target in ("notifications", "bell"):
            self.toggle_notifications()
            return
        if target not in self.pages:
            target = "search"
        self.show(target)
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def _poll_open_request(self):
        self._open_poll = None
        if self._closing:
            return
        try:
            target = A.take_open_request()
            if target:
                self.open_target(target)
        except Exception:
            pass
        try:
            self._open_poll = self.root.after(900, self._poll_open_request)
        except tk.TclError:
            self._open_poll = None

    # ----------------------------------------------------------------- state
    def refresh_status(self):
        try:
            st = self.index.stats(cache=False)
            building = self.index.is_building()
        except Exception:
            st, building = {}, False
        if building:
            p = self.index.progress()
            title, sub, color = "Indexing\u2026", f"{p.get('files', 0):,} files found", T.ACCENT
        elif st.get("files", 0):
            title = "Index ready"
            sub = f"{st['files']:,} files  \u00b7  {A.human_age(st.get('last_build'))}"
            color = T.GREEN
        else:
            title, sub, color = "Not indexed", "One scan makes search instant", T.AMBER
        if getattr(self.sidebar, "status", None) != (title, sub, color):
            self.sidebar.set_status(title, sub, color)
        self.refresh_unread()

    def post(self, fn):
        self.jobs.post(fn)

    def confirm(self, title, body, detail="", confirm="Continue", tone="primary", on_confirm=None):
        self.sheet.ask(title, body, detail=detail, confirm=confirm, tone=tone, on_confirm=on_confirm)

    # --------------------------------------------------------------- watcher
    def start_watcher(self):
        if self._watcher_started or self._closing:
            return
        try:
            self._watcher_started = self.index.start_watcher(on_change=self._watch_ping)
        except Exception:
            self._watcher_started = False

    def _watch_ping(self):
        self.post(self._watch_schedule)

    def _watch_schedule(self):
        if self._closing:
            return
        if self._watch_after is not None:
            try:
                self.root.after_cancel(self._watch_after)
            except Exception:
                pass
        self._watch_after = self.root.after(900, self._watch_apply)

    def _watch_apply(self):
        self._watch_after = None
        if self._closing:
            return
        self.refresh_status()
        if self.current == "search":
            self.search.on_index_changed()
        elif self.current == "installers":
            self.installers.on_index_changed()
        elif self.current == "settings":
            self.settings.on_index_changed()
        elif self.current == "protection":
            self.protection_page.refresh()
        elif self.current == "websites":
            self.websites_page.refresh()

    # ---------------------------------------------------------- external drives
    def _schedule_drive_check(self):
        if self._closing:
            return
        if self._drive_after is not None:
            try:
                self.root.after_cancel(self._drive_after)
            except Exception:
                pass
        self._drive_after = self.root.after(45000, self._sync_drives)

    def _sync_drives(self):
        """Notice unplugged and reconnected drives without a full manual rescan."""
        self._drive_after = None
        if self._closing:
            return
        try:
            result = self.index.sync_roots()
        except Exception:
            result = {}
        if self._closing:
            return
        if result.get("missing"):
            self._watch_apply()
        added = [r for r in (result.get("added") or []) if os.path.isdir(r)]
        if added and not self.index.is_building():
            names = ", ".join(os.path.basename(r.rstrip("\\/")) or r for r in added[:3])
            self.notify("index", "Drive connected",
                        f"{names} is back. Adding its files to the index.", "search")
            self.toast(f"Indexing {names} again.", "info")
            self.index.build_async(roots=added, reset=False, preserve_roots=True,
                                   on_done=lambda ok, st: self.post(
                                       lambda: self._drives_indexed(ok, st)))
        self._schedule_drive_check()

    def _drives_indexed(self, ok, stats):
        if self._closing:
            return
        self.refresh_status()
        if self.current == "search":
            self.search.on_index_changed()
        elif self.current == "installers":
            self.installers.on_index_changed()
        elif self.current == "settings":
            self.settings.on_index_changed()
        if ok:
            self.notify("index", "External drive indexed",
                        f"{stats.get('files', 0):,} files are searchable again.", "search")

    # --------------------------------------------------------------- actions
    def rebuild_index(self):
        self.show("search")
        self.search.after(100, self.search._build)

    def clear_index(self):
        if self.index.is_building():
            self.toast("Stop indexing before removing the index.", "warn")
            return

        def clear():
            try:
                self.index.stop_watcher()
            except Exception:
                pass
            self._watcher_started = False
            try:
                self.index.clear()
            except Exception as e:
                self.toast(f"Could not remove the index: {e}", "error")
                return
            self.search.on_index_changed()
            self.installers.on_index_changed()
            self.settings.on_index_changed()
            self.refresh_status()
            self.toast("Search index removed. Your files were not touched.", "good")
            self.notify("index", "Search index removed",
                        "Your files were not touched. Build the index again whenever you like.", "search")

        self.confirm(
            "Remove the search index?",
            "ClickScope will forget the file names it has indexed. Your files are not touched, and you can "
            "build the index again at any time.",
            detail="Search will be empty until you rebuild.",
            confirm="Remove index", tone="danger", on_confirm=clear)

    def set_autostart(self, on):
        set_autostart(on)

    def autostart_enabled(self):
        return autostart_enabled()

    # ----------------------------------------------------------------- close
    def on_close(self):
        if bool(self.state.get("keep_running", True)):
            self.root.iconify()
        else:
            self.quit()

    def quit(self):
        if self._closing:
            return
        self._closing = True
        try:
            self.notification_panel.close()
            if self._open_poll is not None:
                self.root.after_cancel(self._open_poll)
            if self._drive_after is not None:
                self.root.after_cancel(self._drive_after)
                self._drive_after = None
            self.jobs.close()
            self.toast.close()
            self.sheet.close()
            self.index.close()
        except Exception:
            pass
        if self.on_quit_cb:
            try:
                self.on_quit_cb()
            except Exception:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

