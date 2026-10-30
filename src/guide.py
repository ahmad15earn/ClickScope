"""A small blue triangle 'ghost cursor' that moves on its own (independent of the real mouse),
points at things, performs example clicks and narrates, like a person showing you around.

Runs in its own transparent, borderless, click-through-where-empty window so it can glide over the app.
Script steps: ("say", text) | ("move", fn) | ("click", fn|None) | ("wait", seconds) | ("park", fn)
where fn() returns the target as screen coordinates (x, y), or None.
"""
import math
import tkinter as tk

import theme as T
from motion import Spring, clamp, mix
from widgets import measure, rrect

KEY = "#010203"      # colour made transparent on Windows
BLUE = "#1F5BFF"


def rounded_triangle(pts, t=0.28):
    """Smooth-polygon points for a triangle with rounded corners."""
    out = []
    for i, v in enumerate(pts):
        a, b = pts[i - 1], pts[(i + 1) % len(pts)]
        out += [v[0] + (a[0] - v[0]) * t, v[1] + (a[1] - v[1]) * t, v[0], v[1],
                v[0] + (b[0] - v[0]) * t, v[1] + (b[1] - v[1]) * t]
    return out


class GhostCursor:
    BW, BH, M = 380, 170, 22

    def __init__(self, root, motion, start=None):
        self.root, self.motion, self.alive = root, motion, True
        self.text, self.token, self.parking = "", 0, None
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.win.configure(bg=KEY)
        self.cv = tk.Canvas(self.win, width=T.s(self.BW), height=T.s(self.BH), bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack()
        self.x = Spring(motion, self, 0.0, response=0.62, eps=0.4)
        self.y = Spring(motion, self, 0.0, response=0.62, eps=0.4)
        self.press = Spring(motion, self, 0.0, response=0.12, eps=0.01)
        self.ripple = Spring(motion, self, 1.0, response=0.55, eps=0.004)
        sx, sy = start or self._offscreen()
        self.x.jump(sx)
        self.y.jump(sy)
        self.redraw()

    def _offscreen(self):
        try:
            return (self.root.winfo_rootx() + self.root.winfo_width() + 40, self.root.winfo_rooty() + self.root.winfo_height() + 40)
        except Exception:
            return (1200, 800)

    # ------------------------------------------------------------- drawing
    def redraw(self):
        if not self.alive:
            return
        m = T.s(self.M)
        try:
            self.win.geometry(f"+{int(self.x.value) - m}+{int(self.y.value) - m}")
        except Exception:
            pass
        c = self.cv
        c.delete("all")
        rp = self.ripple.value
        if rp < 0.99:
            r = T.s(5) + rp * T.s(20)
            c.create_oval(m - r, m - r, m + r, m + r, outline="#6D9BFF", width=max(1, int(T.s(3) * (1 - rp))))
        k = 1 - 0.16 * self.press.value
        sz = T.s(18) * k
        tri = [(m, m), (m + sz * 1.0, m + sz * 0.42), (m + sz * 0.42, m + sz * 1.0)]
        c.create_polygon(rounded_triangle([(x + T.s(1.5), y + T.s(2)) for x, y in tri]), smooth=True, fill="#9DB3E6", outline="")
        c.create_polygon(rounded_triangle(tri), smooth=True, fill=BLUE, outline="#FFFFFF", width=T.s(1.5))
        if self.text:
            tw = min(T.s(250), measure(self.text, 10, "bold") + T.s(4))
            lines = max(1, -(-measure(self.text, 10, "bold") // max(tw, 1)))
            bh = T.s(16) + lines * T.s(19)
            bx, by = m + T.s(24), m + T.s(20)
            rrect(c, bx, by, bx + tw + T.s(28), by + bh, T.s(14), fill="#1D1D1F", outline="")
            c.create_text(bx + T.s(14), by + T.s(8), text=self.text, font=T.F(10, "bold"), fill="#FFFFFF", anchor="nw", width=tw)

    # -------------------------------------------------------------- script
    def say(self, text):
        self.text = text
        self.redraw()

    def stop(self):
        self.token += 1
        self.parking = None

    def run(self, script):
        self.stop()
        tok = self.token
        self._step(script, 0, tok)

    def _later(self, tok, ms, fn):
        self.root.after(int(ms), lambda: fn() if (self.alive and tok == self.token) else None)

    def _step(self, script, i, tok):
        if not self.alive or tok != self.token or i >= len(script):
            return
        kind, arg = script[i]
        nxt = lambda ms=120: self._later(tok, ms, lambda: self._step(script, i + 1, tok))
        if kind == "say":
            self.say(arg)
            nxt(350)
        elif kind == "wait":
            nxt(arg * 1000)
        elif kind == "move":
            self._goto(arg, tok, lambda: nxt(160))
        elif kind == "click":
            self.press.to(1)

            def release():
                self.press.to(0)
                self.ripple.jump(0)
                self.ripple.to(1)
                if arg:
                    arg()
                nxt(500)
            self._later(tok, 140, release)
        elif kind == "park":
            self.parking = arg
            self._park(tok)

    def _goto(self, fn, tok, done, waited=0):
        t = fn()
        if t:
            self.x.to(t[0])
            self.y.to(t[1])

        def check():
            if not t or waited > 3000 or (abs(self.x.value - t[0]) < 3 and abs(self.y.value - t[1]) < 3):
                return done()
            self._goto(fn, tok, done, waited + 40)
        self._later(tok, 40, check)

    def _park(self, tok):
        """Stay on the target (and follow it if the window moves)."""
        t = self.parking() if self.parking else None
        if t:
            self.x.to(t[0])
            self.y.to(t[1])
        self._later(tok, 250, lambda: self._park(tok))

    def leave(self):
        """Fly away and close."""
        self.stop()
        self.say("")
        ox, oy = self._offscreen()
        self.x.to(ox)
        self.y.to(oy)
        self.root.after(1200, self.close)

    def close(self):
        self.alive = False
        self.token += 1
        try:
            self.win.destroy()
        except Exception:
            pass
