"""Custom-drawn widgets: rounded cards, charts, segmented control, buttons, sidebar."""
import math
import tkinter as tk
from tkinter import font as tkfont

import theme as T
from motion import Spring, clamp, mix

# ------------------------------------------------------------------ helpers
_fonts = {}


def measure(text, size, weight="normal"):
    key = (T.FAMILY, size, weight)
    if key not in _fonts:
        _fonts[key] = tkfont.Font(family=T.FAMILY, size=size, weight=weight)
    return _fonts[key].measure(text)


def line_height(size, weight="normal"):
    key = (T.FAMILY, size, weight)
    if key not in _fonts:
        _fonts[key] = tkfont.Font(family=T.FAMILY, size=size, weight=weight)
    return _fonts[key].metrics("linespace")


def rrect(c, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle (smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def fmt_k(v):
    v = float(v)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1000:
        return f"{v / 1000:.1f}k".replace(".0k", "k")
    return f"{int(round(v))}"


def nice_step(v):
    """Smallest 'nice' number >= v (1, 2, 2.5, 5, 10 x 10^n)."""
    if v <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * exp:
            return m * exp
    return 10 * exp


def spline(pts, steps=8):
    """Monotone cubic interpolation (smooth, never dips below the data)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    dx = [xs[i + 1] - xs[i] for i in range(n - 1)]
    dy = [ys[i + 1] - ys[i] for i in range(n - 1)]
    m = [d_y / d_x if d_x else 0 for d_x, d_y in zip(dx, dy)]
    t = [m[0]] + [0 if m[i - 1] * m[i] <= 0 else (m[i - 1] + m[i]) / 2 for i in range(1, n - 1)] + [m[-1]]
    for i in range(n - 1):
        if m[i] == 0:
            t[i] = t[i + 1] = 0
        else:
            a, b = t[i] / m[i], t[i + 1] / m[i]
            h = math.hypot(a, b)
            if h > 3:
                t[i], t[i + 1] = 3 * a / h * m[i], 3 * b / h * m[i]
    out = []
    for i in range(n - 1):
        for k in range(steps):
            u = k / steps
            h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
            h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
            out.append((xs[i] + dx[i] * u,
                        h00 * ys[i] + h10 * dx[i] * t[i] + h01 * ys[i + 1] + h11 * dx[i] * t[i + 1]))
    out.append(pts[-1])
    return out


def draw_icon(c, kind, cx, cy, col, sz, hole=T.CARD):
    h = sz / 2
    if kind == "overview":
        g = sz * 0.12
        q = (sz - g) / 2
        for i in (0, 1):
            for j in (0, 1):
                x, y = cx - h + i * (q + g), cy - h + j * (q + g)
                rrect(c, x, y, x + q, y + q, q * 0.32, fill=col, outline="")
    elif kind == "graphs":
        bw = sz * 0.26
        gap = (sz - 3 * bw) / 2
        for i, f in enumerate((0.5, 1.0, 0.72)):
            x = cx - h + i * (bw + gap)
            rrect(c, x, cy + h - sz * f, x + bw, cy + h, bw / 2, fill=col, outline="")
    elif kind == "suggestions":  # sparkle
        pts = []
        for i in range(8):
            ang = math.radians(i * 45 - 90)
            r = h if i % 2 == 0 else h * 0.34
            pts += [cx + r * math.cos(ang), cy + r * math.sin(ang)]
        c.create_polygon(pts, fill=col, outline="")
    elif kind == "settings":  # sliders
        for yy, kx in ((cy - h * 0.5, cx - h * 0.28), (cy + h * 0.5, cx + h * 0.34)):
            c.create_line(cx - h, yy, cx + h, yy, fill=col, width=2, capstyle="round")
            r = sz * 0.19
            c.create_oval(kx - r, yy - r, kx + r, yy + r, fill=hole, outline=col, width=2)


# ------------------------------------------------------------------ surface
class Surface(tk.Canvas):
    """Rounded white card that redraws itself; subclasses implement draw()."""
    RADIUS = 18

    def __init__(self, parent, motion, **kw):
        super().__init__(parent, bg=T.BG, highlightthickness=0, bd=0, **kw)
        self.motion = motion
        self.W = self.H = 0
        self.reveal = Spring(motion, self, 1.0, response=0.55)
        self.bind("<Configure>", self._conf)

    def _conf(self, e):
        self.W, self.H = e.width, e.height
        self.redraw()

    def enter(self, delay=0):
        """Content fades/rises in when its page is shown (cascade via delay)."""
        self.reveal.jump(0)
        self.motion.later(delay, lambda: self.reveal.to(1))

    def redraw(self):
        if self.W < 8 or self.H < 8:
            return
        self.delete("all")
        r = T.s(self.RADIUS)
        rrect(self, 1, 3, self.W - 1, self.H - 1, r, fill=T.SHADOW, outline="")
        rrect(self, 1, 1, self.W - 2, self.H - 3, r, fill=T.CARD, outline=T.LINE)
        self.draw()

    def draw(self):
        pass

    # text that fades in and rises slightly while the card is revealing
    def text(self, x, y, txt, size=10, weight="normal", fill=T.TEXT, anchor="nw", width=None,
             rise=True, bg=T.CARD, **kw):
        t = clamp(self.reveal.value, 0, 1)
        args = dict(text=txt, font=T.F(size, weight), fill=mix(bg, fill, t), anchor=anchor, **kw)
        if width:
            args["width"] = width
        return self.create_text(x, y + ((1 - t) * T.s(8) if rise else 0), **args)

    def fade(self, color, bg=T.CARD):
        return mix(bg, color, clamp(self.reveal.value, 0, 1))


# ----------------------------------------------------------------- stat card
class StatCard(Surface):
    def __init__(self, parent, motion, title, formatter=None):
        super().__init__(parent, motion)
        self.title, self.sub, self.fmt = title, "", formatter or (lambda v: f"{int(round(v)):,}")
        self.num = Spring(motion, self, 0.0, response=0.7, eps=0.4)
        self.label = None  # text mode (e.g. busiest hour)

    def set_number(self, v, sub=""):
        self.label = None
        self.sub = sub
        self.num.to(v)
        self.redraw()

    def set_label(self, txt, sub=""):
        self.label, self.sub = txt, sub
        self.redraw()

    def draw(self):
        pad = T.s(20)
        self.text(pad, T.s(18), self.title, 9, fill=T.SUB)
        self.text(pad, T.s(38), self.label if self.label is not None else self.fmt(self.num.value),
                  22, "bold")
        if self.sub:
            self.text(pad, self.H - T.s(24), self.sub, 9, fill=T.SUB)


# ---------------------------------------------------------------- area chart
class AreaChartCard(Surface):
    def __init__(self, parent, motion, title):
        super().__init__(parent, motion)
        self.title, self.subtitle = title, ""
        self.springs, self.valid, self.labels, self.tips, self.show = [], [], [], [], set()
        self.ymax = Spring(motion, self, 10.0, response=0.6, eps=0.05)
        self.hover = None
        self._pts, self._geo = [], (0, 0, 0, 0)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    def set_data(self, values, labels, tips, subtitle, show):
        """values: list of numbers (None = not reached yet, e.g. future hours)."""
        self.subtitle, self.labels, self.tips, self.show = subtitle, labels, tips, show
        self.valid = [v is not None for v in values]
        n = len(values)
        if n != len(self.springs):  # new shape: grow in from the baseline, left to right wave
            self.springs = [Spring(self.motion, self, 0.0, response=0.42 + 0.012 * i, eps=0.3) for i in range(n)]
        for sp, v in zip(self.springs, values):
            sp.to(v or 0)
        mx = max([v for v in values if v is not None] + [1])
        self.ymax.to(nice_step(mx * 1.1 / 4) * 4)
        self.redraw()

    def draw(self):
        pad = T.s(22)
        self.text(pad, T.s(18), self.title, 12, "bold")
        self.text(pad, T.s(40), self.subtitle, 9, fill=T.SUB)
        left, right = T.s(56), self.W - pad
        top, bottom = T.s(76), self.H - T.s(36)
        h = bottom - top
        ymax = max(self.ymax.value, 1)
        self._geo = (left, right, top, bottom)
        for i in range(5):
            y = bottom - h * i / 4
            self.create_line(left, y, right, y, fill=T.LINE if i else T.LINE2, width=1,
                             dash=None if i == 0 else (2, 4))
            self.text(left - T.s(10), y, fmt_k(ymax * i / 4), 8, fill=T.FAINT, anchor="e", rise=False)
        n = len(self.springs)
        if n == 0:
            return
        xs = [left + (right - left) * (i / (n - 1) if n > 1 else 0.5) for i in range(n)]
        last = max([i for i, v in enumerate(self.valid) if v] + [-1])
        self._pts = [(xs[i], bottom - clamp(self.springs[i].value, 0, ymax) / ymax * h) for i in range(last + 1)]
        if len(self._pts) >= 2:
            dense = spline(self._pts)
            # vertical gradient under the line: nested clamped polygons, strongest at the top
            bands = 14
            for k in range(bands):
                level = top + h * k / bands
                col = mix("#C4F2FA", "#FFFFFF", (k / (bands - 1)) ** 0.8)
                poly = [(x, max(y, level)) for x, y in dense]
                flat = [c for p in poly for c in p] + [dense[-1][0], bottom, dense[0][0], bottom]
                self.create_polygon(flat, fill=self.fade(col), outline="")
            flat = [c for p in dense for c in p]
            self.create_line(flat, fill=self.fade(T.ACCENT), width=T.s(3), capstyle="round", joinstyle="round")
        if self._pts:
            x, y = self._pts[-1]
            r = T.s(5)
            self.create_oval(x - r, y - r, x + r, y + r, fill=T.CARD, outline=self.fade(T.ACCENT), width=T.s(2.5))
        for i in range(n):
            if i in self.show and i < len(self.labels):
                self.text(xs[i], bottom + T.s(12), self.labels[i], 8, fill=T.FAINT, anchor="n", rise=False)
        self._draw_tip()

    def _move(self, e):
        left, right, top, bottom = self._geo
        n = len(self._pts)
        if n == 0 or not (top - T.s(30) <= e.y <= bottom + T.s(24)):
            return self._set_hover(None)
        total = len(self.springs)
        idx = round((e.x - left) / max(right - left, 1) * (total - 1)) if total > 1 else 0
        self._set_hover(int(clamp(idx, 0, n - 1)))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self._draw_tip()

    def _draw_tip(self):
        self.delete("tip")
        i = self.hover
        if i is None or i >= len(self._pts) or i >= len(self.tips):
            return
        x, y = self._pts[i]
        _, _, top, bottom = self._geo
        self.create_line(x, top, x, bottom, fill=T.LINE2, width=1, dash=(3, 3), tags="tip")
        r = T.s(5)
        self.create_oval(x - r, y - r, x + r, y + r, fill=T.CARD, outline=T.ACCENT, width=T.s(2.5), tags="tip")
        draw_tooltip(self, x, y - T.s(16), self.tips[i])


def draw_tooltip(c, x, y, txt, tag="tip"):
    """Dark rounded tooltip centred above (x, y)."""
    tw, th = measure(txt, 9, "bold"), line_height(9, "bold")
    px, py = T.s(10), T.s(6)
    w, h = tw + 2 * px, th + 2 * py
    x1 = clamp(x - w / 2, T.s(6), max(T.s(6), c.W - w - T.s(6)))
    y1 = max(T.s(6), y - h)
    rrect(c, x1, y1, x1 + w, y1 + h, T.s(9), fill=T.INK, outline="", tags=tag)
    c.create_text(x1 + px, y1 + py, text=txt, font=T.F(9, "bold"), fill="#FFFFFF", anchor="nw", tags=tag)


# ----------------------------------------------------------------- bar chart
class BarChartCard(Surface):
    def __init__(self, parent, motion, title):
        super().__init__(parent, motion)
        self.title, self.subtitle = title, ""
        self.springs, self.labels, self.tips, self.show, self.values = [], [], [], set(), []
        self.hover = None
        self._bars, self._geo = [], (0, 0, 0, 0)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    def set_data(self, values, labels, tips, subtitle, show):
        self.values, self.labels, self.tips, self.subtitle, self.show = list(values), labels, tips, subtitle, show
        n = len(values)
        if n != len(self.springs):
            self.springs = [Spring(self.motion, self, 0.0, response=0.4 + 0.015 * i, eps=0.002) for i in range(n)]
        mx = max(values + [1])
        for sp, v in zip(self.springs, values):
            sp.to(v / mx)
        self.redraw()

    def draw(self):
        pad = T.s(22)
        self.text(pad, T.s(18), self.title, 12, "bold")
        self.text(pad, T.s(40), self.subtitle, 9, fill=T.SUB)
        left, right = pad, self.W - pad
        top, bottom = T.s(78), self.H - T.s(34)
        h = bottom - top
        self._geo = (left, right, top, bottom)
        n = len(self.springs)
        if n == 0:
            return
        slot = (right - left) / n
        bw = min(slot * 0.58, T.s(26))
        mx_i = max(range(n), key=lambda i: self.values[i]) if any(self.values) else -1
        self._bars = []
        self.create_line(left, bottom, right, bottom, fill=T.LINE2, width=1)
        for i, sp in enumerate(self.springs):
            cx = left + slot * (i + 0.5)
            bh = max(T.s(5), clamp(sp.value, 0, 1.05) * h)
            top_y = bottom - bh
            self._bars.append((cx, top_y, bw))
            hot = i == mx_i
            rrect(self, cx - bw / 2, top_y, cx + bw / 2, bottom, min(bw / 2, T.s(7)),
                  fill=self.fade(T.ACCENT if hot else T.ACCENT_MID), outline="")
            if i in self.show and i < len(self.labels):
                self.text(cx, bottom + T.s(10), self.labels[i], 8, fill=T.FAINT, anchor="n", rise=False)
        self._draw_tip()

    def _move(self, e):
        left, right, top, bottom = self._geo
        if not self._bars or not (top - T.s(20) <= e.y <= bottom + T.s(24)):
            return self._set_hover(None)
        slot = (right - left) / len(self._bars)
        self._set_hover(int(clamp((e.x - left) // slot, 0, len(self._bars) - 1)))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self._draw_tip()

    def _draw_tip(self):
        self.delete("tip")
        i = self.hover
        if i is None or i >= len(self._bars) or i >= len(self.tips):
            return
        cx, top_y, bw = self._bars[i]
        bottom = self._geo[3]
        rrect(self, cx - bw / 2, top_y, cx + bw / 2, bottom, min(bw / 2, T.s(7)), fill=T.ACCENT_D, outline="", tags="tip")
        draw_tooltip(self, cx, top_y - T.s(8), self.tips[i])


# --------------------------------------------------------------------- donut
class DonutCard(Surface):
    def __init__(self, parent, motion, on_kind):
        super().__init__(parent, motion)
        self.slices, self.kind, self.total = [], "app", 0
        self.sweep = Spring(motion, self, 0.0, response=0.9)
        self.seg = Segmented(self, motion, [("app", "Apps"), ("site", "Websites")],
                             lambda k: on_kind(k), seg_w=T.s(76), h=T.s(28), bg=T.CARD)

    def set_items(self, items, kind, total, animate=False):
        changed = animate or kind != self.kind or not self.slices
        self.slices, self.kind, self.total = items, kind, total
        self.seg.select(kind, silent=True)
        if changed:
            self.sweep.jump(0)
            self.sweep.to(1)
        self.redraw()

    def draw(self):
        pad = T.s(22)
        self.text(pad, T.s(18), "Where your clicks go", 12, "bold")
        self.text(pad, T.s(40), "Share of clicks by " + ("application" if self.kind == "app" else "website"), 9, fill=T.SUB)
        self.create_window(self.W - pad, T.s(16), window=self.seg, anchor="ne")
        if not self.slices:
            self.text(self.W / 2, self.H / 2 + T.s(10), "No clicks yet", 10, fill=T.SUB, anchor="center")
            return
        area_top, area_bot = T.s(78), self.H - T.s(22)
        d = min(area_bot - area_top, self.W * 0.42)
        thick = max(T.s(16), int(d * 0.13))
        cx, cy = pad + d / 2 + T.s(6), (area_top + area_bot) / 2
        r = d / 2 - thick / 2
        box = (cx - r, cy - r, cx + r, cy + r)
        self.create_oval(*box, outline=T.TRACK, width=thick)
        total = sum(n for _, n in self.slices) or 1
        start, gap = 90.0, 2.5 if len(self.slices) > 1 else 0
        p = clamp(self.sweep.value, 0, 1)
        for i, (name, n) in enumerate(self.slices):
            ext = n / total * 360 * p
            col = T.OTHER if name == "Others" else T.PALETTE[i % len(T.PALETTE)]
            if ext - gap > 0.4:
                self.create_arc(*box, start=start - gap / 2, extent=-(ext - gap), style="arc", outline=col, width=thick)
            start -= ext
        self.text(cx, cy - T.s(10), f"{self.total:,}", 20, "bold", anchor="center", rise=False)
        self.text(cx, cy + T.s(14), "clicks", 9, fill=T.SUB, anchor="center", rise=False)
        lx = cx + d / 2 + T.s(40)
        pitch = T.s(36)
        y0 = cy - pitch * len(self.slices) / 2 + pitch / 2
        for i, (name, n) in enumerate(self.slices):
            y = y0 + i * pitch
            col = T.OTHER if name == "Others" else T.PALETTE[i % len(T.PALETTE)]
            rr = T.s(5)
            self.create_oval(lx, y - rr, lx + 2 * rr, y + rr, fill=self.fade(col), outline="")
            nm = name if len(name) <= 22 else name[:21] + "\u2026"
            self.text(lx + T.s(20), y, nm, 10, anchor="w", rise=False)
            self.text(self.W - pad, y, f"{n / total:.0%}", 10, "bold", anchor="e", rise=False)


# ---------------------------------------------------------------------- list
class ListCard(Surface):
    def __init__(self, parent, motion, title, on_mode):
        super().__init__(parent, motion)
        self.title, self.mode, self.on_mode = title, "most", on_mode
        self.rows, self.order, self.empty, self.capacity = {}, [], "", 6
        for m in ("most", "least"):
            self.tag_bind("m_" + m, "<ButtonPress-1>", lambda e, m=m: self.set_mode(m))
            self.tag_bind("m_" + m, "<Enter>", lambda e: self.config(cursor="hand2"))
            self.tag_bind("m_" + m, "<Leave>", lambda e: self.config(cursor=""))

    def set_mode(self, m):
        if m != self.mode:
            self.mode = m
            self.on_mode()
            self.redraw()

    def set_rows(self, rows, empty):
        self.empty = empty
        mx = max([n for _, n in rows] + [1])
        pitch = T.s(46)
        top = T.s(64)
        seen = set()
        for i, (name, n) in enumerate(rows):
            seen.add(name)
            ty = top + i * pitch
            st = self.rows.get(name)
            if st is None:
                st = self.rows[name] = dict(y=Spring(self.motion, self, ty, response=0.45, eps=0.3),
                                            f=Spring(self.motion, self, 0.0, response=0.55, eps=0.002),
                                            n=Spring(self.motion, self, 0.0, response=0.7, eps=0.4))
                st["y"].jump(ty)
            st["y"].to(ty)
            st["f"].to(n / mx)
            st["n"].to(n)
        for name in list(self.rows):
            if name not in seen:
                del self.rows[name]
        self.order = [name for name, _ in rows]
        self.redraw()

    def draw(self):
        pad = T.s(22)
        self.text(pad, T.s(18), self.title, 12, "bold")
        x = self.W - pad
        for m, label in (("least", "Least"), ("most", "Most")):
            on = m == self.mode
            tw = measure(label, 9, "bold")
            rrect(self, x - tw - T.s(8), T.s(16), x + T.s(8), T.s(38), T.s(11),
                  fill=T.ACCENT_SOFT if on else T.CARD, outline="", tags="m_" + m)
            self.create_text(x - tw / 2, T.s(27), text=label, font=T.F(9, "bold" if on else "normal"),
                             fill=T.ACCENT_D if on else T.SUB, anchor="center", tags="m_" + m)
            x -= tw + T.s(22)
        if not self.order:
            self.text(pad, T.s(70), self.empty, 10, fill=T.SUB, width=self.W - 2 * pad)
            return
        bar_h = T.s(6)
        for name in sorted(self.order, key=lambda k: self.rows[k]["y"].value):
            st = self.rows[name]
            y = st["y"].value
            if y + T.s(36) > self.H:
                continue
            nm = name if len(name) <= 30 else name[:29] + "\u2026"
            self.text(pad, y, nm, 10, anchor="nw")
            self.text(self.W - pad, y, f"{int(round(st['n'].value)):,}", 10, "bold", anchor="ne")
            by = y + T.s(24)
            rrect(self, pad, by, self.W - pad, by + bar_h, bar_h / 2, fill=T.TRACK, outline="")
            w = max(bar_h, (self.W - 2 * pad) * clamp(st["f"].value, 0, 1))
            rrect(self, pad, by, pad + w, by + bar_h, bar_h / 2, fill=self.fade(T.ACCENT), outline="")


# ----------------------------------------------------------------- controls
class Segmented(tk.Canvas):
    """iOS-style segmented control with a sliding selection pill."""

    def __init__(self, parent, motion, items, on_change, seg_w=None, h=None, bg=T.BG):
        self.opts, self.on_change = items, on_change
        self.sw, self.h = seg_w or T.s(80), h or T.s(32)
        super().__init__(parent, width=self.sw * len(items) + 4, height=self.h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.motion, self.sel, self.bg = motion, 0, bg
        self.pos = Spring(motion, self, 0.0, response=0.3)
        self.bind("<ButtonPress-1>", self._press)
        self.redraw()

    def select(self, key, silent=False):
        idx = [k for k, _ in self.opts].index(key)
        self.sel = idx
        self.pos.to(idx)
        if not silent:
            self.on_change(key)

    def _press(self, e):  # respond on pointer-down, not on release
        idx = int(clamp((e.x - 2) // self.sw, 0, len(self.opts) - 1))
        if idx != self.sel:
            self.select(self.opts[idx][0])

    def redraw(self):
        self.delete("all")
        w, h = self.sw * len(self.opts) + 4, self.h
        rrect(self, 0, 0, w, h, T.s(10), fill="#E6E8ED", outline="")
        x = 2 + self.pos.value * self.sw
        rrect(self, x, 3, x + self.sw, h, T.s(8), fill="#D9DCE2", outline="")
        rrect(self, x, 2, x + self.sw, h - 2, T.s(8), fill="#FFFFFF", outline="#E3E5EA")
        for i, (_, label) in enumerate(self.opts):
            t = 1 - min(1.0, abs(self.pos.value - i))
            self.create_text(2 + self.sw * (i + 0.5), h / 2, text=label,
                             font=T.F(9, "bold"), fill=mix(T.SUB, T.TEXT, t), anchor="center")


class PillButton(tk.Canvas):
    STYLES = {"dark": (T.INK, "#3C3C41", "#FFFFFF"), "soft": ("#E9EBF0", "#DCDFE6", T.TEXT),
              "danger": ("#FFE8E6", "#FFD6D2", "#C9251A"), "accent": (T.ACCENT, "#00AFCB", "#06303A")}

    def __init__(self, parent, motion, text, command, style="dark", bg=T.CARD, width=None, h=None):
        self.text, self.command, self.style, self.motion = text, command, style, motion
        self.bgc = bg
        self.w = width or (measure(text, 10, "bold") + T.s(36))
        self.h = h or T.s(36)
        super().__init__(parent, width=self.w, height=self.h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.hv = Spring(motion, self, 0.0, response=0.2)
        self.pr = Spring(motion, self, 0.0, response=0.14)
        self.bind("<Enter>", lambda e: self.hv.to(1))
        self.bind("<Leave>", lambda e: (self.hv.to(0), self.pr.to(0)))
        self.bind("<ButtonPress-1>", lambda e: self.pr.to(1))   # instant press feedback
        self.bind("<ButtonRelease-1>", self._release)
        self.redraw()

    def _release(self, e):
        self.pr.to(0)
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.command()

    def restyle(self, text, style):
        self.text, self.style = text, style
        self.redraw()

    def redraw(self):
        self.delete("all")
        base, hov, fg = self.STYLES[self.style]
        col = mix(base, hov, max(self.hv.value, self.pr.value))
        inset = self.pr.value * T.s(1.5)
        rrect(self, inset, inset, self.w - inset, self.h - inset, self.h / 2, fill=col, outline="")
        self.create_text(self.w / 2, self.h / 2, text=self.text, font=T.F(10, "bold"), fill=fg, anchor="center")


# ------------------------------------------------------------------- sidebar
class Sidebar(tk.Canvas):
    ITEMS = [("overview", "Overview"), ("graphs", "Graphs"), ("suggestions", "Suggestions"), ("settings", "Settings")]

    def __init__(self, parent, motion, on_select, on_pause, logo=None, demo=False):
        super().__init__(parent, bg=T.SIDEBAR, highlightthickness=0, bd=0)
        self.motion, self.on_select, self.logo, self.demo = motion, on_select, logo, demo
        self.active, self.hover, self.paused, self.W, self.H = 0, -1, False, 0, 0
        self.pill = Spring(motion, self, 0.0, response=0.32)
        self.ripple = Spring(motion, self, 1.0, response=0.7, eps=0.004)
        self.btn = PillButton(self, motion, "Pause", on_pause, style="dark", bg=T.SIDEBAR, width=T.s(150), h=T.s(34))
        self.bind("<Configure>", self._conf)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._hover(-1))
        self.bind("<ButtonPress-1>", self._press)

    # layout constants
    def _top(self):
        return T.s(124)

    def _pitch(self):
        return T.s(46)

    def _conf(self, e):
        self.W, self.H = e.width, e.height
        self.redraw()

    def _index_at(self, x, y):
        i = (y - self._top()) // self._pitch()
        return int(i) if 0 <= i < len(self.ITEMS) and T.s(10) <= x <= self.W - T.s(10) else -1

    def _hover(self, i):
        if i != self.hover:
            self.hover = i
            self.config(cursor="hand2" if i >= 0 else "")
            self.redraw()

    def _move(self, e):
        self._hover(self._index_at(e.x, e.y))

    def _press(self, e):
        i = self._index_at(e.x, e.y)
        if i >= 0:
            self.select(self.ITEMS[i][0])

    def select(self, key, notify=True):
        i = [k for k, _ in self.ITEMS].index(key)
        self.active = i
        self.pill.to(i)
        if notify:
            self.on_select(key)

    def pulse(self):
        self.ripple.jump(0)
        self.ripple.to(1)

    def set_paused(self, paused):
        self.paused = paused
        self.btn.restyle("Resume" if paused else "Pause", "accent" if paused else "dark")
        self.redraw()

    def redraw(self):
        if self.W < 10:
            return
        self.delete("all")
        W, H = self.W, self.H
        if self.logo is not None:
            self.create_image(T.s(22), T.s(24), image=self.logo, anchor="nw")
        self.create_text(T.s(22) + (self.logo.width() if self.logo else 0) + T.s(12), T.s(49), text="ClickScope",
                         font=T.F(14, "bold"), fill=T.TEXT, anchor="w")
        if self.demo:
            rrect(self, T.s(22), T.s(84), T.s(22) + T.s(84), T.s(84) + T.s(20), T.s(10), fill="#FFF1D6", outline="")
            self.create_text(T.s(22) + T.s(42), T.s(94), text="Demo data", font=T.F(8, "bold"), fill="#9A5B00", anchor="center")
        top, pitch = self._top(), self._pitch()
        py = top + self.pill.value * pitch
        if 0 <= self.hover != round(self.pill.value):
            hy = top + self.hover * pitch
            rrect(self, T.s(12), hy, W - T.s(12), hy + T.s(40), T.s(12), fill="#E4E7EC", outline="")
        rrect(self, T.s(12), py + 2, W - T.s(12), py + T.s(40) + 2, T.s(12), fill="#E1E4EA", outline="")
        rrect(self, T.s(12), py, W - T.s(12), py + T.s(40), T.s(12), fill="#FFFFFF", outline="#E3E6EB")
        for i, (key, label) in enumerate(self.ITEMS):
            t = 1 - min(1.0, abs(self.pill.value - i))
            col = mix(T.SUB, T.ACCENT_D, t)
            cy = top + i * pitch + T.s(20)
            draw_icon(self, key, T.s(36), cy, col, T.s(16), hole=mix(T.SIDEBAR, "#FFFFFF", t))
            self.create_text(T.s(56), cy, text=label, font=T.F(10, "bold" if t > 0.5 else "normal"),
                             fill=mix(T.SUB, T.TEXT, t), anchor="w")
        # status
        sy = H - T.s(92)
        dot = T.AMBER if self.paused else T.GREEN
        dx, r = T.s(28), T.s(5)
        rp = self.ripple.value
        if rp < 0.99 and not self.paused:
            rr = r + rp * T.s(9)
            self.create_oval(dx - rr, sy - rr, dx + rr, sy + rr, outline=mix(dot, T.SIDEBAR, rp), width=T.s(2))
        self.create_oval(dx - r, sy - r, dx + r, sy + r, fill=dot, outline="")
        self.create_text(T.s(44), sy, text="Paused" if self.paused else "Tracking clicks",
                         font=T.F(9, "bold"), fill=T.SUB, anchor="w")
        self.create_window(T.s(22), H - T.s(66), window=self.btn, anchor="nw")
