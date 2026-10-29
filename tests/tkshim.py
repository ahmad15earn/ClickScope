"""A tiny headless stand-in for tkinter (Frame, Canvas, place, after, events) that renders
widget trees to a PNG with Pillow. Lets us run and *look at* the real UI code on Linux.
Approximate (no true Tk metrics), but layout, colours and logic are the real thing."""
import math
import sys
import types

from PIL import Image, ImageDraw, ImageFont

K = 2  # supersampling
FONT_R = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_fcache = {}


def pil_font(spec):
    fam, size, weight = (list(spec) + ["normal"])[:3] if isinstance(spec, (tuple, list)) else ("x", 10, "normal")
    px = max(6, int(round(abs(size) * 96 / 72 * K)))
    key = (px, weight == "bold")
    if key not in _fcache:
        _fcache[key] = ImageFont.truetype(FONT_B if weight == "bold" else FONT_R, px)
    return _fcache[key]


def hexcol(c):
    if not c:
        return None
    if isinstance(c, str) and c.startswith("#") and len(c) == 7:
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    return {"white": (255, 255, 255, 255), "black": (0, 0, 0, 255)}.get(c, (255, 0, 255, 255))


class Event:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Widget:
    def __init__(self, parent=None, **kw):
        self.parent = parent
        self.children, self.cfg, self.binds = [], dict(kw), {}
        self.x = self.y = 0
        self.w, self.h = int(kw.get("width", 1) or 1), int(kw.get("height", 1) or 1)
        self.mapped = False
        self.master = parent
        if parent is not None:
            parent.children.append(self)

    @property
    def root(self):
        w = self
        while w.parent is not None:
            w = w.parent
        return w

    def configure(self, **kw):
        self.cfg.update(kw)
        if "width" in kw and isinstance(self, Canvas) is False:
            pass
        if "width" in kw:
            self.w = int(kw["width"])
        if "height" in kw:
            self.h = int(kw["height"])

    config = configure

    def cget(self, k):
        return self.cfg.get(k)

    def bind(self, seq, fn=None, add=None):
        self.binds.setdefault(seq, []).append(fn)

    def fire(self, seq, **kw):
        for fn in self.binds.get(seq, []):
            fn(Event(widget=self, **kw))

    def place(self, x=0, y=0, width=None, height=None, **_):
        old = (self.w, self.h)
        self.x, self.y = int(x), int(y)
        if width is not None:
            self.w = int(width)
        if height is not None:
            self.h = int(height)
        first = not self.mapped
        self.mapped = True
        if first or old != (self.w, self.h):
            self.fire("<Configure>", width=self.w, height=self.h, x=self.x, y=self.y)

    def place_forget(self):
        self.mapped = False

    def winfo_ismapped(self):
        return self.mapped

    def winfo_width(self):
        return self.w

    def winfo_height(self):
        return self.h

    def winfo_reqwidth(self):
        return self.w

    def winfo_children(self):
        return list(self.children)

    def destroy(self):
        if self.parent and self in self.parent.children:
            self.parent.children.remove(self)
        self.mapped = False
        if isinstance(self.parent, Canvas):
            pass

    def after(self, ms, fn=None):
        return self.root.after(ms, fn)

    def after_idle(self, fn):
        return self.root.after_idle(fn)


def _noop(self, *a, **k):
    return None


for _n in ("focus_set", "tkraise", "lift", "pack", "grid", "attributes", "overrideredirect", "geometry", "update_idletasks"):
    setattr(Widget, _n, _noop)
Widget.winfo_pointerxy = lambda self: (400, 300)


class Toplevel(Widget):
    pass


class Frame(Widget):
    pass


class Tk(Widget):
    def __init__(self):
        super().__init__(None)
        self.queue, self.now, self.seq = [], 0.0, 0
        self.w, self.h = 1120, 740
        self.mapped = True

    def title(self, *a): pass
    def minsize(self, *a): pass
    def iconbitmap(self, *a): pass
    def protocol(self, *a): pass
    def mainloop(self): pass
    def iconify(self): pass
    def withdraw(self): pass
    def destroy(self): pass
    def winfo_fpixels(self, s): return 96.0

    def geometry(self, g):
        wh = g.split("+")[0].split("x")
        self.w, self.h = int(wh[0]), int(wh[1])

    def after(self, ms, fn=None):
        self.seq += 1
        self.queue.append((self.now + ms / 1000.0, self.seq, fn))
        return self.seq

    def after_idle(self, fn):
        return self.after(0, fn)

    def pump(self, seconds):
        """Run scheduled callbacks for `seconds` of virtual time."""
        end = self.now + seconds
        while True:
            due = [q for q in self.queue if q[0] <= end]
            if not due:
                break
            q = min(due)
            self.queue.remove(q)
            self.now = max(self.now, q[0])
            q[2]()
        self.now = end


class PhotoImage:
    def __init__(self, file=None, **_):
        self.img = Image.open(file).convert("RGBA")

    def width(self): return self.img.width
    def height(self): return self.img.height


