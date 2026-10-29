"""ClickScope UI: sidebar + pages, spring-animated, light theme only."""
import datetime
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import theme as T
from core import (ANALYSIS_DAYS, APP_DIR, MIN_ACTIVE_DAYS, build_suggestions, fmt_hour, quick_insights,
                  resource_path, weekly_apps)
from motion import Motion, Spring, clamp, mix, reduced_motion
from widgets import (AreaChartCard, BarChartCard, DonutCard, ListCard, PillButton, Segmented,
                     Sidebar, StatCard, Surface, line_height, measure, ring_sector, rrect, star_points)

RANGES = [("today", "Today"), ("7d", "7 days"), ("30d", "30 days"), ("all", "All time")]
RANGE_NAME = {"today": "today", "7d": "the last 7 days", "30d": "the last 30 days", "all": "all time"}
TITLES = {"overview": "Overview", "graphs": "Graphs", "inventory": "Inventory", "suggestions": "Suggestions", "settings": "Settings"}
HOUR_LABELS = ["12a", "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a", "9a", "10a", "11a",
               "12p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p", "10p", "11p"]
DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SIDEBAR_W, HEADER_H = 220, 92


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


# ------------------------------------------------------------ data builders
def activity_series(store, rng):
    """values, labels, tips, subtitle, indices that get an x label."""
    now = datetime.datetime.now()
    if rng == "today":
        hrs = store.hours("today")
        n = now.hour + 1
        vals = hrs[:n] + [None] * (24 - n)
        tips = [f"{fmt_hour(h)}  \u00b7  {v:,} clicks" if v is not None else "" for h, v in enumerate(vals)]
        return vals, HOUR_LABELS, tips, "Clicks per hour, today", {h for h in range(24) if h % 3 == 0}
    if rng in ("7d", "30d"):
        n = 7 if rng == "7d" else 30
    else:
        first = store.first_data_day()
        n = int(clamp((datetime.date.today() - first).days + 1 if first else 7, 7, 120))
    series = store.daily_series(n)
    vals = [v for _, v in series]
    labels = [DAY_SHORT[d.weekday()] if n <= 7 else day_label(d) for d, _ in series]
    tips = [f"{d.strftime('%a')}, {day_label(d)}  \u00b7  {v:,} clicks" for d, v in series]
    step = 1 if n <= 7 else 5 if n <= 30 else -(-n // 6)
    show = {i for i in range(n) if (n - 1 - i) % step == 0}
    sub = {"7d": "Clicks per day, last 7 days", "30d": "Clicks per day, last 30 days"}.get(rng, "Clicks per day, all time")
    return vals, labels, tips, sub, show


def delta_text(store, rng):
    today, day = datetime.date.today(), datetime.timedelta
    if rng == "today":
        cur, prev, name = store.total("today"), store.total_between(today - day(1), today - day(1)), "yesterday"
    elif rng == "7d":
        cur, prev, name = store.total("7d"), store.total_between(today - day(13), today - day(7)), "previous 7 days"
    elif rng == "30d":
        cur, prev, name = store.total("30d"), store.total_between(today - day(59), today - day(30)), "previous 30 days"
    else:
        return ""
    if prev <= 0:
        return ""
    pct = (cur - prev) / prev * 100
    if prev < 100 or abs(pct) > 500:  # too little history to compare fairly
        return ""
    arrow = "\u2191" if pct >= 0 else "\u2193"
    return f"{arrow} {abs(pct):.0f}% vs {name}"


def top_with_others(store, kind, rng, keep=5):
    rows = store.top(kind, rng)
    if len(rows) <= keep + 1:
        return rows
    return rows[:keep] + [("Others", sum(n for _, n in rows[keep:]))]


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


class OverviewPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.s_total = StatCard(self, m, "Total clicks")
        self.s_apps = StatCard(self, m, "Apps used")
        self.s_sites = StatCard(self, m, "Websites")
        self.s_peak = StatCard(self, m, "Busiest hour")
        self.chart = AreaChartCard(self, m, "Activity")
        self.apps = ListCard(self, m, "Applications", self.update_data, lambda n: self._ignore("app", n), self._keep)
        self.sites = ListCard(self, m, "Websites", self.update_data, lambda n: self._ignore("site", n))
        self.cards = [self.s_total, self.s_apps, self.s_sites, self.s_peak, self.chart, self.apps, self.sites]

    def _keep(self, name):
        self.app.store.toggle_keep(name)
        self.update_data()

    def _ignore(self, kind, name):
        if messagebox.askyesno("ClickScope", f"Stop counting clicks in \u201c{name}\u201d?\n\nIts existing counts are removed too. "
                                              "You can undo this in Settings > Reset ignore list."):
            self.app.store.add_ignore(kind, name)
            self.app.refresh()

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        cw = (iw - 3 * G) // 4
        sh = T.s(112)
        for i, c in enumerate((self.s_total, self.s_apps, self.s_sites, self.s_peak)):
            c.place(x=P + i * (cw + G), y=0, width=cw, height=sh)
        remaining = h - sh - 2 * G - T.s(26)
        ch = int(clamp(remaining * 0.40, T.s(200), T.s(280)))
        self.chart.place(x=P, y=sh + G, width=iw, height=ch)
        ly = sh + 2 * G + ch
        lw = (iw - G) // 2
        lh = max(T.s(200), h - ly - T.s(26))
        self.apps.place(x=P, y=ly, width=lw, height=lh)
        self.sites.place(x=P + lw + G, y=ly, width=lw, height=lh)
        cap = max(3, (lh - T.s(64) - T.s(30)) // T.s(46))
        self.apps.capacity = self.sites.capacity = cap

    def update_data(self):
        st, r = self.app.store, self.app.rng
        self.apps.kept = set(st.kept())
        self.s_total.set_number(st.total(r), delta_text(st, r))
        apps, sites = st.top("app", r, 1), st.top("site", r, 1)
        self.s_apps.set_number(st.count("app", r), f"Top: {apps[0][0]}" if apps else "No clicks yet")
        off = st.get("track_sites", "1") != "1"
        self.s_sites.set_number(st.count("site", r),
                                f"Top: {sites[0][0]}" if sites else ("Tracking is off" if off else "No clicks yet"))
        ph = st.busiest_hour(r)
        self.s_peak.set_label(fmt_hour(ph), "Most clicks" if ph is not None else "No clicks yet")
        vals, labels, tips, sub, show = activity_series(st, r)
        self.chart.set_data(vals, labels, tips, sub, show)
        for kind, card, empty in (
                ("app", self.apps, "No clicks yet. Use your PC as usual and they will show up here."),
                ("site", self.sites, "Website tracking is turned off in Settings." if off
                 else "No website clicks yet. Click around in your browser.")):
            card.set_rows(st.top(kind, r, card.capacity, desc=(card.mode == "most")), empty)


class GraphsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.kind = "app"
        self.donut = DonutCard(self, m, self._kind)
        self.week = BarChartCard(self, m, "Busiest days")
        self.hours = BarChartCard(self, m, "Busiest hours")
        self.cards = [self.donut, self.week, self.hours]

    def _kind(self, k):
        self.kind = k
        self.update_data()

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        top_h = int(clamp((h - G - T.s(26)) * 0.5, T.s(230), T.s(330)))
        dw = int(iw * 0.6)
        self.donut.place(x=P, y=0, width=dw, height=top_h)
        self.week.place(x=P + dw + G, y=0, width=iw - dw - G, height=top_h)
        self.hours.place(x=P, y=top_h + G, width=iw, height=max(T.s(200), h - top_h - G - T.s(26)))

    def update_data(self):
        st, r = self.app.store, self.app.rng
        items = top_with_others(st, self.kind, r)
        total = st.total(r) if self.kind == "app" else sum(n for _, n in st.top("site", r))
        self.donut.set_items(items, self.kind, total)
        wd = st.weekday_totals(r)
        self.week.set_data(wd, DAY_SHORT, [f"{DAY_FULL[i]}  \u00b7  {v:,} clicks" for i, v in enumerate(wd)],
                           f"Total clicks per weekday, {RANGE_NAME[r]}", set(range(7)))
        hrs = st.hours(r)
        self.hours.set_data(hrs, HOUR_LABELS, [f"{fmt_hour(h)}  \u00b7  {v:,} clicks" for h, v in enumerate(hrs)],
                            f"When you click most, {RANGE_NAME[r]}", {h for h in range(24) if h % 3 == 0})


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
    def __init__(self, parent, motion, item):
        super().__init__(parent, motion)
        self.item = item

    @staticmethod
    def height_for(item, width):
        avail = width - T.s(24 + 52 + 24)
        lines = max(1, math.ceil(measure(item["text"], 10) * 1.06 / max(avail, 60)))
        return T.s(26) + line_height(12, "bold") + T.s(6) + lines * line_height(10) + T.s(22)

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
        self.text(x, pad + line_height(12, "bold") + T.s(4), it["text"], 10, fill=T.SUB, width=self.W - x - pad)


class SuggestionsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.learning = LearningCard(self, app.motion)
        self.checkin = CheckinCard(self, app.motion, self._toggle)
        self.items, self.sig, self.ready = [], None, False
        self.cards = [self.learning, self.checkin]

    def _toggle(self, name):
        self.app.store.toggle_keep(name)
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
            self.checkin.set_data(day, quick_insights(st), weekly_apps(st), st.kept())
            self.layout(self.W, self.H)
            return
        sug = build_suggestions(st, "30d")
        sig = tuple((i["title"], i["text"]) for i in sug)
        if sig == self.sig:
            return
        self.sig, self.ready = sig, True
        for c in self.items:
            c.destroy()
        self.items = [SuggestionCard(self, self.app.motion, it) for it in sug]
        self.cards = list(self.items)
        self.layout(self.W, self.H)
        for i, c in enumerate(self.items):
            c.enter(delay=i * 70)


class InventoryPage(Page):
    """Apps the user marked as must-keep. Importance is chosen by the user, not by click counts."""

    def __init__(self, parent, app):
        super().__init__(parent, app)
        m = app.motion
        self.card = Surface(self, m)
        self.cards = [self.card]
        self.info = []
        self.card.draw = self._draw
        self.card.bind("<ButtonPress-1>", self._click)
        self.btns = [PillButton(self.card, m, "Add app\u2026", self._add, "dark"),
                     PillButton(self.card, m, "Export recovery checklist", self._export, "soft")]

    def layout(self, w, h):
        P = T.s(32)
        self.card.place(x=P, y=0, width=w - 2 * P, height=h - T.s(26))

    def update_data(self):
        self.info = self.app.store.keep_info()
        self.card.redraw()

    def _pitch(self):
        return T.s(52)

    def _cap(self):
        return max(1, (self.card.H - T.s(150)) // self._pitch())

    def _click(self, e):
        if T.s(20) <= e.x <= T.s(56):
            i = (e.y - T.s(104)) // self._pitch()
            if 0 <= i < min(len(self.info), self._cap()):
                self.app.store.toggle_keep(self.info[int(i)][0])
                self.update_data()

    def _draw(self):
        c, pad = self.card, T.s(28)
        c.text(pad, T.s(22), "Recovery inventory", 14, "bold")
        c.text(pad, T.s(48), "Clicks measure habit, not importance. Mark the apps you must get back first if your PC "
                              "fails or is reinstalled, even ones you open once a week.", 10, fill=T.SUB, width=c.W - 2 * pad)
        y0 = T.s(104)
        if not self.info:
            c.text(pad, y0 + T.s(10), "Nothing here yet. Tap the \u2605 next to an app in Overview, answer the weekly "
                                       "check-in, or add an app by name.", 10, fill=T.SUB, width=c.W - 2 * pad)
        for i, (name, n, last) in enumerate(self.info[: self._cap()]):
            y = y0 + i * self._pitch()
            c.create_line(pad, y - T.s(8), c.W - pad, y - T.s(8), fill=T.LINE)
            c.create_polygon(star_points(pad + T.s(10), y + T.s(14), T.s(10)), fill=c.fade(T.AMBER), outline=c.fade(T.AMBER))
            c.text(pad + T.s(36), y + T.s(3), name, 11, "bold")
            if last:
                ago = (datetime.date.today() - last).days
                seen = "today" if ago == 0 else f"{ago} day{'s' if ago != 1 else ''} ago"
                sub = f"{n:,} clicks  \u00b7  last clicked {seen}"
            else:
                sub = "Not seen yet  \u00b7  added manually"
            c.text(pad + T.s(36), y + T.s(24), sub, 9, fill=T.SUB)
        extra = len(self.info) - self._cap()
        if extra > 0:
            c.text(pad, c.H - T.s(92), f"+{extra} more (included in the exported checklist)", 9, fill=T.SUB, anchor="sw")
        x = pad
        for b in self.btns:
            c.create_window(x, c.H - T.s(66), window=b, anchor="nw")
            x += b.w + T.s(10)

    def _add(self):
        name = simpledialog.askstring("ClickScope", "App name to add to your recovery inventory\n(for example: your backup tool):")
        if name and name.strip():
            st = self.app.store
            if name.strip() not in st.kept():
                st.toggle_keep(name.strip())
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


class SettingsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        m, st = app.motion, app.store
        self.general, self.data, self.privacy = Surface(self, m), Surface(self, m), Surface(self, m)
        self.cards = [self.general, self.data, self.privacy]
        self.on = [st.get("track_sites", "1") == "1", autostart_enabled()]
        self.knob = [Spring(m, self.general, 1.0 if v else 0.0, response=0.25) for v in self.on]
        self.rows = [("Count clicks per website", "Uses the browser tab title to name the site, never the URL."),
                     ("Start with Windows", "Launches minimized so tracking runs in the background.")]
        self.general.draw, self.data.draw, self.privacy.draw = self._draw_general, self._draw_data, self._draw_privacy
        for i in range(2):
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
                     PillButton(self.data, m, "Clear all data", self._clear, "danger")]

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        gh, dh = T.s(168), T.s(236)
        self.general.place(x=P, y=0, width=iw, height=gh)
        self.data.place(x=P, y=gh + G, width=iw, height=dh)
        self.privacy.place(x=P, y=gh + dh + 2 * G, width=iw, height=T.s(160))

    def _toggle(self, i):
        self.on[i] = not self.on[i]
        self.knob[i].to(1.0 if self.on[i] else 0.0)
        if i == 0:
            self.app.store.set("track_sites", "1" if self.on[0] else "0")
        else:
            try:
                set_autostart(self.on[1])
            except Exception as e:
                self.on[1] = not self.on[1]
                self.knob[1].to(1.0 if self.on[1] else 0.0)
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
               "or what is on your screen, and it never connects to the internet.\n\n"
               "Only totals are saved: per day, per app and per website. Clicks inside ClickScope are ignored. "
               "Closing the window keeps ClickScope counting in the background (minimized). "
               "Use Quit ClickScope in the sidebar to exit completely.")
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
    def __init__(self, root, store, tracker, demo=False, size=(1120, 740), on_quit=None):
        T.init(root)
        self.root, self.store, self.tracker, self.demo = root, store, tracker, demo
        self.on_quit = on_quit or root.destroy
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
        self.sidebar = Sidebar(root, self.motion, self.show, self.toggle_pause, self.on_quit, logo=self.logo, demo=demo)
        self.main = tk.Frame(root, bg=T.BG)
        self.header = tk.Canvas(self.main, bg=T.BG, highlightthickness=0, bd=0)
        self.title_reveal = Spring(self.motion, self, 1.0, response=0.5)
        self.seg = Segmented(self.main, self.motion, RANGES, self.set_range, seg_w=T.s(78), h=T.s(32), bg=T.BG)
        self.seg.select(self.rng, silent=True)
        self.seg.pos.jump(self.seg.sel)
        self.stage = tk.Frame(self.main, bg=T.BG)
        self.pages = {"overview": OverviewPage(self.stage, self), "graphs": GraphsPage(self.stage, self),
                      "inventory": InventoryPage(self.stage, self),
                      "suggestions": SuggestionsPage(self.stage, self), "settings": SettingsPage(self.stage, self)}
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
        self.redraw()

    def redraw(self):
        """Redraws the header; App is also the spring owner of the title fade."""
        h = self.header
        h.delete("all")
        t = clamp(self.title_reveal.value, 0, 1)
        h.create_text(T.s(32), T.s(50) + (1 - t) * T.s(8), text=TITLES[self.tab], font=T.F(24, "bold"),
                      fill=mix(T.BG, T.TEXT, t), anchor="w")
        W = self._geom[0] or self.size[0]
        if self.tab in ("overview", "graphs"):
            self.seg.place(x=W - T.s(SIDEBAR_W) - T.s(32) - (self.seg.sw * len(RANGES) + 4), y=T.s(30))
        else:
            self.seg.place_forget()

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

    def set_range(self, key):
        self.rng = key
        self.refresh()

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
