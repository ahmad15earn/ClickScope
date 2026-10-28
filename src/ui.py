"""ClickScope UI (Tkinter, light theme only)."""
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

from core import APP_DIR, build_suggestions, fmt_hour, resource_path

BG = "#F5F8FB"
CARD = "#FFFFFF"
BORDER = "#E3EAF0"
TEXT = "#0F1B2D"
MUTED = "#64748B"
TRACK = "#EAF2F7"
ACCENT = "#00D8F2"
ACCENT_DARK = "#0891B2"
GREEN = "#16A34A"
AMBER = "#D97706"
LEVEL_COLORS = {"tip": ACCENT, "info": "#94A3B8", "good": "#22C55E", "warn": "#F59E0B"}

FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_S = ("Segoe UI", 9)
FONT_H = ("Segoe UI", 11, "bold")
FONT_T = ("Segoe UI", 18, "bold")
FONT_N = ("Segoe UI Semibold", 22)

SCALE = 1.0


def init_scale(root):
    global SCALE
    try:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        SCALE = 1.0


def s(n):
    return int(round(n * SCALE))


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


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
        cmd = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}" --minimized'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "ClickScope", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "ClickScope")
            except FileNotFoundError:
                pass


class FlatButton(tk.Label):
    def __init__(self, parent, text, command, bg=TEXT, fg="#FFFFFF", hover="#1E3350", **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=FONT_B, padx=s(16), pady=s(7),
                         cursor="hand2", **kw)
        self.command, self.base, self.hover = command, bg, hover
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.base))

    def restyle(self, text, bg, fg, hover):
        self.base, self.hover = bg, hover
        self.config(text=text, bg=bg, fg=fg)


def card(parent, **kw):
    return tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1, **kw)


