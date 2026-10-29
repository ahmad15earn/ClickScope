"""First-run setup: scan installed apps and favourite sites, guided by a small cursor companion."""
import threading
import tkinter as tk

import scanner as real_scanner
import theme as T
from core import resource_path
from guide import CursorGuide
from motion import Spring, clamp
from widgets import ChecklistCard, PillButton, Surface, line_height, measure, rrect

STEPS = ["Welcome", "Scan apps", "Your apps", "Browsers", "Your sites", "Done"]
GUIDE = ["Hi! I'll guide you. It takes about a minute.", "Scanning your apps...", "Tick the apps you can't live without",
         "Which browsers should I look at?", "Tick your favourite sites", "Thank you!"]


class SetupFlow(tk.Frame):
    def __init__(self, parent, app, first_time, start=0, scanner=real_scanner, on_done=None):
        super().__init__(parent, bg=T.BG)
        self.app, self.m, self.store, self.sc = app, app.motion, app.store, scanner
        self.first, self.on_done = first_time, on_done
        self.step, self.apps, self.sites, self.browsers = -1, [], [], []
        self.added_apps = self.added_sites = 0
        self.busy = False
        self.W = self.H = 0
        self.prog = Spring(self.m, self, 0.0, response=2.2, eps=0.003)
        try:
            self.big_logo = tk.PhotoImage(file=resource_path("assets/logo_128.png"))
        except Exception:
            self.big_logo = None
        self.hero = Surface(self, self.m)
        self.hero.draw = self._draw_hero
        self.list = ChecklistCard(self, self.m, "", self._list_changed)
        self.skip = PillButton(self, self.m, "Skip for now", lambda: self.finish(False), "soft", bg=T.BG)
        self.next = PillButton(self, self.m, "Start setup", self._next, "accent", bg=T.BG, width=T.s(214), h=T.s(40))
        self.all_btn = PillButton(self.list, self.m, "Select all", lambda: self.list.select_all_shown(), "soft")
        self.list.buttons = [self.all_btn]
        try:
            self.guide = CursorGuide(app.root, self.m, resource_path("assets/logo_64.png"))
        except Exception:
            self.guide = None
        self.bind("<Configure>", self._conf)
        self._pending = start

    def redraw(self):  # spring owner (progress bar)
        self.hero.redraw()

    # ------------------------------------------------------------- layout
    def start(self):
        self.place(x=0, y=0, width=self.app.root_w(), height=self.app.root_h())
        self.tkraise()
        self.go(self._pending)

    def _conf(self, e):
        self.W, self.H = e.width, e.height
        self.layout()

    def _wide(self):
        return self.step in (0, 5)

    def layout(self):
        W, H = self.W, self.H
        if W < 200:
            return
        M = max(T.s(28), (W - T.s(900)) // 2)
        cw, top = W - 2 * M, T.s(32)
        bar_y = H - T.s(70)
        if self._wide():
            self.hero.place(x=M, y=top, width=cw, height=min(bar_y - top - T.s(12), T.s(500)))
            self.list.place_forget()
        else:
            hh = T.s(160)
            self.hero.place(x=M, y=top, width=cw, height=hh)
            self.list.place(x=M, y=top + hh + T.s(14), width=cw, height=bar_y - top - hh - T.s(26))
        if self.step != 5:
            self.skip.place(x=M, y=bar_y + T.s(8))
        if not self.busy:
            self.next.place(x=W - M - self.next.w, y=bar_y + T.s(4))

    # -------------------------------------------------------------- steps
    def go(self, n):
        self.step = n
        if self.guide:
            self.guide.set_text(GUIDE[n])
        self.layout()
        if n == 0:
            self.next.restyle("Start setup", "accent")
        elif n == 1:
            self.next.place_forget()
            self.prog.jump(0)
            self.prog.to(0.9)
            self.busy = True
            self._run_bg(self.sc.scan_apps, self._apps_done)
        elif n == 2:
            kept = set(self.store.kept())
            self.list.title = "Your installed software"
            self.list.subtitle = "Tick the apps to get back first if your PC fails. Everything found is also saved in your full list."
            self.list.set_items([(a, a, d) for a, d in self.apps], (), {a for a, _ in self.apps if a in kept})
            self.all_btn.restyle("Select all", "soft")
            self._list_changed()
        elif n == 3:
            self.browsers = self.sc.detect_browsers()
            if not self.browsers:
                return self.go(5)
            self.list.title = "Your favourite websites"
            self.list.subtitle = ("ClickScope can read your bookmarks and most-visited sites once, on this PC only. "
                                  "Only domain names are saved, never page titles or full links. Tick the browsers to read.")
            self.list.set_items([(str(i), b[0], "Reads bookmarks and most-visited sites") for i, b in enumerate(self.browsers)])
            self.all_btn.restyle("Select all", "soft")
            self._list_changed()
        elif n == 4:
            kept = set(self.store.kept_sites())
            self.list.title = "Sites you use a lot"
            self.list.subtitle = "Tick the ones to remember, so you can open them again after a reset."
            self.list.set_items([(d, d, det) for d, det in self.sites], (), {d for d, _ in self.sites if d in kept})
            self._list_changed()
        elif n == 5:
            self.next.restyle("Start using ClickScope", "accent")
            self.skip.place_forget()
        self.hero.enter()
        self.hero.redraw()

    def _list_changed(self):
        k = len(self.list.new_selection())
        self.list.info = f"{k} selected" if k else "Nothing selected yet"
        if self.step == 2:
            self.next.restyle(f"Add {k} app{'s' if k != 1 else ''}" if k else "Continue", "accent")
        elif self.step == 3:
            self.next.restyle("Read selected" if k else "Skip websites", "accent")
        elif self.step == 4:
            self.next.restyle(f"Add {k} site{'s' if k != 1 else ''}" if k else "Continue", "accent")
        self.list.redraw()

    def _next(self):
        if self.busy:
            return
        s = self.step
        if s == 0:
            self.go(1)
        elif s == 2:
            for a in self.list.new_selection():
                self.store.set_keep(a, True)
                self.added_apps += 1
            self.go(3)
        elif s == 3:
            picks = [self.browsers[int(i)] for i in self.list.new_selection()]
            if not picks:
                return self.go(5)
            self.busy = True
            self.next.place_forget()
            self.list.place_forget()
            if self.guide:
                self.guide.set_text("Looking at your favourite sites...")
            self.step = 3.5
            self.prog.jump(0)
            self.prog.to(0.9)
            self._run_bg(lambda: [self.sc.read_sites(k, p) for _, k, p in picks], self._sites_done)
            self.hero.redraw()
        elif s == 4:
            for d in self.list.new_selection():
                self.store.toggle_keep_site(d, True)
                self.added_sites += 1
            self.go(5)
        elif s == 5:
            self.finish(True)

    def _apps_done(self, result, err):
        self.busy = False
        self.apps = result or []
        self.store.set_catalog("app", self.apps)
        self.prog.to(1.0)
        self.hero.redraw()
        self.after(900, lambda: self.go(2 if self.apps else 3))

    def _sites_done(self, result, err):
        self.busy = False
        merged = {}
        for lst in result or []:
            for d, det in lst:
                if d not in merged:
                    merged[d] = det
        self.sites = list(merged.items())
        self.store.set_catalog("site", self.sites)
        self.prog.to(1.0)
        self.after(700, lambda: self.go(4 if self.sites else 5))

    def _run_bg(self, fn, done):
        box = {}

        def work():
            try:
                box["v"] = fn()
            except Exception as e:  # never crash the setup because a scan failed
                box["e"] = e

        threading.Thread(target=work, daemon=True).start()

        def poll():
            if "v" in box or "e" in box:
                done(box.get("v"), box.get("e"))
            else:
                self.after(100, poll)
        poll()

    def finish(self, completed):
        if self.guide:
            self.guide.close()
            self.guide = None
        self.store.set("onboarded", "1" if completed else "skipped")
        if self.first:
            self.store.reset_first_run()
        self.destroy()
        if self.on_done:
            self.on_done(completed, self.added_apps, self.added_sites)

    # --------------------------------------------------------------- hero
    def _draw_hero(self):
        c, pad = self.hero, T.s(32)
        s = self.step
        # progress dots
        n = len(STEPS)
        for i in range(n):
            x = pad + i * T.s(20)
            on = i <= int(s)
            c.create_oval(x, T.s(26), x + T.s(10), T.s(36), fill=T.ACCENT if on else T.TRACK, outline="")
        if self._wide():
            cx = c.W / 2
            if self.big_logo:
                c.create_image(cx - self.big_logo.width() / 2, T.s(86), image=self.big_logo, anchor="nw")
            title = "Welcome to ClickScope" if s == 0 else "Thank you!"
            body = ("Let's set up in about a minute. ClickScope will look at the software and websites on this PC, so you "
                    "always have a recovery list if your computer ever fails. Everything stays on this PC."
                    if s == 0 else
                    "ClickScope is ready and now counting your clicks. Your full list of software is saved, and your "
                    "first suggestions unlock in 30 days. You can rescan any time from the Inventory tab.")
            y = T.s(86) + (self.big_logo.height() if self.big_logo else 0) + T.s(26)
            c.text(cx, y, title, 26, "bold", anchor="n")
            c.text(cx, y + T.s(50), body, 11, fill=T.SUB, anchor="n", width=min(T.s(600), c.W - 2 * pad), justify="center")
            if s == 5:
                yy = y + T.s(150)
                for i, (val, lab) in enumerate(((len(self.apps), "apps found"), (self.added_apps, "apps in your inventory"),
                                                (self.added_sites, "favourite sites saved"))):
                    x = cx + (i - 1) * T.s(210)
                    c.text(x, yy, f"{val:,}", 24, "bold", anchor="n", rise=False)
                    c.text(x, yy + T.s(36), lab, 9, fill=T.SUB, anchor="n", rise=False)
            return
        titles = {1: ("Looking at your PC", "Reading installed programs and Start Menu shortcuts. This only takes a moment."),
                  2: ("Pick the apps you can't live without", "Found %d apps. Tick the important ones." % len(self.apps)),
                  3: ("Your favourite websites", "Choose which browsers ClickScope may read, once."),
                  3.5: ("Looking at your favourite sites", "Reading bookmarks and most-visited domains on this PC."),
                  4: ("Sites you use a lot", "Found %d sites. Tick the ones to remember." % len(self.sites))}
        t, b = titles.get(s, ("", ""))
        c.text(pad, T.s(56), f"Step {min(int(s), 4)} of 4", 9, "bold", fill=T.ACCENT_D)
        c.text(pad, T.s(78), t, 20, "bold")
        c.text(pad, T.s(112), b, 10, fill=T.SUB, width=c.W - 2 * pad)
        if s in (1, 3.5):
            bw = c.W - 2 * pad
            y = c.H - T.s(34)
            rrect(c, pad, y, pad + bw, y + T.s(8), T.s(4), fill=T.TRACK, outline="")
            rrect(c, pad, y, pad + max(T.s(8), bw * clamp(self.prog.value, 0, 1)), y + T.s(8), T.s(4), fill=T.ACCENT, outline="")
