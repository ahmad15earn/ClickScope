"""ClickScope UI: sidebar + pages, spring-animated, light theme only."""
import datetime
import json
import math
import os
import subprocess
import sys
import webbrowser
from urllib.parse import quote
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import theme as T
from core import (ANALYSIS_DAYS, APP_DIR, MIN_ACTIVE_DAYS, build_suggestions, fmt_hour, quick_insights,
                  resource_path, same_app, SYSTEM_LABELS, weekly_apps)
import cloud
import cloud_config
import recovery as rec
from motion import Motion, Spring, clamp, mix, reduced_motion
from widgets import (AreaChartCard, BarChartCard, ChecklistCard, DonutCard, ListCard, PillButton, Segmented,
                     Sidebar, StatCard, Surface, line_height, measure, ring_sector, rrect, star_points)

RANGES = [("today", "Today"), ("7d", "7 days"), ("30d", "30 days"), ("all", "All time")]
RANGE_NAME = {"today": "today", "7d": "the last 7 days", "30d": "the last 30 days", "all": "all time"}
TITLES = {"overview": "Home", "inventory": "Inventory", "recovery": "Recovery", "account": "Account",
          "suggestions": "Insights", "settings": "Settings"}
TAGLINES = {"overview": "Your PC's safety net, built quietly in the background.",
            "inventory": "What you must get back first, whatever the clicks say.",
            "recovery": "Official installers, collected in one folder.",
            "suggestions": "A few useful nudges. No vanity stats.",
            "account": "Back up your list once, restore it on any PC.",
            "settings": "Privacy and preferences."}