class Canvas(Widget):
    def __init__(self, parent=None, **kw):
        super().__init__(parent, **kw)
        self.items, self.nid, self.tagbinds = [], 0, {}

    # --- item creation
    def _add(self, typ, coords, opts):
        self.nid += 1
        tags = opts.get("tags", ())
        tags = (tags,) if isinstance(tags, str) else tuple(tags)
        self.items.append(dict(id=self.nid, type=typ, coords=list(coords), opts=opts, tags=tags))
        return self.nid

    @staticmethod
    def _flat(args):
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            return list(args[0])
        return list(args)

    def create_rectangle(self, *a, **kw): return self._add("rect", self._flat(a), kw)
    def create_oval(self, *a, **kw): return self._add("oval", self._flat(a), kw)
    def create_polygon(self, *a, **kw): return self._add("poly", self._flat(a), kw)
    def create_line(self, *a, **kw): return self._add("line", self._flat(a), kw)
    def create_arc(self, *a, **kw): return self._add("arc", self._flat(a), kw)
    def create_text(self, x, y, **kw): return self._add("text", [x, y], kw)
    def create_image(self, x, y, **kw): return self._add("image", [x, y], kw)
    def create_window(self, x, y, **kw): return self._add("window", [x, y], kw)

    def delete(self, what):
        if what == "all":
            self.items = []
        else:
            self.items = [i for i in self.items if i["id"] != what and what not in i["tags"]]

    def coords(self, item, *c):
        for i in self.items:
            if i["id"] == item:
                i["coords"] = list(c)

    def tag_bind(self, tag, seq, fn):
        self.tagbinds.setdefault((tag, seq), []).append(fn)

    def click_tag(self, tag, seq="<ButtonPress-1>"):
        for fn in self.tagbinds.get((tag, seq), []):
            fn(Event(widget=self, x=0, y=0))

    def bbox(self, item):
        for i in self.items:
            if i["id"] == item and i["type"] == "text":
                lines = self._wrap(i)
                f = pil_font(i["opts"].get("font", ("x", 10)))
                w = max(f.getlength(l) for l in lines) / K
                return (i["coords"][0], i["coords"][1], i["coords"][0] + w, i["coords"][1] + len(lines) * f.size * 1.2 / K)

    # --- text layout
    def _wrap(self, it):
        text = it["opts"].get("text", "")
        width = it["opts"].get("width")
        f = pil_font(it["opts"].get("font", ("x", 10)))
        out = []
        for para in str(text).split("\n"):
            if not width:
                out.append(para)
                continue
            line = ""
            for word in para.split(" "):
                trial = (line + " " + word).strip()
                if f.getlength(trial) > width * K and line:
                    out.append(line)
                    line = word
                else:
                    line = trial
            out.append(line)
        return out

    # --- rendering
    def render(self):
        img = Image.new("RGBA", (self.w * K, self.h * K), hexcol(self.cfg.get("bg", "#FFFFFF")))
        d = ImageDraw.Draw(img)
        for it in self.items:
            self._draw_item(img, d, it)
        return img

    def _draw_item(self, img, d, it):
        t, c, o = it["type"], [v * K for v in it["coords"]], it["opts"]
        fill, outline = hexcol(o.get("fill")), hexcol(o.get("outline"))
        w = max(1, int(round(float(o.get("width", 1)) * K))) if o.get("width") is not None else K
        if t == "rect":
            d.rectangle(c, fill=fill, outline=outline, width=w)
        elif t == "oval":
            x1, y1, x2, y2 = c
            if fill and outline:
                d.ellipse([x1 - w / 2, y1 - w / 2, x2 + w / 2, y2 + w / 2], fill=outline)
                d.ellipse([x1 + w / 2, y1 + w / 2, x2 - w / 2, y2 - w / 2], fill=fill)
            elif fill:
                d.ellipse(c, fill=fill)
            elif outline:
                d.ellipse([x1 - w / 2, y1 - w / 2, x2 + w / 2, y2 + w / 2], outline=outline, width=w)
        elif t == "poly":
            pts = list(zip(c[0::2], c[1::2]))
            if o.get("smooth"):
                pts = self._smooth(pts)
            if len(pts) >= 3:
                d.polygon(pts, fill=fill, outline=outline, width=w if outline else 1)
        elif t == "line":
            pts = list(zip(c[0::2], c[1::2]))
            col = fill or (0, 0, 0, 255)
            dash = o.get("dash")
            if dash:
                self._dashed(d, pts, col, w, dash)
            else:
                d.line(pts, fill=col, width=w, joint="curve")
                if w >= 3 * K / 2 and o.get("capstyle") == "round":
                    for px, py in (pts[0], pts[-1]):
                        d.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=col)
        elif t == "arc":
            x1, y1, x2, y2 = c
            st, ex = float(o.get("start", 0)), float(o.get("extent", 90))
            lo, hi = min(st, st + ex), max(st, st + ex)
            col = outline or fill
            d.arc([x1 - w / 2, y1 - w / 2, x2 + w / 2, y2 + w / 2], -hi, -lo, fill=col, width=w)
        elif t == "text":
            lines = self._wrap(it)
            f = pil_font(o.get("font", ("x", 10)))
            lh = f.size * 1.2
            x, y = c[0], c[1]
            anchor = o.get("anchor", "center")
            total_h = lh * len(lines)
            maxw = max(f.getlength(l) for l in lines)
            if "n" in anchor and anchor != "center":
                y0 = y
            elif "s" in anchor:
                y0 = y - total_h
            else:
                y0 = y - total_h / 2
            for i, l in enumerate(lines):
                lw = f.getlength(l)
                if "e" in anchor and anchor != "center":
                    x0 = x - lw
                elif "w" in anchor:
                    x0 = x
                elif anchor in ("n", "s", "center"):
                    x0 = x - lw / 2
                else:
                    x0 = x
                d.text((x0, y0 + i * lh), l, font=f, fill=fill or (0, 0, 0, 255))
        elif t == "image":
            im = o["image"].img
            big = im.resize((im.width * K, im.height * K), Image.LANCZOS)
            img.alpha_composite(big, (int(c[0]), int(c[1])))
        elif t == "window":
            ch = o["window"]
            sub = ch.render()
            ax, ay = c[0], c[1]
            anchor = o.get("anchor", "center")
            if "e" in anchor and anchor != "center":
                ax -= sub.width
            if "s" in anchor:
                ay -= sub.height
            if anchor in ("n", "s", "center"):
                ax -= sub.width / 2
            if anchor == "center":
                ay -= sub.height / 2
            ch.x, ch.y = ax / K, ay / K
            img.alpha_composite(sub, (int(ax), int(ay)))

    @staticmethod
    def _smooth(pts):
        n = len(pts)
        mids = [((pts[i][0] + pts[(i + 1) % n][0]) / 2, (pts[i][1] + pts[(i + 1) % n][1]) / 2) for i in range(n)]
        out = []
        for i in range(n):
            a, b, cpt = mids[i - 1], pts[i], mids[i]
            for k in range(9):
                u = k / 8
                out.append(((1 - u) ** 2 * a[0] + 2 * u * (1 - u) * b[0] + u * u * cpt[0],
                            (1 - u) ** 2 * a[1] + 2 * u * (1 - u) * b[1] + u * u * cpt[1]))
        return out

    @staticmethod
    def _dashed(d, pts, col, w, dash):
        on, off = dash[0] * K, dash[1] * K
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            pos = 0.0
            while pos < L:
                e = min(L, pos + on)
                d.line([(x1 + (x2 - x1) * pos / L, y1 + (y2 - y1) * pos / L),
                        (x1 + (x2 - x1) * e / L, y1 + (y2 - y1) * e / L)], fill=col, width=w)
                pos += on + off