class ListCard(tk.Frame):
    """A titled card listing items with proportional bars. Toggle Most / Least."""

    def __init__(self, parent, title, on_mode):
        super().__init__(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.mode, self.on_mode, self.sig = "most", on_mode, None
        head = tk.Frame(self, bg=CARD)
        head.pack(fill="x", padx=s(16), pady=(s(14), s(6)))
        tk.Label(head, text=title, font=FONT_H, fg=TEXT, bg=CARD).pack(side="left")
        self.btns = {}
        for m, t in (("least", "Least"), ("most", "Most")):
            lb = tk.Label(head, text=t, font=FONT_S, cursor="hand2", bg=CARD)
            lb.pack(side="right", padx=(s(10), 0))
            lb.bind("<Button-1>", lambda e, m=m: self.set_mode(m))
            self.btns[m] = lb
        self.body = tk.Frame(self, bg=CARD)
        self.body.pack(fill="both", expand=True, padx=s(16), pady=(0, s(12)))
        self._style()

    def _style(self):
        for m, lb in self.btns.items():
            on = m == self.mode
            lb.config(fg=ACCENT_DARK if on else MUTED, font=FONT_B if on else FONT_S)

    def set_mode(self, m):
        self.mode = m
        self._style()
        self.on_mode()

    def update_rows(self, rows, empty):
        sig = (tuple(rows), self.mode, empty)
        if sig == self.sig:
            return
        self.sig = sig
        for w in self.body.winfo_children():
            w.destroy()
        if not rows:
            tk.Label(self.body, text=empty, font=FONT, fg=MUTED, bg=CARD, justify="left",
                     wraplength=s(330)).pack(anchor="w", pady=s(8))
            return
        mx = max(n for _, n in rows) or 1
        for name, n in rows:
            r = tk.Frame(self.body, bg=CARD)
            r.pack(fill="x", pady=s(4))
            top = tk.Frame(r, bg=CARD)
            top.pack(fill="x")
            tk.Label(top, text=name if len(name) <= 30 else name[:29] + "\u2026", font=FONT,
                     fg=TEXT, bg=CARD, anchor="w").pack(side="left")
            tk.Label(top, text=f"{n:,}", font=FONT_B, fg=TEXT, bg=CARD).pack(side="right")
            track = tk.Frame(r, bg=TRACK, height=s(6))
            track.pack(fill="x", pady=(s(3), 0))
            track.pack_propagate(False)
            bar = tk.Frame(track, bg=ACCENT)
            bar.place(x=0, y=0, relheight=1, relwidth=max(0.03, n / mx))


class App:
    def __init__(self, root, store, tracker):
        self.root, self.store, self.tracker = root, store, tracker
        self.rng, self.tab = "today", "overview"
        self.sug_sig = None

        self._header()
        self._nav()
        self.body = tk.Frame(root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=s(28), pady=(s(16), s(20)))
        self.pages = {
            "overview": self._page_overview(),
            "suggestions": self._page_suggestions(),
            "settings": self._page_settings(),
        }
        self.show_tab("overview")
        self.tick()

    # ------------------------------------------------------------- chrome
    def _header(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=s(28), pady=(s(22), s(10)))
        logo_file = "assets/logo_80.png" if SCALE >= 1.4 else "assets/logo_40.png"
        try:
            self.logo = tk.PhotoImage(file=resource_path(logo_file))
            tk.Label(hdr, image=self.logo, bg=BG).pack(side="left", padx=(0, s(12)))
        except Exception:
            pass
        t = tk.Frame(hdr, bg=BG)
        t.pack(side="left")
        tk.Label(t, text="ClickScope", font=FONT_T, fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(t, text="See where your clicks go", font=FONT_S, fg=MUTED, bg=BG).pack(anchor="w")

        self.btn_pause = FlatButton(hdr, "Pause", self.toggle_pause)
        self.btn_pause.pack(side="right")
        self.status = tk.Label(hdr, text="", font=FONT_B, bg=BG)
        self.status.pack(side="right", padx=(0, s(16)))

    def _nav(self):
        nav = tk.Frame(self.root, bg=BG)
        nav.pack(fill="x", padx=s(28))
        self.tab_widgets = {}
        for key, label in (("overview", "Overview"), ("suggestions", "Suggestions"), ("settings", "Settings")):
            f = tk.Frame(nav, bg=BG, cursor="hand2")
            f.pack(side="left", padx=(0, s(22)))
            lb = tk.Label(f, text=label, font=FONT_B, bg=BG, cursor="hand2")
            lb.pack(pady=(s(4), s(6)))
            ind = tk.Frame(f, bg=BG, height=s(3))
            ind.pack(fill="x")
            for w in (f, lb, ind):
                w.bind("<Button-1>", lambda e, k=key: self.show_tab(k))
            self.tab_widgets[key] = (lb, ind)

        seg = tk.Frame(nav, bg=BORDER, padx=1, pady=1)
        seg.pack(side="right", pady=(0, s(6)))
        self.seg = {}
        for key, label in (("today", "Today"), ("7d", "7 days"), ("all", "All time")):
            lb = tk.Label(seg, text=label, font=FONT_S, padx=s(12), pady=s(4), cursor="hand2")
            lb.pack(side="left")
            lb.bind("<Button-1>", lambda e, k=key: self.set_range(k))
            self.seg[key] = lb
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=s(28))
        self._style_nav()

    def _style_nav(self):
        for k, (lb, ind) in self.tab_widgets.items():
            on = k == self.tab
            lb.config(fg=TEXT if on else MUTED)
            ind.config(bg=ACCENT if on else BG)
        for k, lb in self.seg.items():
            on = k == self.rng
            lb.config(bg=TEXT if on else CARD, fg="#FFFFFF" if on else MUTED)

    def show_tab(self, key):
        self.tab = key
        for k, p in self.pages.items():
            p.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        self._style_nav()
        self.sug_sig = None
        self.refresh()

    def set_range(self, key):
        self.rng = key
        self._style_nav()
        self.sug_sig = None
        self.refresh()

    def toggle_pause(self):
        self.tracker.paused = not self.tracker.paused
        self.refresh()

    # ------------------------------------------------------------ overview
    def _page_overview(self):
        page = tk.Frame(self.body, bg=BG)
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x")
        self.stats = {}
        for i, (key, title) in enumerate((("total", "Total clicks"), ("apps", "Apps used"),
                                          ("sites", "Websites"), ("peak", "Busiest hour"))):
            c = card(row)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else s(12), 0))
            row.columnconfigure(i, weight=1, uniform="stat")
            tk.Label(c, text=title, font=FONT_S, fg=MUTED, bg=CARD).pack(anchor="w", padx=s(16), pady=(s(14), 0))
            v = tk.Label(c, text="\u2013", font=FONT_N, fg=TEXT, bg=CARD)
            v.pack(anchor="w", padx=s(16), pady=(0, s(12)))
            self.stats[key] = v

        lists = tk.Frame(page, bg=BG)
        lists.pack(fill="both", expand=True, pady=(s(14), 0))
        lists.columnconfigure(0, weight=1, uniform="lst")
        lists.columnconfigure(1, weight=1, uniform="lst")
        lists.rowconfigure(0, weight=1)
        self.card_apps = ListCard(lists, "Applications", self.refresh)
        self.card_apps.grid(row=0, column=0, sticky="nsew", padx=(0, s(7)))
        self.card_sites = ListCard(lists, "Websites", self.refresh)
        self.card_sites.grid(row=0, column=1, sticky="nsew", padx=(s(7), 0))
        return page

    def _refresh_overview(self):
        r = self.rng
        self.stats["total"].config(text=f"{self.store.total(r):,}")
        self.stats["apps"].config(text=str(self.store.count("app", r)))
        self.stats["sites"].config(text=str(self.store.count("site", r)))
        self.stats["peak"].config(text=fmt_hour(self.store.busiest_hour(r)))
        for kind, c, empty in (
                ("app", self.card_apps, "No clicks yet. Use your PC as usual and they will show up here."),
                ("site", self.card_sites,
                 "No website clicks yet. Click around in your browser."
                 if self.store.get("track_sites", "1") == "1" else
                 "Website tracking is turned off in Settings.")):
            rows = self.store.top(kind, r, 8, desc=(c.mode == "most"))
            c.update_rows(rows, empty)

    # --------------------------------------------------------- suggestions
    def _page_suggestions(self):
        page = tk.Frame(self.body, bg=BG)
        self.sug_box = tk.Frame(page, bg=BG)
        self.sug_box.pack(fill="both", expand=True)
        return page

    def _refresh_suggestions(self):
        items = build_suggestions(self.store, self.rng)
        sig = (self.rng, tuple((i["title"], i["text"]) for i in items))
        if sig == self.sug_sig:
            return
        self.sug_sig = sig
        for w in self.sug_box.winfo_children():
            w.destroy()
        for it in items:
            c = card(self.sug_box)
            c.pack(fill="x", pady=(0, s(10)))
            tk.Frame(c, bg=LEVEL_COLORS.get(it["level"], ACCENT), width=s(5)).pack(side="left", fill="y")
            inner = tk.Frame(c, bg=CARD)
            inner.pack(side="left", fill="x", expand=True, padx=s(16), pady=s(12))
            tk.Label(inner, text=it["title"], font=FONT_H, fg=TEXT, bg=CARD, anchor="w").pack(fill="x")
            body = tk.Label(inner, text=it["text"], font=FONT, fg=MUTED, bg=CARD, anchor="w", justify="left")
            body.pack(fill="x", pady=(s(3), 0))
            body.bind("<Configure>", lambda e, l=body: l.config(wraplength=max(100, e.width - 4)))

    # ------------------------------------------------------------ settings
    def _page_settings(self):
        page = tk.Frame(self.body, bg=BG)
        c = card(page)
        c.pack(fill="x")
        inner = tk.Frame(c, bg=CARD)
        inner.pack(fill="x", padx=s(18), pady=s(14))

        self.var_sites = tk.BooleanVar(value=self.store.get("track_sites", "1") == "1")
        self.var_auto = tk.BooleanVar(value=autostart_enabled())
        for var, text, cmd in (
                (self.var_sites, "Count clicks per website (uses the browser tab title, never the URL)", self._on_sites),
                (self.var_auto, "Start ClickScope with Windows (starts minimized)", self._on_auto)):
            tk.Checkbutton(inner, text=text, variable=var, command=cmd, font=FONT, fg=TEXT, bg=CARD,
                           activebackground=CARD, selectcolor="#FFFFFF", anchor="w", cursor="hand2"
                           ).pack(fill="x", pady=s(3))

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(s(14), 0))
        FlatButton(row, "Export CSV", self._export, bg=TEXT).pack(side="left")
        FlatButton(row, "Open data folder", lambda: self._open_folder(), bg=TRACK, fg=TEXT,
                   hover=BORDER).pack(side="left", padx=s(10))
        FlatButton(row, "Clear all data", self._clear, bg="#FEE2E2", fg="#B91C1C",
                   hover="#FECACA").pack(side="left")

        p = card(page)
        p.pack(fill="x", pady=(s(14), 0))
        tk.Label(p, text="Your privacy", font=FONT_H, fg=TEXT, bg=CARD).pack(anchor="w", padx=s(18), pady=(s(14), 0))
        msg = ("ClickScope only counts mouse clicks. It never records keystrokes, screenshots, cursor "
               "movement, or what is on your screen, and it never connects to the internet.\n\n"
               "Only totals are saved (per day, per app, per website). Everything stays on this PC in:\n"
               f"{APP_DIR}\n\nClicks inside ClickScope itself are ignored. "
               "Tracking only runs while the app is open; minimize it to keep it running in the background.")
        lb = tk.Label(p, text=msg, font=FONT, fg=MUTED, bg=CARD, justify="left", anchor="w")
        lb.pack(fill="x", padx=s(18), pady=(s(6), s(14)))
        lb.bind("<Configure>", lambda e: lb.config(wraplength=max(100, e.width - 4)))
        return page

    def _on_sites(self):
        self.store.set("track_sites", "1" if self.var_sites.get() else "0")
        self.card_sites.sig = None

    def _on_auto(self):
        try:
            set_autostart(self.var_auto.get())
        except Exception as e:
            self.var_auto.set(not self.var_auto.get())
            messagebox.showerror("ClickScope", f"Could not change the startup setting:\n{e}")

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="clickscope-export.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if path:
            try:
                self.store.export_csv(path)
                messagebox.showinfo("ClickScope", "Exported successfully.")
            except Exception as e:
                messagebox.showerror("ClickScope", f"Export failed:\n{e}")

    def _open_folder(self):
        try:
            os.startfile(APP_DIR)
        except Exception:
            pass

    def _clear(self):
        if messagebox.askyesno("ClickScope", "Delete all saved click data? This cannot be undone."):
            self.store.clear()
            self.card_apps.sig = self.card_sites.sig = self.sug_sig = None
            self.refresh()

    # ------------------------------------------------------------ refresh
    def refresh(self):
        if self.tracker.paused:
            self.status.config(text="\u25CF Paused", fg=AMBER)
            self.btn_pause.restyle("Resume", ACCENT, TEXT, "#4BE6F8")
        else:
            self.status.config(text="\u25CF Tracking", fg=GREEN)
            self.btn_pause.restyle("Pause", TEXT, "#FFFFFF", "#1E3350")
        if self.tab == "overview":
            self._refresh_overview()
        elif self.tab == "suggestions":
            self._refresh_suggestions()

    def tick(self):
        try:
            self.refresh()
        except Exception:
            pass
        self.root.after(1500, self.tick)