HOUR_LABELS = ["12a", "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a", "9a", "10a", "11a",
               "12p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "11p"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SIDEBAR_W, HEADER_H = 220, 104


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


def day_label(d):
    return f"{d.day} {d.strftime('%b')}"


def toggle_protect(store, label):
    """Add/remove an app (named by a tracked window label) to/from the recovery list; returns True if now kept."""
    matches = [k for k in store.kept() if same_app(label, k)]
    if matches:
        for k in matches:
            store.toggle_keep(k)
        return False
    cat = [n for n, _ in store.catalog("app") if same_app(label, n)]
    store.toggle_keep(cat[0] if cat else label)
    return True


# -------------------------------------------------------------------- pages
class Page(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app, self.cards = app, []
        self.W = self.H = 0
        self.bind("<Configure>", self._conf)

    def _conf(self, e):
        self.W, self.H = e.width, e.height
        self.layout(e.width, e.height)

    def layout(self, w, h):
        pass

    def enter(self):
        for i, c in enumerate(self.cards):
            c.enter(delay=i * 55)
        self.update_data()

    def update_data(self):
        pass


class ReadinessCard(Surface):
    """Recovery readiness: a progress ring plus the four steps that make a PC recoverable."""

    def __init__(self, parent, motion):
        super().__init__(parent, motion)
        self.steps = []
        self.ring = Spring(motion, self, 0.0, response=0.8, eps=0.002)
        self.bind("<ButtonPress-1>", self._click)

    def set_steps(self, steps):
        self.steps = steps
        self.ring.to(sum(1 for s in steps if s[2]) / max(len(steps), 1))
        self.redraw()

    def _row_y(self, i):
        return T.s(184) + i * T.s(56)

    def _click(self, e):
        for i, (_, _, _, act) in enumerate(self.steps):
            y = self._row_y(i)
            if y - T.s(6) <= e.y <= y + T.s(48):
                return act()

    def draw(self):
        pad = T.s(26)
        done = sum(1 for s in self.steps if s[2])
        total = max(len(self.steps), 1)
        self.text(pad, T.s(20), "Recovery readiness", 12, "bold")
        d, thick = T.s(92), T.s(11)
        cx, cy = pad + d / 2, T.s(66) + d / 2
        r = d / 2 - thick / 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T.TRACK, width=thick)
        deg = 360 * clamp(self.ring.value, 0, 1)
        col = T.GREEN if done == total else T.ACCENT
        if deg > 1:
            ring_sector(self, cx, cy, r, thick, 0, min(deg, 359.9), self.fade(col))
        self.text(cx, cy, f"{done}/{total}", 20, "bold", anchor="center", rise=False)
        tx = cx + d / 2 + T.s(24)
        head = "Ready to recover" if done == total else "Almost there" if done >= total - 1 else "Getting started"
        sub = ("If your PC fails, you can be back up and running fast." if done == total else
               "Finish the steps below so a crash never costs you your setup.")
        self.text(tx, T.s(78), head, 16, "bold")
        self.text(tx, T.s(104), sub, 10, fill=T.SUB, width=self.W - tx - pad)
        for i, (title, sub, ok, _) in enumerate(self.steps):
            y = self._row_y(i)
            self.create_line(pad, y - T.s(8), self.W - pad, y - T.s(8), fill=T.LINE)
            cx2, cy2, rr = pad + T.s(14), y + T.s(18), T.s(14)
            if ok:
                self.create_oval(cx2 - rr, cy2 - rr, cx2 + rr, cy2 + rr, fill=self.fade(T.GREEN), outline="")
                self.create_line(cx2 - 5, cy2, cx2 - 1, cy2 + 4, cx2 + 6, cy2 - 4, fill="#FFFFFF", width=T.s(2.5),
                                 capstyle="round", joinstyle="round")
            else:
                self.create_oval(cx2 - rr, cy2 - rr, cx2 + rr, cy2 + rr, outline=T.LINE2, width=T.s(2), fill=T.CARD)
                self.text(cx2, cy2, str(i + 1), 10, "bold", fill=T.SUB, anchor="center", rise=False)
            self.text(pad + T.s(42), y + T.s(2), title, 11, "bold", fill=T.SUB if ok else T.TEXT)
            self.text(pad + T.s(42), y + T.s(24), sub, 9, fill=T.SUB)
            ax = self.W - pad - T.s(6)
            self.create_line(ax - 5, cy2 - 6, ax, cy2, ax - 5, cy2 + 6, fill=T.LINE2, width=T.s(2), capstyle="round", joinstyle="round")
        py = self.H - T.s(28)
        self.create_line(pad, py - T.s(16), self.W - pad, py - T.s(16), fill=T.LINE)
        self.create_oval(pad, py - T.s(8), pad + T.s(16), py + T.s(8), fill=self.fade(T.ACCENT_SOFT), outline="")
        self.create_line(pad + 4, py, pad + 7, py + 3, pad + 12, py - 3, fill=self.fade(T.ACCENT_D), width=T.s(2), capstyle="round", joinstyle="round")
        self.text(pad + T.s(26), py, "Your click data never leaves this PC. No keystrokes, no screenshots.", 9, fill=T.SUB, anchor="w", rise=False)


class HomePage(Page):
    """Recovery-first home: what is protected, what is not, and what to do next."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.s_prot = StatCard(self, m, "Protected apps")
        self.s_add = StatCard(self, m, "Worth adding")
        self.s_cloud = StatCard(self, m, "Cloud backup")
        self.s_track = StatCard(self, m, "Background tracking")
        self.ready = ReadinessCard(self, m)
        self.list = ListCard(self, m, "Worth protecting", lambda: None, None, self._keep, toggles=False)
        self.cards = [self.s_prot, self.s_add, self.s_cloud, self.s_track, self.ready, self.list]

    def _keep(self, label):
        toggle_protect(self.app.store, label)
        self.update_data()

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        cw = (iw - 3 * G) // 4
        sh = T.s(112)
        for i, c in enumerate((self.s_prot, self.s_add, self.s_cloud, self.s_track)):
            c.place(x=P + i * (cw + G), y=0, width=cw, height=sh)
        ly, lh = sh + G, max(T.s(300), h - sh - G - T.s(26))
        lw = int(iw * 0.52)
        self.ready.place(x=P, y=ly, width=lw, height=lh)
        self.list.place(x=P + lw + G, y=ly, width=iw - lw - G, height=lh)
        self.list.capacity = max(3, (lh - T.s(64) - T.s(30)) // T.s(46))

    def update_data(self):
        a, st = self.app, self.app.store
        kept, ksites = st.kept(), st.kept_sites()
        self.s_prot.set_number(len(kept), f"{len(ksites)} favourite site{'s' if len(ksites) != 1 else ''}")
        fu = st.frequent_unprotected(10)
        self.s_add.set_number(len(fu), "used often, not in your list" if fu else "Everything covered")
        if cloud.configured() and cloud.signed_in(st):
            last = st.get("cloud_last_sync", "")
            self.s_cloud.set_label("On", f"Last synced {last[-5:]}" if last else "Syncing\u2026", T.GREEN)
        else:
            self.s_cloud.set_label("Off", "Sign in to back up" if cloud.configured() else "Not set up", T.AMBER)
        trk = getattr(a.tracker, "paused", False)
        off = st.get("tracking", "1") == "0"
        self.s_track.set_label("Off" if off else "Paused" if trk else "Active",
                               f"{st.total('today'):,} clicks today" if not off else "Saves resources",
                               T.FAINT if off else (T.AMBER if trk else T.GREEN))
        steps = [("Scan this PC", "Find every app installed here", bool(st.catalog("app")), lambda: a.start_setup(False, 1)),
                 ("Choose your must-keep apps", "Mark what you would want back first", bool(kept), lambda: a.show("inventory")),
                 ("Back up your list", "Sign in so a new PC can restore it",
                  bool(cloud.configured() and cloud.signed_in(st) and st.get("cloud_last_sync")), lambda: a.show("account")),
                 ("Download your installers", "Collect them in one folder", bool(st.get("recovery_done")), lambda: a.show("recovery"))]
        self.ready.set_steps(steps)
        rows = [(n, c) for n, c in st.top("app", "30d", 20) if n not in SYSTEM_LABELS and c >= 10][: self.list.capacity]
        self.list.kept = {n for n, _ in rows if any(same_app(n, k) for k in kept)}
        self.list.set_rows(rows, "Use your PC as usual. The apps you rely on will show up here.")


class LearningCard(Surface):
    """First 30 days: progress ring + 30-day dot calendar."""

    def __init__(self, parent, motion):
        super().__init__(parent, motion)
        self.day, self.unlock = 1, None
        self.short, self.active = False, 0
        self.ring = Spring(motion, self, 0.0, response=0.9, eps=0.002)
        self.dots = Spring(motion, self, 0.0, response=1.1, eps=0.002)

    def set_progress(self, day, unlock, short=False, active=0):
        self.day, self.unlock, self.short, self.active = day, unlock, short, active
        self.ring.to(day / ANALYSIS_DAYS)
        self.dots.to(1)
        self.redraw()

    def enter(self, delay=0):
        super().enter(delay)
        self.ring.jump(0)
        self.dots.jump(0)
        self.ring.to(self.day / ANALYSIS_DAYS)
        self.dots.to(1)

    def draw(self):
        pad = T.s(28)
        d = T.s(118)
        thick = T.s(12)
        cx, cy = pad + d / 2 + T.s(6), pad + d / 2 + T.s(2)
        r = d / 2 - thick / 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T.TRACK, width=thick)
        deg = 360 * clamp(self.ring.value, 0, 1)
        if deg > 1:
            ring_sector(self, cx, cy, r, thick, 0, deg, T.ACCENT)
            for ang in (0, deg):  # round caps
                a = math.radians(ang)
                ex, ey = cx + r * math.sin(a), cy - r * math.cos(a)
                self.create_oval(ex - thick / 2, ey - thick / 2, ex + thick / 2, ey + thick / 2, fill=T.ACCENT, outline=T.ACCENT)
        self.text(cx, cy - T.s(28), "Day", 9, fill=T.SUB, anchor="center", rise=False)
        self.text(cx, cy, str(self.day), 28, "bold", anchor="center", rise=False)
        self.text(cx, cy + T.s(30), f"of {ANALYSIS_DAYS}", 9, fill=T.SUB, anchor="center", rise=False)

        tx = cx + d / 2 + T.s(40)
        tw = self.W - tx - pad
        self.text(tx, pad - T.s(2), "Learning your habits", 18, "bold")
        unlock = f"{self.unlock.strftime('%B')} {self.unlock.day}" if self.unlock else ""
        if self.short:
            body = (f"Day {ANALYSIS_DAYS} is here, but ClickScope has only seen {self.active} active days. "
                    f"Full suggestions need {MIN_ACTIVE_DAYS} days with real activity.")
        else:
            body = ("Full suggestions unlock after 30 days of real patterns. Until then you get weekly check-ins "
                    "and early insights below, and you can already build your recovery inventory.")
        self.text(tx, pad + T.s(32), body, 10, fill=T.SUB, width=tw)
        lines = max(1, math.ceil(measure(body, 10) * 1.05 / max(tw, 50)))
        y = pad + T.s(32) + lines * line_height(10) + T.s(12)
        label = (f"Active days so far: {self.active} of {MIN_ACTIVE_DAYS}" if self.short
                 else f"Full suggestions unlock on {unlock}")
        rrect(self, tx, y, tx + measure(label, 10, "bold") + T.s(28), y + T.s(30), T.s(15),
              fill=self.fade(T.ACCENT_SOFT), outline="")
        self.text(tx + T.s(14), y + T.s(15), label, 10, "bold", fill=T.ACCENT_D, anchor="w", bg=T.ACCENT_SOFT)

        gy = self.H - T.s(26)
        slot = (self.W - 2 * pad) / ANALYSIS_DAYS
        dr = min(T.s(6), slot * 0.3)
        shown = self.dots.value * ANALYSIS_DAYS
        for i in range(ANALYSIS_DAYS):
            x = pad + slot * (i + 0.5)
            if i < self.day - 1 and i < shown:
                self.create_oval(x - dr, gy - dr, x + dr, gy + dr, fill=T.ACCENT, outline="")
            elif i == self.day - 1 and i < shown + 1:
                self.create_oval(x - dr - 2, gy - dr - 2, x + dr + 2, gy + dr + 2, fill=T.CARD, outline=T.ACCENT, width=T.s(2.5))
                self.create_oval(x - dr * 0.45, gy - dr * 0.45, x + dr * 0.45, gy + dr * 0.45, fill=T.ACCENT, outline="")
            else:
                self.create_oval(x - dr, gy - dr, x + dr, gy + dr, fill=T.TRACK, outline="")


class CheckinCard(Surface):
    """Weekly mini report during the learning window, with an interactive question."""

    def __init__(self, parent, motion, on_toggle):
        super().__init__(parent, motion)
        self.on_toggle = on_toggle
        self.week, self.partial, self.insights, self.names, self.kept = 1, True, [], [], set()
        self.chips = []
        for i in range(8):
            self.tag_bind(f"chip{i}", "<ButtonPress-1>", lambda e, i=i: self._chip(i))
            self.tag_bind(f"chip{i}", "<Enter>", lambda e: self.config(cursor="hand2"))
            self.tag_bind(f"chip{i}", "<Leave>", lambda e: self.config(cursor=""))

    def set_data(self, day, insights, names, kept):
        self.week = min(4, (day - 1) // 7 + 1)
        self.partial = day % 7 != 0
        self.insights, self.names, self.kept = insights, names, set(kept)
        self.redraw()

    def _chip(self, i):
        if i < len(self.names):
            self.on_toggle(self.names[i])

    def draw(self):
        pad = T.s(28)
        self.text(pad, T.s(22), f"Week {self.week} check-in" + ("  \u00b7  so far" if self.partial else ""), 14, "bold")
        y = T.s(54)
        for line in self.insights:
            self.create_oval(pad, y + T.s(6), pad + T.s(6), y + T.s(12), fill=self.fade(T.ACCENT), outline="")
            self.text(pad + T.s(16), y, line, 10, fill=T.SUB)
            y += T.s(24)
        y += T.s(10)
        q = (f"You used {len(self.names)} apps regularly this week. Which belong in your recovery inventory?"
             if self.names else "No regularly used apps yet. They will appear here as you work.")
        self.text(pad, y, q, 10, "bold", width=self.W - 2 * pad)
        self.text(pad, y + T.s(22), "Rarely clicked apps can matter most when a PC fails, so pick by importance, not by clicks.",
                  9, fill=T.SUB, width=self.W - 2 * pad)
        x, cy = pad, y + T.s(70)
        for i, name in enumerate(self.names):
            on = name in self.kept
            nm = name if len(name) <= 22 else name[:21] + "\u2026"
            wdt = measure(nm, 10, "bold") + T.s(52)
            if x + wdt > self.W - pad:
                x, cy = pad, cy + T.s(44)
            rrect(self, x, cy, x + wdt, cy + T.s(34), T.s(17), fill=self.fade("#FFF4D6" if on else T.TRACK),
                  outline=self.fade(T.AMBER if on else T.TRACK), tags=f"chip{i}")
            self.create_polygon(star_points(x + T.s(20), cy + T.s(17), T.s(8)), fill=self.fade(T.AMBER) if on else "",
                                outline=self.fade(T.AMBER if on else T.FAINT), width=T.s(1.5), tags=f"chip{i}")
            self.create_text(x + T.s(36), cy + T.s(17), text=nm, font=T.F(10, "bold"), fill=self.fade(T.TEXT),
                             anchor="w", tags=f"chip{i}")
            x += wdt + T.s(8)


class SuggestionCard(Surface):
    def __init__(self, parent, motion, item, on_action=None):
        super().__init__(parent, motion)
        self.item = item
        self.btn = None
        if item.get("action") and on_action:
            self.btn = PillButton(self, motion, item["action"]["label"], lambda: on_action(item), "dark", h=T.s(34))

    @staticmethod
    def height_for(item, width):
        avail = width - T.s(24 + 52 + 24) - (T.s(210) if item.get("action") else 0)
        lines = max(1, math.ceil(measure(item["text"], 10) * 1.06 / max(avail, 60)))
        return max(T.s(92), T.s(26) + line_height(12, "bold") + T.s(6) + lines * line_height(10) + T.s(22))

    def draw(self):
        it, pad = self.item, T.s(24)
        col = T.LEVEL.get(it["level"], T.ACCENT)
        cx, cy, rr = pad + T.s(20), pad + T.s(20), T.s(20)
        self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=self.fade(mix(T.CARD, col, 0.16)), outline="")
        c = self.fade(col)
        if it["level"] == "good":
            self.create_line(cx - 7, cy, cx - 2, cy + 6, cx + 8, cy - 6, fill=c, width=T.s(3), capstyle="round", joinstyle="round")
        elif it["level"] == "warn":
            self.create_line(cx, cy - 8, cx, cy + 2, fill=c, width=T.s(3), capstyle="round")
            self.create_oval(cx - 2, cy + 6, cx + 2, cy + 10, fill=c, outline="")
        elif it["level"] == "info":
            self.create_line(cx, cy - 1, cx, cy + 8, fill=c, width=T.s(3), capstyle="round")
            self.create_oval(cx - 2, cy - 9, cx + 2, cy - 5, fill=c, outline="")
        else:
            pts = []
            for i in range(8):
                a = math.radians(i * 45 - 90)
                rad = T.s(9) if i % 2 == 0 else T.s(3.4)
                pts += [cx + rad * math.cos(a), cy + rad * math.sin(a)]
            self.create_polygon(pts, fill=c, outline="")
        x = pad + T.s(52)
        self.text(x, pad - T.s(2), it["title"], 12, "bold")
        bw = (self.btn.w + T.s(20)) if self.btn else 0
        self.text(x, pad + line_height(12, "bold") + T.s(4), it["text"], 10, fill=T.SUB, width=self.W - x - pad - bw)
        if self.btn:
            self.create_window(self.W - pad, (self.H - self.btn.h) / 2, window=self.btn, anchor="ne")


class SuggestionsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.learning = LearningCard(self, app.motion)
        self.checkin = CheckinCard(self, app.motion, self._toggle)
        self.items, self.sig, self.ready = [], None, False
        self.cards = [self.learning, self.checkin]

    def _toggle(self, name):
        toggle_protect(self.app.store, name)
        self.update_data()

    def _action(self, item):
        act = item["action"]
        if act["kind"] == "keep":
            toggle_protect(self.app.store, act["name"])
        self.sig = None
        self.update_data()

    def layout(self, w, h):
        P, G = T.s(32), T.s(14)
        iw = w - 2 * P
        if not self.ready:
            lh = T.s(240)
            self.learning.place(x=P, y=0, width=iw, height=lh)
            self.checkin.place(x=P, y=lh + G, width=iw, height=max(T.s(250), h - lh - G - T.s(26)))
            return
        self.learning.place_forget()
        self.checkin.place_forget()
        y = 0
        for c in self.items:
            ch = SuggestionCard.height_for(c.item, iw)
            c.place(x=P, y=y, width=iw, height=ch)
            y += ch + G

    def enter(self):
        self.sig = None
        self.update_data()
        for i, c in enumerate(self.cards):
            c.enter(delay=i * 70)

    def update_data(self):
        st = self.app.store
        day, ready, unlock = st.analysis_progress()
        if not ready:
            if self.items:
                for c in self.items:
                    c.destroy()
                self.items = []
            if self.ready or not self.checkin.mapped:
                self.ready = False
                self.layout(self.W, self.H)
            self.ready, self.sig, self.cards = False, None, [self.learning, self.checkin]
            self.learning.set_progress(day, unlock, day >= ANALYSIS_DAYS, st.active_days())
            wk = weekly_apps(st)
            kl = [n for n in wk if any(same_app(n, k) for k in st.kept())]
            self.checkin.set_data(day, quick_insights(st), wk, kl)
            self.layout(self.W, self.H)
            return
        sug = build_suggestions(st, "30d")
        sig = tuple((i["title"], i["text"]) for i in sug)
        if sig == self.sig:
            return
        self.sig, self.ready = sig, True
        for c in self.items:
            c.destroy()
        self.items = [SuggestionCard(self, self.app.motion, it, self._action) for it in sug]
        self.cards = list(self.items)
        self.layout(self.W, self.H)
        for i, c in enumerate(self.items):
            c.enter(delay=i * 70)


class InventoryPage(Page):
    """Apps and websites the user marked as must-keep. Importance is chosen by the user, not by click counts."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.kind = "app"
        self.card = Surface(self, m)
        self.cards = [self.card]
        self.rows = []
        self.card.draw = self._draw
        self.card.bind("<ButtonPress-1>", self._click)
        self.seg = Segmented(self.card, m, [("app", "Apps"), ("site", "Websites")], self._kind,
                             seg_w=T.s(84), h=T.s(30), bg=T.CARD)
        self.btns = [PillButton(self.card, m, "Scan this PC", lambda: app.start_setup(False, 1), "accent"),
                     PillButton(self.card, m, "Add manually\u2026", self._add, "soft"),
                     PillButton(self.card, m, "Export recovery checklist", self._export, "soft")]

    def _kind(self, k):
        self.kind = k
        self.update_data()

    def layout(self, w, h):
        P = T.s(32)
        self.card.place(x=P, y=0, width=w - 2 * P, height=h - T.s(26))

    def update_data(self):
        st = self.app.store
        if self.kind == "app":
            self.rows = [(n, f"{c:,} clicks  \u00b7  last clicked " + (
                "today" if l == datetime.date.today() else f"{(datetime.date.today() - l).days} days ago")
                          if l else "Not seen yet  \u00b7  added manually") for n, c, l in st.keep_info()]
        else:
            self.rows = st.keep_sites_info()
        self.card.redraw()

    def _pitch(self):
        return T.s(52)

    def _cap(self):
        return max(1, (self.card.H - T.s(160)) // self._pitch())

    def _click(self, e):
        if T.s(20) <= e.x <= T.s(56):
            i = (e.y - T.s(104)) // self._pitch()
            if 0 <= i < min(len(self.rows), self._cap()):
                st, name = self.app.store, self.rows[int(i)][0]
                st.toggle_keep(name) if self.kind == "app" else st.toggle_keep_site(name)
                self.update_data()

    def _draw(self):
        c, pad = self.card, T.s(28)
        c.text(pad, T.s(22), "Recovery inventory", 14, "bold")
        c.create_window(c.W - pad, T.s(18), window=self.seg, anchor="ne")
        c.text(pad, T.s(52), "Clicks measure habit, not importance. Keep the apps and sites you must get back first if your "
                              "PC fails or is reinstalled, even ones you open once a week.", 10, fill=T.SUB, width=c.W - 2 * pad)
        y0 = T.s(104)
        if not self.rows:
            msg = ("Nothing here yet. Press Scan this PC to find your installed software and tick what matters, "
                   "or tap the star next to an app in Overview." if self.kind == "app" else
                   "No websites yet. Press Scan this PC, choose your browsers, and tick the sites you want to remember.")
            c.text(pad, y0 + T.s(10), msg, 10, fill=T.SUB, width=c.W - 2 * pad)
        for i, (name, sub) in enumerate(self.rows[: self._cap()]):
            y = y0 + i * self._pitch()
            c.create_line(pad, y - T.s(8), c.W - pad, y - T.s(8), fill=T.LINE)
            c.create_polygon(star_points(pad + T.s(10), y + T.s(14), T.s(10)), fill=c.fade(T.AMBER), outline=c.fade(T.AMBER))
            c.text(pad + T.s(36), y + T.s(3), name, 11, "bold")
            c.text(pad + T.s(36), y + T.s(24), sub, 9, fill=T.SUB)
        extra = len(self.rows) - self._cap()
        if extra > 0:
            c.text(pad, c.H - T.s(84), f"+{extra} more (all included in the exported checklist)", 9, fill=T.SUB, anchor="sw")
        x = pad
        for b in self.btns:
            c.create_window(x, c.H - T.s(66), window=b, anchor="nw")
            x += b.w + T.s(10)

    def _add(self):
        what = "app" if self.kind == "app" else "website (for example github.com)"
        name = simpledialog.askstring("ClickScope", f"Name of the {what} to add to your recovery inventory:")
        if name and name.strip():
            st = self.app.store
            if self.kind == "app":
                st.set_keep(name.strip(), True)
            else:
                st.toggle_keep_site(name.strip(), True)
            self.update_data()

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="recovery-checklist.txt",
                                            filetypes=[("Text file", "*.txt")])
        if path:
            try:
                self.app.store.export_inventory(path)
                messagebox.showinfo("ClickScope", "Checklist saved.")
            except Exception as e:
                messagebox.showerror("ClickScope", f"Export failed:\n{e}")


class RecoveryPage(Page):
    """Download installers for chosen apps into one folder, in the background, with progress and retry."""
    STATUS = {rec.QUEUED: (T.FAINT, "Waiting"), rec.RESOLVING: (T.ACCENT, "Looking"), rec.DOWNLOADING: (T.ACCENT, "Downloading"),
              rec.DONE: (T.GREEN, "Done"), rec.FAILED: (T.RED, "Failed"), rec.NOSOURCE: (T.AMBER, "Manual"),
              rec.CANCELLED: (T.FAINT, "Cancelled")}

    def __init__(self, parent, app):
        super().__init__(parent, app)
        m, st = app.motion, app.store
        self.card = Surface(self, m)
        self.picker = ChecklistCard(self, m, "Choose apps to download")
        self.cards = [self.card]
        self.card.draw = self._draw
        self.mgr, self.picking, self._ticking, self._actions = None, False, False, []
        self.folder = st.get("recovery_folder", "")
        self.chosen = self._load_chosen()
        self.scroll = Spring(m, self.card, 0.0, response=0.22, eps=0.3)
        self.card.bind("<MouseWheel>", self._wheel)
        self.card.bind("<ButtonPress-1>", self._click)
        self.card.bind("<Enter>", lambda e: self.card.focus_set())
        self.b_apps = PillButton(self.card, m, "Choose apps\u2026", self._pick, "soft")
        self.b_folder = PillButton(self.card, m, "Choose folder\u2026", self._choose_folder, "soft")
        self.b_start = PillButton(self.card, m, "Start download", self._start, "accent", width=T.s(210), h=T.s(44))
        self.b_retry = PillButton(self.card, m, "Retry failed", lambda: self._retry_all(), "dark")
        self.b_cancel = PillButton(self.card, m, "Cancel", lambda: self.mgr and self.mgr.cancel(), "soft")
        self.b_open = PillButton(self.card, m, "Open folder", self._open_folder, "soft")
        self.b_back = PillButton(self.card, m, "New download", self._reset, "soft")
        self.p_all = PillButton(self.picker, m, "Select all", lambda: self.picker.select_all_shown(), "soft")
        self.p_cancel = PillButton(self.picker, m, "Cancel", self._pick_cancel, "soft")
        self.p_done = PillButton(self.picker, m, "Use selected", self._pick_done, "accent")
        self.picker.buttons = [self.p_all, self.p_cancel, self.p_done]

    # ---- persistence
    def _load_chosen(self):
        try:
            v = json.loads(self.app.store.get("recovery_apps", "null"))
        except ValueError:
            v = None
        return list(v) if v else list(self.app.store.kept())

    def layout(self, w, h):
        P = T.s(32)
        self.card.place(x=P, y=0, width=w - 2 * P, height=h - T.s(26))
        if self.picking:
            self.picker.place(x=P, y=0, width=w - 2 * P, height=h - T.s(26))
        else:
            self.picker.place_forget()

    def update_data(self):
        if not self.mgr and not self.picking:
            self.chosen = self._load_chosen()
        self.card.redraw()

    # ---- choosing
    def _pick(self):
        st = self.app.store
        cat = st.catalog("app")
        names = {n: d for n, d in cat}
        for n in set(self.chosen) | set(st.kept()):
            names.setdefault(n, "From your inventory")
        if not names:
            if messagebox.askyesno("ClickScope", "ClickScope has not scanned this PC yet.\nScan your installed apps now?"):
                self.app.start_setup(False, 1)
            return
        items = [(n, n, d) for n, d in sorted(names.items(), key=lambda t: t[0].lower())]
        self.picker.set_items(items, set(self.chosen))
        self.picker.title = "Choose apps to download"
        self.picker.subtitle = "Tick the software you want installers for. Your inventory is pre-selected."
        self.picker.info = ""
        self.picking = True
        self.layout(self.W, self.H)
        self.picker.enter()

    def _pick_cancel(self):
        self.picking = False
        self.layout(self.W, self.H)

    def _pick_done(self):
        self.chosen = self.picker.new_selection()
        self.app.store.set("recovery_apps", json.dumps(self.chosen))
        self._pick_cancel()
        self.card.redraw()

    def _choose_folder(self):
        d = filedialog.askdirectory(title="Where should ClickScope save the installers?", mustexist=False)
        if d:
            self.folder = d
            self.app.store.set("recovery_folder", d)
            self.card.redraw()

    # ---- running
    def _start(self):
        if not self.chosen:
            return messagebox.showinfo("ClickScope", "Choose at least one app first.")
        if not self.folder:
            return messagebox.showinfo("ClickScope", "Choose the folder where the installers should be saved.")
        try:
            ids = json.loads(self.app.store.get("winget_ids", "{}"))
        except ValueError:
            ids = {}
        self.mgr = rec.RecoveryManager(self.folder, list(self.chosen), ids)
        self.scroll.jump(0)
        self.mgr.start()
        self._start_ticking()
        self.card.redraw()

    def _retry_all(self):
        if self.mgr:
            self.mgr.retry_failed()
            self._start_ticking()

    def _reset(self):
        self.mgr = None
        self.card.redraw()

    def _open_folder(self):
        try:
            os.startfile(self.folder)
        except Exception:
            pass

    def _start_ticking(self):
        if not self._ticking:
            self._ticking = True
            self._tick()

    def _tick(self):
        if not self.mgr:
            self._ticking = False
            return
        self.card.redraw()
        if self.mgr.running:
            self.app.root.after(350, self._tick)
        else:
            self._ticking = False
            self.app.store.set("winget_ids", json.dumps(self.mgr.ids))
            if self.mgr.counts().get(rec.DONE):
                self.app.store.set("recovery_done", datetime.date.today().isoformat())

    # ---- events
    def _max_scroll(self):
        if not self.mgr:
            return 0
        return max(0, len(self.mgr.jobs) * T.s(62) - (self.card.H - T.s(118) - T.s(84)))

    def _wheel(self, e):
        self.scroll.to(clamp(self.scroll.target - (e.delta / 120.0) * T.s(62) * 1.4, 0, self._max_scroll()))

    def _click(self, e):
        for y1, y2, job, kind in self._actions:
            if y1 <= e.y <= y2 and e.x >= self.card.W - T.s(150):
                if kind == "retry":
                    self.mgr.retry(job)
                    self._start_ticking()
                elif kind == "web":
                    webbrowser.open("https://www.google.com/search?q=" + quote(job.name + " official download"))
                elif kind == "open" and job.folder:
                    try:
                        os.startfile(job.folder)
                    except Exception:
                        pass
                return

    # ---- drawing
    def _draw(self):
        (self._draw_jobs if self.mgr else self._draw_idle)()

    def _step_row(self, c, y, num, title, sub, btn):
        pad = T.s(28)
        c.create_oval(pad, y, pad + T.s(30), y + T.s(30), fill=c.fade(T.ACCENT_SOFT), outline="")
        c.text(pad + T.s(15), y + T.s(15), str(num), 11, "bold", fill=T.ACCENT_D, anchor="center", rise=False, bg=T.ACCENT_SOFT)
        c.text(pad + T.s(46), y - T.s(2), title, 11, "bold")
        c.text(pad + T.s(46), y + T.s(20), sub, 9, fill=T.SUB, width=c.W - 2 * pad - T.s(260))
        c.create_window(c.W - pad, y - T.s(4), window=btn, anchor="ne")

    def _draw_idle(self):
        c, pad = self.card, T.s(28)
        c.text(pad, T.s(22), "Software recovery", 14, "bold")
        c.text(pad, T.s(50), "Pick your software and a folder. ClickScope downloads the official installers one by one in the "
                              "background, each in its own folder, so you can reinstall everything after a reset.",
               10, fill=T.SUB, width=c.W - 2 * pad)
        n = len(self.chosen)
        self._step_row(c, T.s(124), 1, "Software to recover",
                       f"{n} app{'s' if n != 1 else ''} selected" if n else "None yet. Choose from your inventory or scan results.", self.b_apps)
        c.create_line(pad, T.s(176), c.W - pad, T.s(176), fill=T.LINE)
        self._step_row(c, T.s(196), 2, "Save installers to", self.folder or "No folder chosen yet", self.b_folder)
        c.create_line(pad, T.s(248), c.W - pad, T.s(248), fill=T.LINE)
        c.create_window(pad, T.s(272), window=self.b_start, anchor="nw")
        note = ("How it works: ClickScope asks Windows Package Manager (winget) for each app, so installers come from its "
                "official, hash-checked repository. Nothing is installed. Paid, Store-only or niche apps have no automatic "
                "source; they are listed so you can fetch them manually. Failed downloads can be retried with one click.")
        c.text(pad, T.s(344), note, 9, fill=T.SUB, width=c.W - 2 * pad)

    def _draw_jobs(self):
        c, pad, mg = self.card, T.s(28), self.mgr
        jobs, cnt = mg.jobs, mg.counts()
        pitch, top, bot = T.s(62), T.s(118), c.H - T.s(84)
        self._actions = []
        for i, j in enumerate(jobs):
            y = top + i * pitch - self.scroll.value
            if y + pitch < top or y > bot:
                continue
            col, label = self.STATUS[j.status]
            c.create_line(pad, y + pitch - 2, c.W - pad, y + pitch - 2, fill=T.LINE)
            c.create_oval(pad, y + T.s(10), pad + T.s(12), y + T.s(22), fill=c.fade(col), outline="")
            nm = j.name if len(j.name) <= 40 else j.name[:39] + "\u2026"
            c.create_text(pad + T.s(26), y + T.s(16), text=nm, font=T.F(10, "bold"), fill=T.TEXT, anchor="w")
            c.create_text(pad + T.s(26), y + T.s(36), text=j.message[:96], font=T.F(9), fill=T.RED if j.status == rec.FAILED else T.SUB, anchor="w")
            action = {rec.FAILED: ("Retry", "retry"), rec.CANCELLED: ("Retry", "retry"), rec.NOSOURCE: ("Search web", "web"),
                      rec.DONE: ("Open", "open")}.get(j.status)
            if action:
                c.create_text(c.W - pad - T.s(14), y + T.s(16), text=action[0], font=T.F(10, "bold"), fill=T.ACCENT_D, anchor="e")
                self._actions.append((y, y + pitch, j, action[1]))
            else:
                c.create_text(c.W - pad - T.s(14), y + T.s(16), text=label, font=T.F(9), fill=T.SUB, anchor="e")
            if j.status in (rec.DOWNLOADING, rec.DONE):
                bw = c.W - 2 * pad - T.s(150)
                by = y + T.s(46)
                rrect(c, pad + T.s(26), by, pad + T.s(26) + bw, by + T.s(5), T.s(2.5), fill=T.TRACK, outline="")
                rrect(c, pad + T.s(26), by, pad + T.s(26) + max(T.s(5), bw * j.progress), by + T.s(5), T.s(2.5),
                      fill=c.fade(T.GREEN if j.status == rec.DONE else T.ACCENT), outline="")
        c.create_rectangle(T.s(8), 3, c.W - T.s(8), top - 2, fill=T.CARD, outline="")
        c.create_rectangle(T.s(8), bot, c.W - T.s(8), c.H - 5, fill=T.CARD, outline="")
        c.create_line(pad, bot, c.W - pad, bot, fill=T.LINE)
        done, total = cnt.get(rec.DONE, 0), len(jobs)
        c.text(pad, T.s(22), "Downloading your software" if mg.running else "Recovery finished", 14, "bold")
        bits = [f"{done} of {total} downloaded"] + [f"{cnt[k]} {w}" for k, w in ((rec.FAILED, "failed"), (rec.NOSOURCE, "need manual download"))
                                                     if cnt.get(k)]
        c.text(pad, T.s(50), "  \u00b7  ".join(bits), 10, fill=T.SUB)
        frac = sum(1.0 if j.status in (rec.DONE, rec.NOSOURCE, rec.FAILED, rec.CANCELLED) else j.progress for j in jobs) / max(total, 1)
        rrect(c, pad, T.s(82), c.W - pad, T.s(90), T.s(4), fill=T.TRACK, outline="")
        rrect(c, pad, T.s(82), pad + max(T.s(8), (c.W - 2 * pad) * frac), T.s(90), T.s(4), fill=c.fade(T.ACCENT), outline="")
        x, by = pad, bot + T.s(20)
        btns = ([self.b_cancel] if mg.running else [self.b_back]) + ([self.b_retry] if (cnt.get(rec.FAILED) or cnt.get(rec.CANCELLED)) else []) + [self.b_open]
        for b in sorted(btns, key=lambda b: b is not self.b_retry):
            c.create_window(x, by, window=b, anchor="nw")
            x += b.w + T.s(10)
        mx = self._max_scroll()
        if mx > 0:
            th = max(T.s(30), (bot - top) * (bot - top) / (len(jobs) * pitch))
            ty = top + (bot - top - th) * (self.scroll.value / mx)
            rrect(c, c.W - T.s(14), ty, c.W - T.s(9), ty + th, T.s(3), fill=T.LINE2, outline="")


class AccountPage(Page):
    """Google sign-in and cloud backup of the recovery list (never clicks)."""

    SYNCED = ["Your installed-app list", "Must-keep apps and favourite sites", "Your recovery selection"]
    NEVER = ["Click statistics", "Which apps you click most", "Anything else on your PC"]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.card = Surface(self, m)
        self.cards = [self.card]
        self.card.draw = self._draw
        self.busy, self.msg, self.err = False, "", False
        self.b_in = PillButton(self.card, m, "Sign in", lambda: self._email_auth(False), "dark", width=T.s(150), h=T.s(44))
        self.b_up = PillButton(self.card, m, "Create account", lambda: self._email_auth(True), "soft", width=T.s(170), h=T.s(44))
        self.b_google = PillButton(self.card, m, "Continue with Google", self._sign_in, "soft", width=T.s(210), h=T.s(44))
        ekw = dict(font=T.F(11), relief="flat", bd=0, bg=T.TRACK, fg=T.TEXT, insertbackground=T.TEXT,
                   highlightthickness=1, highlightbackground=T.LINE, highlightcolor=T.ACCENT)
        self.e_mail = tk.Entry(self.card, **ekw)
        self.e_pass = tk.Entry(self.card, show="\u2022", **ekw)
        self.b_sync = PillButton(self.card, m, "Sync now", self._sync, "dark")
        self.b_restore = PillButton(self.card, m, "Restore from cloud", self._restore, "soft")
        self.b_out = PillButton(self.card, m, "Sign out", self._sign_out, "danger")

    def layout(self, w, h):
        P = T.s(32)
        self.card.place(x=P, y=0, width=w - 2 * P, height=h - T.s(26))

    def update_data(self):
        self.card.redraw()

    # ---- actions (network work happens in a background thread)
    def _email_auth(self, create):
        st, email, pw = self.app.store, self.e_mail.get().strip(), self.e_pass.get()

        def work():
            (cloud.sign_up if create else cloud.sign_in_password)(st, email, pw)
            restored = cloud.pull(st)          # new PC: bring everything back
            cloud.push(st)                      # existing PC: merge up
            return restored

        def after(r):
            self.e_pass.delete(0, "end")
            if r[1] or r[2]:                    # something was restored: go straight to Recovery
                self.app.show("recovery")
        self._run("Signing in\u2026", work, lambda r: (f"Welcome back! Restored {r[1]} kept apps and {r[2]} favourite sites."
                                                      if (r[1] or r[2]) else "Signed in. Your recovery list is backed up."), after)

    def _run(self, label, fn, ok_text, after=None):
        if self.busy:
            return
        self.busy, self.msg, self.err = True, label, False
        self.card.redraw()

        def done(res, err):
            self.busy = False
            self.err = err is not None
            self.msg = str(err) if err else ok_text(res)
            self.card.redraw()
            self.app.refresh()
            if after and not err:
                after(res)
        cloud.run_bg(self.app.root, fn, done)

    def _sign_in(self):
        st = self.app.store

        def work():
            cloud.sign_in(st)
            restored = cloud.pull(st)          # new PC: bring everything back
            cloud.push(st)                      # existing PC: merge up
            return restored
        self._run("Waiting for Google\u2026 finish signing in in your browser.", work,
                  lambda r: (f"Signed in. Restored {r[1]} kept apps and {r[2]} favourite sites." if (r[1] or r[2])
                             else "Signed in. Your recovery list is backed up."))

    def _sync(self):
        st = self.app.store
        self._run("Syncing\u2026", lambda: (cloud.pull(st), cloud.push(st)), lambda r: "Everything is up to date.")

    def _restore(self):
        st = self.app.store
        self._run("Restoring\u2026", lambda: cloud.pull(st),
                  lambda r: f"Restored: {r[0]} apps in your list, {r[1]} kept apps, {r[2]} kept sites.")

    def _sign_out(self):
        cloud.sign_out(self.app.store)
        self.msg, self.err = "", False
        self.card.redraw()

    # ---- drawing
    def _lists(self, c, y):
        pad = T.s(28)
        half = (c.W - 2 * pad) / 2
        for col, (title, items, tint, sym) in enumerate((("Backed up", self.SYNCED, T.GREEN, "\u2713"),
                                                          ("Never uploaded", self.NEVER, T.RED, "\u2715"))):
            x = pad + col * half
            c.text(x, y, title, 10, "bold", fill=T.SUB)
            for i, line in enumerate(items):
                yy = y + T.s(28) + i * T.s(28)
                c.create_oval(x, yy, x + T.s(18), yy + T.s(18), fill=c.fade(mix(T.CARD, tint, 0.16)), outline="")
                cx, cy = x + T.s(9), yy + T.s(9)
                if sym == "\u2713":
                    c.create_line(cx - 4, cy, cx - 1, cy + 3, cx + 4, cy - 3, fill=c.fade(tint), width=T.s(2), capstyle="round", joinstyle="round")
                else:
                    c.create_line(cx - 3, cy - 3, cx + 3, cy + 3, fill=c.fade(tint), width=T.s(2), capstyle="round")
                    c.create_line(cx - 3, cy + 3, cx + 3, cy - 3, fill=c.fade(tint), width=T.s(2), capstyle="round")
                c.text(x + T.s(28), yy + T.s(1), line, 10)

    def _draw(self):
        c, pad = self.card, T.s(28)
        st = self.app.store
        if not cloud.configured():
            c.text(pad, T.s(26), "Cloud backup isn't set up yet", 14, "bold")
            c.text(pad, T.s(56), "Google sign-in needs a Supabase project. Add its URL and publishable key to "
                                  "src/cloud_config.py and enable Google sign-in in Supabase (see README). Until then your "
                                  "recovery list stays on this PC; use Settings > Back up data for a manual copy.",
                   10, fill=T.SUB, width=c.W - 2 * pad)
            return
        sess = cloud.session(st) if cloud.signed_in(st) else None
        if sess:
            email = sess.get("email") or "Signed in"
            c.create_oval(pad, T.s(26), pad + T.s(52), T.s(78), fill=c.fade(T.ACCENT), outline="")
            c.text(pad + T.s(26), T.s(52), (email[:1] or "?").upper(), 18, "bold", fill="#06303A", anchor="center", rise=False, bg=T.ACCENT)
            c.text(pad + T.s(68), T.s(28), email, 13, "bold")
            last = st.get("cloud_last_sync", "")
            c.text(pad + T.s(68), T.s(54), f"Last synced {last}" if last else "Not synced yet", 10, fill=T.SUB)
        else:
            c.text(pad, T.s(26), "Back up your recovery list", 14, "bold")
            c.text(pad, T.s(54), "Create a free account to keep your recovery inventory safe. On a new PC, install ClickScope, "
                                  "sign in, and your apps, favourite sites and recovery selection come back, ready to download.",
                   10, fill=T.SUB, width=c.W - 2 * pad)
        y = T.s(120)
        self._lists(c, y)
        by = y + T.s(130)
        if self.msg:
            c.text(pad, by, self.msg, 10, "bold", fill=T.RED if self.err else (T.SUB if self.busy else T.ACCENT_D), width=c.W - 2 * pad)
            by += T.s(46)
        if self.busy:
            return
        if sess:
            x = pad
            for b in (self.b_sync, self.b_restore, self.b_out):
                c.create_window(x, by, window=b, anchor="nw")
                x += b.w + T.s(10)
        else:
            c.text(pad, by, "Email", 9, "bold", fill=T.SUB)
            c.create_window(pad, by + T.s(20), window=self.e_mail, anchor="nw", width=T.s(340), height=T.s(36))
            c.text(pad + T.s(370), by, "Password (at least 6 characters)", 9, "bold", fill=T.SUB)
            c.create_window(pad + T.s(370), by + T.s(20), window=self.e_pass, anchor="nw", width=T.s(300), height=T.s(36))
            bx, byy = pad, by + T.s(74)
            for b in ([self.b_in, self.b_up] + ([self.b_google] if cloud_config.GOOGLE_ENABLED else [])):
                c.create_window(bx, byy, window=b, anchor="nw")
                bx += b.w + T.s(10)
            c.text(pad, byy + T.s(58), "New here? Type an email and password, then press Create account. On a new PC, "
                                       "just press Sign in with the same details. Use a password you don't use anywhere else.",
                   9, fill=T.SUB, width=c.W - 2 * pad)


class SettingsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        m, st = app.motion, app.store
        self.general, self.data, self.privacy = Surface(self, m), Surface(self, m), Surface(self, m)
        self.cards = [self.general, self.data, self.privacy]
        self.on = [st.get("tracking", "1") == "1", st.get("track_sites", "1") == "1", autostart_enabled()]
        self.knob = [Spring(m, self.general, 1.0 if v else 0.0, response=0.25) for v in self.on]
        self.rows = [("Count clicks in the background", "Only used to spot the apps you rely on. Turn off to save resources."),
                     ("Name websites in browsers", "Uses the browser tab title to name the site, never the URL."),
                     ("Start with Windows", "Launches minimized so tracking runs in the background.")]
        self.general.draw, self.data.draw, self.privacy.draw = self._draw_general, self._draw_data, self._draw_privacy
        for i in range(3):
            tag = f"tg{i}"
            self.general.tag_bind(tag, "<ButtonPress-1>", lambda e, i=i: self._toggle(i))
            self.general.tag_bind(tag, "<Enter>", lambda e: self.general.config(cursor="hand2"))
            self.general.tag_bind(tag, "<Leave>", lambda e: self.general.config(cursor=""))
        self.btns = [PillButton(self.data, m, "Export CSV", self._export, "dark"),
                     PillButton(self.data, m, "Open data folder", self._open_folder, "soft"),
                     PillButton(self.data, m, "Preview with sample data", self._demo, "soft"),
                     PillButton(self.data, m, "Back up data", self._backup, "soft"),
                     PillButton(self.data, m, "Restore backup", self._restore, "soft"),
                     PillButton(self.data, m, "Reset ignore list", self._reset_ignore, "soft"),
                     PillButton(self.data, m, "Run setup guide", lambda: app.start_setup(False, 0), "soft"),
                     PillButton(self.data, m, "Replay tour", lambda: app.start_tour(), "soft"),
                     PillButton(self.data, m, "Clear all data", self._clear, "danger")]

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        gh, dh = T.s(228), T.s(250)
        self.general.place(x=P, y=0, width=iw, height=gh)
        self.data.place(x=P, y=gh + G, width=iw, height=dh)
        self.privacy.place(x=P, y=gh + dh + 2 * G, width=iw, height=T.s(150))

    def _toggle(self, i):
        self.on[i] = not self.on[i]
        self.knob[i].to(1.0 if self.on[i] else 0.0)
        if i == 0:
            tr = self.app.tracker
            self.app.store.set("tracking", "1" if self.on[0] else "0")
            tr.paused = not self.on[0]
            if self.on[0] and hasattr(tr, "start"):
                tr.start()
            self.app.sidebar.set_paused(tr.paused)
        elif i == 1:
            self.app.store.set("track_sites", "1" if self.on[1] else "0")
        else:
            try:
                set_autostart(self.on[2])
            except Exception as e:
                self.on[2] = not self.on[2]
                self.knob[2].to(1.0 if self.on[2] else 0.0)
                messagebox.showerror("ClickScope", f"Could not change the startup setting:\n{e}")

    def _draw_general(self):
        c, pad = self.general, T.s(24)
        c.text(pad, T.s(18), "General", 12, "bold")
        for i, (title, sub) in enumerate(self.rows):
            y = T.s(58) + i * T.s(56)
            if i:
                c.create_line(pad, y - T.s(10), c.W - pad, y - T.s(10), fill=T.LINE)
            c.text(pad, y, title, 10, "bold")
            c.text(pad, y + T.s(20), sub, 9, fill=T.SUB)
            k = self.knob[i].value
            tw, th = T.s(46), T.s(28)
            x2, y1 = c.W - pad, y + T.s(2)
            rrect(c, x2 - tw, y1, x2, y1 + th, th / 2, fill=mix("#E3E5EA", T.ACCENT, k), outline="", tags=f"tg{i}")
            kr = th / 2 - T.s(3)
            kx = x2 - tw + th / 2 + k * (tw - th)
            c.create_oval(kx - kr, y1 + th / 2 - kr, kx + kr, y1 + th / 2 + kr, fill="#FFFFFF", outline="#DADDE3", tags=f"tg{i}")

    def _draw_data(self):
        c, pad = self.data, T.s(24)
        c.text(pad, T.s(18), "Your data", 12, "bold")
        x, y = pad, T.s(54)
        for b in self.btns:
            if x + b.w > c.W - pad:
                x, y = pad, y + T.s(46)
            c.create_window(x, y, window=b, anchor="nw")
            x += b.w + T.s(10)
        n = len(self.app.store.ignored())
        tip = (f"{n} ignored. " if n else "") + "Tip: right-click a row in Overview to stop counting an app or website."
        c.text(pad, c.H - T.s(36), tip, 9, fill=T.SUB, anchor="sw")
        c.text(pad, c.H - T.s(14), f"Saved only on this PC:  {APP_DIR}", 8, fill=T.FAINT, anchor="sw")

    def _draw_privacy(self):
        c, pad = self.privacy, T.s(24)
        c.text(pad, T.s(18), "Your privacy", 12, "bold")
        msg = ("ClickScope only counts mouse clicks. It never records keystrokes, screenshots, cursor movement "
               "or what is on your screen, and it never connects to the internet. Websites are named from the browser tab "
               "title. If you choose it in the setup guide, it also reads your bookmarks and most-visited domains once; "
               "only domain names are saved.\n\n"
               "Only totals are saved: per day, per app and per website. Clicks inside ClickScope are ignored. "
               "ClickScope runs quietly in the background all the time: closing the window just tucks it into the taskbar. "
               "Verify it yourself: the tracking code (winhook.py and core.py) has no network code. See TRUST.md.")
        c.text(pad, T.s(46), msg, 10, fill=T.SUB, width=c.W - 2 * pad)

    def _export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="clickscope-export.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if path:
            try:
                self.app.store.export_csv(path)
                messagebox.showinfo("ClickScope", "Exported successfully.")
            except Exception as e:
                messagebox.showerror("ClickScope", f"Export failed:\n{e}")

    def _open_folder(self):
        try:
            os.startfile(APP_DIR)
        except Exception:
            pass

    def _demo(self):
        cmd = [sys.executable, "--demo"] if getattr(sys, "frozen", False) else \
            [sys.executable, os.path.abspath(sys.argv[0]), "--demo"]
        try:
            subprocess.Popen(cmd)
        except Exception as e:
            messagebox.showerror("ClickScope", f"Could not open demo mode:\n{e}")

    def _backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".db", initialfile=f"clickscope-backup-{datetime.date.today()}.db",
                                            filetypes=[("ClickScope backup", "*.db")])
        if path:
            try:
                self.app.store.backup_to(path)
                messagebox.showinfo("ClickScope", "Backup saved. Keep it somewhere safe, e.g. cloud storage or a USB drive.")
            except Exception as e:
                messagebox.showerror("ClickScope", f"Backup failed:\n{e}")

    def _restore(self):
        path = filedialog.askopenfilename(filetypes=[("ClickScope backup", "*.db")])
        if path and messagebox.askyesno("ClickScope", "Replace the current data with this backup?\nUse this after reinstalling Windows or on a new PC."):
            try:
                self.app.store.restore_from(path)
                self.app.refresh()
                messagebox.showinfo("ClickScope", "Backup restored.")
            except Exception as e:
                messagebox.showerror("ClickScope", f"Restore failed:\n{e}")

    def _reset_ignore(self):
        self.app.store.clear_ignored()
        self.data.redraw()
        messagebox.showinfo("ClickScope", "Ignore list cleared. Those apps and websites will be counted again.")

    def _clear(self):
        if messagebox.askyesno("ClickScope", "Delete all saved click data?\nThe 30-day learning period "
                                              "will also start over. This cannot be undone."):
            self.app.store.clear()
            self.app.refresh()