def render_tree(widget):
    """Render a Frame/Tk tree (placed children) to a PIL image at 1x."""
    img = Image.new("RGBA", (widget.w * K, widget.h * K), hexcol(widget.cfg.get("bg", "#F5F5F7")))
    for ch in widget.children:
        if not ch.mapped:
            continue
        sub = render_tree(ch) if isinstance(ch, (Frame, Tk)) else ch.render()
        img.paste(sub, (int(ch.x * K), int(ch.y * K)), sub)
    return img


class FontObj:
    def __init__(self, family=None, size=10, weight="normal", **_):
        self.spec = (family, size, weight)

    def measure(self, text):
        return int(pil_font(self.spec).getlength(str(text)) / K)

    def metrics(self, what=None):
        return int(pil_font(self.spec).size * 1.2 / K)


def install():
    tk = types.ModuleType("tkinter")
    tk.Tk, tk.Frame, tk.Canvas, tk.PhotoImage, tk.Toplevel = Tk, Frame, Canvas, PhotoImage, Toplevel
    tk.TclError = Exception
    font = types.ModuleType("tkinter.font")
    font.Font = FontObj
    font.families = lambda root=None: ["Segoe UI"]
    fd, mb = types.ModuleType("tkinter.filedialog"), types.ModuleType("tkinter.messagebox")
    fd.asksaveasfilename = lambda **k: ""
    fd.askopenfilename = lambda **k: ""
    sd = types.ModuleType("tkinter.simpledialog")
    sd.askstring = lambda *a, **k: None
    tk.simpledialog = sd
    sys.modules["tkinter.simpledialog"] = sd
    for n in ("showinfo", "showerror"):
        setattr(mb, n, lambda *a, **k: None)
    mb.askyesno = lambda *a, **k: False
    tk.font, tk.filedialog, tk.messagebox = font, fd, mb
    sys.modules.update({"tkinter": tk, "tkinter.font": font, "tkinter.filedialog": fd, "tkinter.messagebox": mb})
