"""The floating Universal Search bar.

One small, top-most panel that appears over whatever you are doing. It searches
the local file index plus the Start Menu list, and can open or reveal a result.
It never deletes, moves or uploads anything, and it is only shown by the user's
own shortcut (or from Settings).
"""
import ctypes
import os
import tkinter as tk

import appdata as A
import theme as T
from uikit import draw_file_icon, draw_icon, ellipsize, measure, rr

HEADER = 60
ROW = 50
SECTION = 24
FOOTER = 36
PAD = 22
MAX_ROWS = 9


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


def _work_area():
    """The usable rectangle of the monitor under the mouse (multi-monitor aware)."""
    try:
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        mon = user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    try:
        root = tk._get_default_root()
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
    except Exception:
        return 0, 0, 1280, 800


class QuickBar:
    def __init__(self, app):
        self.app = app
        self.top = None
        self.cv = None
        self.entry = None
        self.var = None
        self.placeholder = None
        self.results = []
        self.app_count = 0
        self.sel = 0
        self.hover = -1
        self.width = T.s(600)
        self._height = 0
        self._x = self._y = 0
        self._gen = 0
        self._typing_after = None
        self._setting = False
        self._visible = False
        self._rows = []

    # ------------------------------------------------------------------ build
    def _ensure(self):
        if self.top is not None:
            return
        self.top = tk.Toplevel(self.app.root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.configure(bg=T.CARD)
        try:
            self.top.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.top, bg=T.CARD, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.var = tk.StringVar(master=self.cv)
        self.entry = tk.Entry(self.cv, textvariable=self.var, font=T.F(14), relief="flat", bd=0,
                              bg=T.CARD, fg=T.TEXT, insertbackground=T.TEXT,
                              highlightthickness=0, selectbackground=T.ACCENT_MID,
                              selectforeground=T.TEXT)
        self.entry.place(x=T.s(50), y=T.s(14), height=T.s(32))
        self.placeholder = tk.Label(self.cv, text="Search files, folders and apps",
                                    font=T.F(14), fg=T.FAINT, bg=T.CARD, anchor="w",
                                    cursor="xterm")
        self.placeholder.place(x=T.s(52), y=T.s(16))
        self.entry.bind("<KeyRelease>", self._changed)
        self.entry.bind("<Down>", lambda e: self._move(1))
        self.entry.bind("<Up>", lambda e: self._move(-1))
        self.entry.bind("<Return>", lambda e: self._open_selected())
        self.entry.bind("<KP_Enter>", lambda e: self._open_selected())
        self.entry.bind("<Control-Return>", lambda e: self._reveal_selected())
        self.entry.bind("<Control-KP_Enter>", lambda e: self._reveal_selected())
        self.entry.bind("<Escape>", lambda e: self.hide())
        self.entry.bind("<FocusOut>", lambda e: self._show_placeholder())
        self.placeholder.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.cv.bind("<Button-1>", self._click)
        self.cv.bind("<Motion>", self._motion)
        self.cv.bind("<Leave>", self._leave)
        self.cv.bind("<MouseWheel>", lambda e: self._wheel(e))
        self.top.bind("<Escape>", lambda e: self.hide())
        self.top.bind("<FocusOut>", self._focus_out)
        self._round_corners()

    def _round_corners(self):
        """Windows 11 rounded corners, quietly ignored elsewhere."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.top.winfo_id())
            pref = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref),
                                                       ctypes.sizeof(pref))
        except Exception:
            pass

    # ------------------------------------------------------------------- show
    def show(self):
        if self.app._closing:
            return
        self._ensure()
        x, y, w, h = _work_area()
        self.width = max(T.s(430), min(T.s(600), w - T.s(40)))
        self._x = x + (w - self.width) // 2
        self._y = y + max(T.s(30), int(h * 0.14))
        self._visible = True
        self._reset()
        self._place_entry()
        self.top.deiconify()
        self.top.lift()
        try:
            self.top.attributes("-topmost", True)
            self.top.focus_force()
        except tk.TclError:
            pass
        self.entry.focus_set()
        self.top.after(30, self._focus_entry)
        try:
            if self.app.apps is not None:
                self.app.jobs.run(lambda: self.app.apps.refresh_if_stale(900))
        except Exception:
            pass

    def _focus_entry(self):
        if not self._visible:
            return
        try:
            self.entry.focus_force()
        except tk.TclError:
            pass

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def hide(self):
        self._visible = False
        if self._typing_after is not None and self.top is not None:
            try:
                self.top.after_cancel(self._typing_after)
            except Exception:
                pass
            self._typing_after = None
        self._gen += 1
        if self.top is not None:
            try:
                self.top.withdraw()
            except tk.TclError:
                pass

    def close(self):
        self.hide()
        if self.top is not None:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
            self.top = None

    # ------------------------------------------------------------------ entry
    def _reset(self):
        self._setting = True
        try:
            self.var.set("")
        except tk.TclError:
            pass
        self._setting = False
        self.results = []
        self.app_count = 0
        self.sel = 0
        self.hover = -1
        self._show_placeholder()
        self._render()

    def _hide_placeholder(self):
        try:
            self.placeholder.place_forget()
        except Exception:
            pass

    def _show_placeholder(self):
        if self.top is None or not self._visible:
            return
        try:
            if not self.var.get().strip():
                self.placeholder.place(x=T.s(52), y=T.s(16))
        except Exception:
            pass

    def _place_entry(self):
        self.entry.place(x=T.s(50), y=T.s(14), height=T.s(32), width=self.width - T.s(126))

    def _changed(self, e=None):
        if e is not None and getattr(e, "keysym", "") in ("Up", "Down", "Return", "KP_Enter",
                                                         "Escape", "Control_L", "Control_R"):
            return
        if self._setting:
            return
        query = self.var.get().strip()
        if query:
            self._hide_placeholder()
        if self._typing_after is not None:
            try:
                self.top.after_cancel(self._typing_after)
            except Exception:
                pass
            self._typing_after = None
        if not query:
            self._gen += 1
            self.results, self.app_count = [], 0
            self.sel = 0
            self._show_placeholder()
            self._render()
            return
        self._typing_after = self.top.after(90, lambda q=query: self._search(q))

    # ----------------------------------------------------------------- search
    def _search(self, query):
        self._typing_after = None
        self._gen += 1
        gen = self._gen
        try:
            apps = self.app.apps.search(query, limit=3) if self.app.apps else []
        except Exception:
            apps = []

        def work():
            try:
                files = self.app.index.search(query, limit=20) if self.app.index else []
            except Exception:
                files = []
            return apps, files

        self.app.jobs.run(work, on_done=lambda pair: self._results(gen, query, pair))

    def _results(self, gen, query, pair):
        if gen != self._gen or not self._visible:
            return
        apps, files = pair
        if self.var.get().strip() != query:
            return
        items = [dict(a) for a in apps]
        seen = {i.get("path") for i in items}
        for f in files:
            if f.get("path") in seen:
                continue
            seen.add(f.get("path"))
            items.append(f)
        self.results = items[:MAX_ROWS]
        self.app_count = min(len(apps), len(self.results))
        self.sel = 0
        self.hover = -1
        self._render()

    # ------------------------------------------------------------------- draw
    def _render(self):
        if self.cv is None:
            return
        c = self.cv
        c.delete("all")
        w = self.width
        query = self.var.get().strip() if self.var is not None else ""
        c.configure(width=w)

        # Panel edge and header.
        c.create_rectangle(0, 0, w, 2000, fill=T.CARD, outline="")
        c.create_rectangle(0, 0, w - 1, 2000, fill="", outline=T.LINE2)
        draw_icon(c, "search", T.s(28), T.s(30), T.s(18), T.FAINT)
        c.create_line(0, HEADER - 1, w, HEADER - 1, fill=T.LINE)
        esc_w = measure("Esc", 8, "bold") + T.s(18)
        rr(c, w - T.s(18) - esc_w, T.s(13), w - T.s(18), T.s(37), T.s(7), fill=T.TRACK, outline="")
        c.create_text(w - T.s(18) - esc_w / 2, T.s(25), text="Esc", font=T.F(8, "bold"),
                      fill=T.SUB, anchor="center")

        layout, total = self._layout()
        self._rows = layout
        if query and not self.results:
            total = HEADER + T.s(96) + FOOTER
            cy = HEADER + T.s(40)
            c.create_text(w / 2, cy, text=f"No matches for \u201c{ellipsize(query, 10, 'bold', w - T.s(80))}\u201d",
                          font=T.F(11, "bold"), fill=T.TEXT, anchor="center")
            c.create_text(w / 2, cy + T.s(24), text="Try a shorter word, or a different spelling.",
                          font=T.F(9), fill=T.FAINT, anchor="center")
        elif not query:
            total = HEADER + T.s(118) + FOOTER
            cy = HEADER + T.s(40)
            c.create_oval(w / 2 - T.s(22), cy - T.s(22), w / 2 + T.s(22), cy + T.s(22),
                          fill=T.ACCENT_SOFT, outline="")
            draw_icon(c, "search", w / 2, cy, T.s(20), T.ACCENT_D)
            c.create_text(w / 2, cy + T.s(40), text="Search files, folders and apps",
                          font=T.F(11, "bold"), fill=T.TEXT, anchor="center")
            c.create_text(w / 2, cy + T.s(60),
                          text="Uses the local index and your Start Menu. Nothing leaves this PC.",
                          font=T.F(9), fill=T.FAINT, anchor="center",
                          width=max(T.s(260), w - T.s(80)))
        else:
            for kind, value, y in layout:
                if kind == "section":
                    c.create_text(T.s(24), y + T.s(15), text=value, font=T.F(8, "bold"),
                                  fill=T.FAINT, anchor="w")
                    x1 = T.s(24) + measure(value, 8, "bold") + T.s(10)
                    c.create_line(x1, y + T.s(15), w - T.s(24), y + T.s(15), fill=T.LINE)
                else:
                    self._draw_row(c, value, y)

        # Footer.
        top = total - FOOTER
        c.create_line(0, top, w, top, fill=T.LINE)
        hint = "Up / Down choose      Enter open      Ctrl+Enter show in folder      Esc close"
        c.create_text(T.s(20), top + T.s(18), text=hint, font=T.F(8), fill=T.FAINT, anchor="w")
        c.create_text(w - T.s(20), top + T.s(18), text="Local only", font=T.F(8, "bold"),
                      fill=T.GREEN, anchor="e")

        if total != self._height:
            self._height = total
            self.top.geometry(f"{w}x{total}+{self._x}+{self._y}")
        else:
            self.top.geometry(f"+{self._x}+{self._y}")

    def _draw_row(self, c, index, y):
        item = self.results[index]
        selected = index == self.sel
        hover = index == self.hover
        if selected:
            rr(c, T.s(8), y + T.s(2), self.width - T.s(8), y + ROW - T.s(2), T.s(10),
               fill=T.ACCENT_SOFT, outline="")
        elif hover:
            rr(c, T.s(8), y + T.s(2), self.width - T.s(8), y + ROW - T.s(2), T.s(10),
               fill=T.HOVER, outline="")
        kind = "app" if item.get("source") else ("folder" if item.get("is_dir") else
                                                item.get("kind") or "other")
        draw_file_icon(c, kind, T.s(24), y + T.s(10), T.s(30))
        name_x = T.s(66)
        avail = self.width - name_x - T.s(24)
        name = item.get("name") or os.path.basename(item.get("path") or "") or item.get("path", "")
        c.create_text(name_x, y + T.s(18), text=ellipsize(name, 11, "bold", avail),
                      font=T.F(11, "bold"), fill=T.TEXT, anchor="w")
        sub = self._subtitle(item)
        c.create_text(name_x, y + T.s(34), text=ellipsize(sub, 8, "normal", avail),
                      font=T.F(8), fill=T.FAINT, anchor="w")

    def _subtitle(self, item):
        if item.get("source"):
            return "App  \u00b7  " + str(item.get("source") or "Start Menu")
        path = item.get("path") or ""
        folder = os.path.dirname(path)
        kind = "Folder" if item.get("is_dir") else (str(item.get("ext") or "").lstrip(".").upper()
                                                    or "File")
        where = A.shorten_path(folder, 58)
        return f"{kind}  \u00b7  {where}" if where else kind

    def _layout(self):
        """[(kind, value, y)] for rows and captions, plus the window height."""
        if not self.results:
            return [], HEADER + T.s(96) + FOOTER
        items, y = [], HEADER + T.s(6)
        files = len(self.results) - self.app_count
        if self.app_count:
            items.append(("section", "APPS", y))
            y += SECTION
            for i in range(self.app_count):
                items.append(("row", i, y))
                y += ROW
        if files:
            if self.app_count:
                y += T.s(6)
            items.append(("section", "FILES & FOLDERS", y))
            y += SECTION
            for i in range(self.app_count, len(self.results)):
                items.append(("row", i, y))
                y += ROW
        y += T.s(8)
        return items, y + FOOTER

    # ------------------------------------------------------------------ input
    def _row_at(self, y):
        for kind, value, top in self._rows:
            if kind == "row" and top <= y < top + ROW:
                return value
        return None

    def _click(self, e):
        if e.y < HEADER:
            chip_w = measure("Esc", 8, "bold") + T.s(18)
            if e.x >= self.width - T.s(18) - chip_w:
                self.hide()
            return
        index = self._row_at(e.y)
        if index is None:
            return
        self.sel = index
        self._open_selected()

    def _motion(self, e):
        index = self._row_at(e.y)
        if index != self.hover:
            self.hover = index
            self._render()

    def _leave(self, e=None):
        if self.hover != -1:
            self.hover = -1
            self._render()

    def _wheel(self, e):
        if not self.results or self.top is None:
            return "break"
        self._move(-1 if e.delta > 0 else 1)
        return "break"

    def _move(self, delta):
        if not self.results:
            return "break"
        self.sel = (self.sel + delta) % len(self.results)
        self.hover = -1
        self._render()
        return "break"

    def _selected(self):
        if not self.results:
            return None
        self.sel = max(0, min(self.sel, len(self.results) - 1))
        return self.results[self.sel]

    def _open_selected(self):
        item = self._selected()
        if item is None:
            return "break"
        path = item.get("path") or ""
        self.hide()
        if not os.path.exists(path):
            self.app.toast("That item moved or was removed.", "warn")
            return "break"
        if not A.open_path(path):
            self.app.toast("Windows could not open that item.", "error")
        return "break"

    def _reveal_selected(self):
        item = self._selected()
        if item is None:
            return "break"
        path = item.get("path") or ""
        self.hide()
        if not os.path.exists(path) or not A.reveal_path(path):
            self.app.toast("Windows could not show that item.", "error")
        return "break"

    def _focus_out(self, e=None):
        if self.top is None:
            return
        try:
            self.top.after(120, self._hide_if_unfocused)
        except tk.TclError:
            pass

    def _hide_if_unfocused(self):
        if not self._visible or self.top is None:
            return
        try:
            focus = self.top.focus_displayof()
        except Exception:
            focus = None
        if focus is None:
            self.hide()
        else:
            try:
                if focus.winfo_toplevel() is not self.top:
                    self.hide()
            except Exception:
                self.hide()