# ---------------------------------------------------------------------- app
class App:
    def __init__(self, root, store, tracker, demo=False, size=(1120, 760), on_quit=None, on_ready=None):
        T.init(root)
        self.root, self.store, self.tracker, self.demo = root, store, tracker, demo
        self.on_quit = on_quit or root.destroy
        self.on_ready, self.setup = on_ready, None
        self.rng = "30d" if demo else "today"
        self.tab = "overview"
        self.size = (T.s(size[0]), T.s(size[1]))
        self.motion = Motion(root, enabled=not reduced_motion())
        root.configure(bg=T.BG)

        self.logo = None
        try:
            self.logo = tk.PhotoImage(file=resource_path("assets/logo_128.png" if T.SCALE >= 1.4 else "assets/logo_64.png"))
        except Exception:
            pass
        self.sidebar = Sidebar(root, self.motion, self.show, self.toggle_pause, logo=self.logo, demo=demo)
        self.main = tk.Frame(root, bg=T.BG)
        self.header = tk.Canvas(self.main, bg=T.BG, highlightthickness=0, bd=0)
        self.title_reveal = Spring(self.motion, self, 1.0, response=0.5)
        self.stage = tk.Frame(self.main, bg=T.BG)
        self.pages = {"overview": HomePage(self.stage, self),
                      "inventory": InventoryPage(self.stage, self),
                      "recovery": RecoveryPage(self.stage, self), "account": AccountPage(self.stage, self), "suggestions": SuggestionsPage(self.stage, self), "settings": SettingsPage(self.stage, self)}
        self._geom = (0, 0)
        self._last_count, self._dirty, self._last_refresh = getattr(tracker, "click_count", 0), False, 0.0
        root.bind("<Configure>", self._on_root_conf)
        self.sidebar.set_paused(getattr(tracker, "paused", False))
        self.layout(*self.size)
        self.show("overview")
        self._poll()
        self._slow()

    # ---- layout
    def _on_root_conf(self, e):
        if e.widget is self.root and e.width > 200:
            self.layout(e.width, e.height)

    def layout(self, W, H):
        if (W, H) == self._geom:
            return
        self._geom = (W, H)
        sb, hh = T.s(SIDEBAR_W), T.s(HEADER_H)
        self.sidebar.place(x=0, y=0, width=sb, height=H)
        self.main.place(x=sb, y=0, width=W - sb, height=H)
        self.header.place(x=0, y=0, width=W - sb, height=hh)
        self.stage.place(x=0, y=hh, width=W - sb, height=H - hh)
        self.pages[self.tab].place(x=0, y=0, width=W - sb, height=H - hh)
        if self.setup is not None:
            self.setup.place(x=0, y=0, width=W, height=H)
        self.redraw()

    def root_w(self):
        return self._geom[0] or self.size[0]

    def root_h(self):
        return self._geom[1] or self.size[1]

    def start_setup(self, first_time=False, start=0, scanner=None):
        if self.setup is not None:
            return
        from onboarding import SetupFlow
        kw = {"scanner": scanner} if scanner else {}
        self.setup = SetupFlow(self.root, self, first_time, start, on_done=self._setup_done, **kw)
        self.setup.start()

    def _setup_done(self, completed, apps, sites, ghost=None):
        self.setup = None
        if self.on_ready:
            self.on_ready()
            self.on_ready = None
        tab = getattr(self, "after_setup_tab", None)
        self.show(tab or ("inventory" if (apps or sites) else "overview"))
        self.refresh()
        if ghost is not None:
            if completed:
                self.start_tour(ghost)
            else:
                ghost.close()

    # ---- the guided tour: the ghost cursor clicks each tab and explains it
    TOUR = {"overview": "Home shows how ready your PC is to recover, and what to protect next.",
            "inventory": "Inventory is your recovery list: apps and sites you can't lose.",
            "recovery": "Recovery downloads those installers into one folder for you.",
            "suggestions": "Insights spots unprotected apps, unused software and subscriptions.",
            "account": "Account backs up your recovery list, so a new PC can restore it.",
            "settings": "Settings has backup, the ignore list and your privacy options."}

    def start_tour(self, ghost=None):
        from guide import GhostCursor
        if self.setup is not None:
            return
        if getattr(self, "tour", None):
            self.tour.close()
        ghost = ghost or GhostCursor(self.root, self.motion)
        self.tour = ghost

        def item_pos(i):
            return lambda: (self.sidebar.winfo_rootx() + T.s(110),
                            self.sidebar.winfo_rooty() + self.sidebar._top() + i * self.sidebar._pitch() + T.s(20))
        script = [("say", "Quick tour! I'll click through the tabs for you.")]
        for i, (key, _) in enumerate(Sidebar.ITEMS):
            script += [("move", item_pos(i)), ("click", lambda k=key: self.show(k)), ("say", self.TOUR[key]), ("wait", 2.6)]
        script += [("say", "That's it. Replay this tour any time from Settings."), ("wait", 2.2)]
        ghost.run(script)
        self.root.after(int(1000 * len(Sidebar.ITEMS) * 3.2 + 4500), lambda g=ghost: self._end_tour(g))

        def stop_on_user_click(e, g=ghost):
            self._end_tour(g)
        self._tour_bind = self.root.bind("<ButtonPress>", stop_on_user_click, add="+")

    def _end_tour(self, ghost):
        if getattr(self, "tour", None) is ghost:
            self.tour = None
            ghost.leave()

    def redraw(self):
        """Redraws the header; App is also the spring owner of the title fade."""
        h = self.header
        h.delete("all")
        t = clamp(self.title_reveal.value, 0, 1)
        h.create_text(T.s(32), T.s(42) + (1 - t) * T.s(8), text=TITLES[self.tab], font=T.F(24, "bold"),
                      fill=mix(T.BG, T.TEXT, t), anchor="w")
        h.create_text(T.s(32), T.s(74) + (1 - t) * T.s(8), text=TAGLINES[self.tab], font=T.F(10),
                      fill=mix(T.BG, T.SUB, t), anchor="w")

    # ---- navigation
    def show(self, key):
        self.tab = key
        W, H = self._geom if self._geom != (0, 0) else self.size
        sb, hh = T.s(SIDEBAR_W), T.s(HEADER_H)
        for k, p in self.pages.items():
            if k != key:
                p.place_forget()
        self.pages[key].place(x=0, y=0, width=W - sb, height=H - hh)
        self.sidebar.select(key, notify=False)
        self.title_reveal.jump(0)
        self.title_reveal.to(1)
        self.redraw()
        self.pages[key].enter()

    def toggle_pause(self):
        self.tracker.paused = not self.tracker.paused
        self.sidebar.set_paused(self.tracker.paused)

    # ---- data refresh
    def refresh(self):
        self._last_refresh, self._dirty = self.motion.clock(), False
        try:
            self.pages[self.tab].update_data()
        except Exception:
            if os.environ.get("CLICKSCOPE_DEBUG"):
                raise

    def _poll(self):
        c = getattr(self.tracker, "click_count", 0)
        if c != self._last_count:
            self._last_count = c
            self.sidebar.pulse()
            self._dirty = True
        if self._dirty and self.motion.clock() - self._last_refresh > 0.6:
            self.refresh()
        self.root.after(150, self._poll)

    def _slow(self):
        if self.motion.clock() - self._last_refresh > 2.5:
            self.refresh()
        self.root.after(3000, self._slow)
