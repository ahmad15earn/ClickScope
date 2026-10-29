"""ClickScope UI: sidebar + pages, spring-animated, light theme only."""
import datetime
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import theme as T
from core import ANALYSIS_DAYS, APP_DIR, build_suggestions, fmt_hour, resource_path
from motion import Motion, Spring, clamp, mix, reduced_motion
from widgets import (AreaChartCard, BarChartCard, DonutCard, ListCard, PillButton, Segmented,
                     Sidebar, StatCard, Surface, line_height, measure, rrect)

RANGES = [("today", "Today"), ("7d", "7 days"), ("30d", "30 days"), ("all", "All time")]
RANGE_NAME = {"today": "today", "7d": "the last 7 days", "30d": "the last 30 days", "all": "all time"}
TITLES = {"overview": "Overview", "graphs": "Graphs", "suggestions": "Suggestions", "settings": "Settings"}
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
        self.apps = ListCard(self, m, "Applications", self.update_data)
        self.sites = ListCard(self, m, "Websites", self.update_data)
        self.cards = [self.s_total, self.s_apps, self.s_sites, self.s_peak, self.chart, self.apps, self.sites]

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        cw = (iw - 3 * G) // 4
        sh = T.s(112)
        for i, c in enumerate((self.s_total, self.s_apps, self.s_sites, self.s_peak)):
            c.place(x=P + i * (cw + G), y=0, width=cw, height=sh)
        remaining = h - sh - 2 * G - T.s(26)
        ch = int(clamp(remaining * 0.46, T.s(210), T.s(300)))
        self.chart.place(x=P, y=sh + G, width=iw, height=ch)
        ly = sh + 2 * G + ch
        lw = (iw - G) // 2
        lh = max(T.s(200), h - ly - T.s(26))
        self.apps.place(x=P, y=ly, width=lw, height=lh)
        self.sites.place(x=P + lw + G, y=ly, width=lw, height=lh)
        cap = max(3, (lh - T.s(64) - T.s(8)) // T.s(46))
        self.apps.capacity = self.sites.capacity = cap

    def update_data(self):
        st, r = self.app.store, self.app.rng
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
        self.day, self.unlock, self.stats = 1, None, (0, 0, 0)
        self.ring = Spring(motion, self, 0.0, response=0.9, eps=0.002)
        self.dots = Spring(motion, self, 0.0, response=1.1, eps=0.002)

    def set_progress(self, day, unlock, stats):
        self.day, self.unlock, self.stats = day, unlock, stats
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
        pad = T.s(32)
        d = min(T.s(190), self.H - T.s(190))
        thick = T.s(14)
        cx, cy = pad + d / 2 + T.s(8), pad + d / 2 + T.s(6)
        r = d / 2 - thick / 2
        box = (cx - r, cy - r, cx + r, cy + r)
        self.create_oval(*box, outline=T.TRACK, width=thick)
        ext = -360 * clamp(self.ring.value, 0, 1)
        if abs(ext) > 1:
            self.create_arc(*box, start=90, extent=ext, style="arc", outline=T.ACCENT, width=thick)
            a = math.radians(90 + ext)
            for ex, ey in ((cx + r * math.cos(a), cy - r * math.sin(a)), (cx, cy - r)):  # round caps
                self.create_oval(ex - thick / 2, ey - thick / 2, ex + thick / 2, ey + thick / 2, fill=T.ACCENT, outline="")
        self.text(cx, cy - T.s(40), "Day", 10, fill=T.SUB, anchor="center", rise=False)
        self.text(cx, cy + T.s(2), str(self.day), 34, "bold", anchor="center", rise=False)
        self.text(cx, cy + T.s(42), f"of {ANALYSIS_DAYS}", 10, fill=T.SUB, anchor="center", rise=False)

        tx = cx + d / 2 + T.s(48)
        tw = self.W - tx - pad
        self.text(tx, pad, "Learning your habits", 20, "bold")
        unlock = f"{self.unlock.strftime('%B')} {self.unlock.day}" if self.unlock else ""
        body = ("ClickScope studies 30 days of your clicks before it suggests anything, so tips come from "
                "real patterns and not one lucky afternoon. Meanwhile, Overview and Graphs already work.")
        self.text(tx, pad + T.s(38), body, 10, fill=T.SUB, width=tw)
        lines = max(1, math.ceil(measure(body, 10) * 1.05 / max(tw, 50)))
        y = pad + T.s(38) + lines * line_height(10) + T.s(16)
        label = f"Suggestions unlock on {unlock}"
        rrect(self, tx, y, tx + measure(label, 10, "bold") + T.s(28), y + T.s(32), T.s(16),
              fill=self.fade(T.ACCENT_SOFT), outline="")
        self.text(tx + T.s(14), y + T.s(16), label, 10, "bold", fill=T.ACCENT_D, anchor="w", bg=T.ACCENT_SOFT)
        clicks, apps, sites = self.stats
        sy = y + T.s(54)
        for i, (val, lab) in enumerate(((clicks, "clicks analyzed"), (apps, "apps seen"), (sites, "websites seen"))):
            x = tx + i * T.s(150)
            self.text(x, sy, f"{val:,}", 18, "bold")
            self.text(x, sy + T.s(28), lab, 9, fill=T.SUB)

        gy = self.H - T.s(44)
        slot = (self.W - 2 * pad) / ANALYSIS_DAYS
        dr = min(T.s(7), slot * 0.32)
        shown = self.dots.value * ANALYSIS_DAYS
        self.text(pad, gy - T.s(34), "Your first 30 days", 9, fill=T.SUB)
        for i in range(ANALYSIS_DAYS):
            x = pad + slot * (i + 0.5)
            if i < self.day - 1 and i < shown:
                self.create_oval(x - dr, gy - dr, x + dr, gy + dr, fill=T.ACCENT, outline="")
            elif i == self.day - 1 and i < shown + 1:
                self.create_oval(x - dr - 2, gy - dr - 2, x + dr + 2, gy + dr + 2, fill=T.CARD, outline=T.ACCENT, width=T.s(2.5))
                self.create_oval(x - dr * 0.45, gy - dr * 0.45, x + dr * 0.45, gy + dr * 0.45, fill=T.ACCENT, outline="")
            else:
                self.create_oval(x - dr, gy - dr, x + dr, gy + dr, fill=T.TRACK, outline="")


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
        self.items, self.sig, self.ready = [], None, False
        self.cards = [self.learning]

    def layout(self, w, h):
        P, G = T.s(32), T.s(14)
        iw = w - 2 * P
        if not self.ready:
            self.learning.place(x=P, y=0, width=iw, height=int(clamp(h - T.s(30), T.s(340), T.s(380))))
            return
        self.learning.place_forget()
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
            self.ready, self.sig, self.cards = False, None, [self.learning]
            self.learning.set_progress(day, unlock, (st.total("all"), st.count("app", "all"), st.count("site", "all")))
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
                     PillButton(self.data, m, "Clear all data", self._clear, "danger")]

    def layout(self, w, h):
        P, G = T.s(32), T.s(16)
        iw = w - 2 * P
        gh, dh = T.s(176), T.s(150)
        self.general.place(x=P, y=0, width=iw, height=gh)
        self.data.place(x=P, y=gh + G, width=iw, height=dh)
        self.privacy.place(x=P, y=gh + dh + 2 * G, width=iw, height=T.s(176))

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
        c.text(pad, c.H - T.s(14), f"Saved only on this PC:  {APP_DIR}", 8, fill=T.FAINT, anchor="sw")

    def _draw_privacy(self):
        c, pad = self.privacy, T.s(24)
        c.text(pad, T.s(18), "Your privacy", 12, "bold")
        msg = ("ClickScope only counts mouse clicks. It never records keystrokes, screenshots, cursor movement "
               "or what is on your screen, and it never connects to the internet.\n\n"
               "Only totals are saved: per day, per app and per website. Clicks inside ClickScope are ignored. "
               "Tracking runs while the app is open, so minimize the window to keep it going in the background; "
               "closing the window quits it.")
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

    def _clear(self):
        if messagebox.askyesno("ClickScope", "Delete all saved click data?\nThe 30-day learning period "
                                              "will also start over. This cannot be undone."):
            self.app.store.clear()
            self.app.refresh()


# ---------------------------------------------------------------------- app
class App:
    def __init__(self, root, store, tracker, demo=False, size=(1120, 740)):
        T.init(root)
        self.root, self.store, self.tracker, self.demo = root, store, tracker, demo
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
        self.seg = Segmented(self.main, self.motion, RANGES, self.set_range, seg_w=T.s(78), h=T.s(32), bg=T.BG)
        self.seg.select(self.rng, silent=True)
        self.seg.pos.jump(self.seg.sel)
        self.stage = tk.Frame(self.main, bg=T.BG)
        self.pages = {"overview": OverviewPage(self.stage, self), "graphs": GraphsPage(self.stage, self),
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
