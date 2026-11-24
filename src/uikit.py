"""Custom-drawn interface pieces for the new ClickScope.

Everything is a Tk canvas so the app keeps its soft, rounded, high-DPI look
without external UI dependencies. Motion follows the Apple-style springs in
motion.py: immediate press feedback, interruptible values, reduced-motion aware.
"""
import math
import os
import tkinter as tk
from tkinter import font as tkfont

import appdata as A
import theme as T
from motion import Spring, clamp, mix

_fonts = {}
_photo_cache = {}


def photo(path, width, height, radius=0):
    """A cover-cropped, optionally rounded preview. One cached PhotoImage per size.

    Pillow makes the soft corners when it is available; without it the preview
    is still shown, just square, through Tk's own PNG loader.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        stamp = 0
    key = (os.path.abspath(path), width, height, radius, stamp)
    if key in _photo_cache:
        return _photo_cache[key]
    try:
        from PIL import Image, ImageDraw, ImageOps, ImageTk
        img = Image.open(path).convert("RGB")
        img = ImageOps.fit(img, (max(1, width), max(1, height)), method=Image.LANCZOS)
        if radius > 0:
            mask = Image.new("L", (max(1, width), max(1, height)), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
            img.putalpha(mask)
        ph = ImageTk.PhotoImage(img)
    except Exception:
        try:
            raw = tk.PhotoImage(file=path)
            factor = max(1, round(max(raw.width() / max(1, width), raw.height() / max(1, height))))
            ph = raw.subsample(factor) if factor > 1 else raw
        except Exception:
            return None
    _photo_cache[key] = ph
    return ph


def measure(text, size, weight="normal"):
    key = (T.FAMILY, size, weight)
    if key not in _fonts:
        _fonts[key] = tkfont.Font(family=T.FAMILY, size=size, weight=weight)
    return _fonts[key].measure(str(text))


def line_height(size, weight="normal"):
    key = (T.FAMILY, size, weight)
    if key not in _fonts:
        _fonts[key] = tkfont.Font(family=T.FAMILY, size=size, weight=weight)
    return _fonts[key].metrics("linespace")


def ellipsize(text, size, weight, width):
    """Trim text until it fits, with a real ellipsis (measured, not guessed)."""
    text = str(text)
    if width <= 0:
        return ""
    if measure(text, size, weight) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid] + "\u2026", size, weight) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "\u2026"


def middle_ellipsize(text, size, weight, width):
    text = str(text)
    if measure(text, size, weight) <= width or width <= 0:
        return text
    if measure("\u2026", size, weight) > width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        left = (mid + 1) // 2
        right = mid - left
        trial = text[:left] + "\u2026" + (text[-right:] if right else "")
        if measure(trial, size, weight) <= width:
            lo = mid
        else:
            hi = mid - 1
    left = (lo + 1) // 2
    right = lo - left
    return text[:left] + "\u2026" + (text[-right:] if right else "")


def rr(c, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    kw.setdefault("fill", "")
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def circle(c, cx, cy, r, **kw):
    return c.create_oval(cx - r, cy - r, cx + r, cy + r, **kw)


def tint_fill(kind):
    return {"doc": (T.DOC_FILL, T.DOC_INK), "pdf": (T.PDF_FILL, T.PDF_INK),
            "image": (T.IMAGE_FILL, T.IMAGE_INK),
            "video": (T.VIDEO_FILL, T.VIDEO_INK), "audio": (T.AUDIO_FILL, T.AUDIO_INK),
            "archive": (T.ARCHIVE_FILL, T.ARCHIVE_INK), "app": (T.APP_FILL, T.APP_INK),
            "code": (T.CODE_FILL, T.CODE_INK), "folder": (T.FOLDER_FILL, T.FOLDER_INK),
            "other": (T.OTHER_FILL, T.OTHER_INK)}.get(kind, (T.OTHER_FILL, T.OTHER_INK))


def file_color_kind(name, kind="other", is_dir=False):
    """Files get a colour by type; folders and EXE/MSI tiles keep their own look."""
    if is_dir or kind == "folder":
        return "folder"
    if kind == "app":
        return "app"
    ext = os.path.splitext(name or "")[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab", ".tgz", ".zst"):
        return "archive"
    return kind or "other"


# ---------------------------------------------------------------------- icons
def draw_glyph(c, kind, cx, cy, col, sz, width=None):
    """Small line icons, centred, drawn to match at any scale."""
    w = width or max(1.2, T.s(1.7))
    h = sz / 2.0
    if kind == "search":
        r = h * 0.62
        c.create_oval(cx - h * 0.9, cy - h * 0.9, cx - h * 0.9 + 2 * r, cy - h * 0.9 + 2 * r,
                     outline=col, width=w)
        c.create_line(cx + h * 0.04, cy + h * 0.04, cx + h * 0.82, cy + h * 0.82, fill=col, width=w,
                      capstyle="round")
    elif kind == "installers":  # open archive box
        c.create_line(cx - h * 0.8, cy - h * 0.35, cx + h * 0.8, cy - h * 0.35, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.8, cy - h * 0.35, cx - h * 0.8, cy + h * 0.5, cx - h * 0.35, cy + h * 0.8,
                      fill=col, width=w, capstyle="round", joinstyle="round")
        c.create_line(cx + h * 0.8, cy - h * 0.35, cx + h * 0.8, cy + h * 0.5, cx + h * 0.35, cy + h * 0.8,
                      fill=col, width=w, capstyle="round", joinstyle="round")
        c.create_line(cx - h * 0.35, cy + h * 0.8, cx + h * 0.35, cy + h * 0.8, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.45, cy - h * 0.75, cx + h * 0.45, cy - h * 0.75, fill=col, width=w,
                      capstyle="round")
    elif kind == "blueprint":  # stacked layers
        for i, yy in enumerate((-0.5, 0.0, 0.5)):
            a = cy + h * yy
            c.create_line(cx - h * 0.8, a, cx, a - h * 0.33, cx + h * 0.8, a, cx, a + h * 0.33,
                          cx - h * 0.8, a, fill=col, width=w, joinstyle="round", capstyle="round")
    elif kind == "settings":
        for yy, kx in ((cy - h * 0.48, cx - h * 0.28), (cy + h * 0.48, cx + h * 0.34)):
            c.create_line(cx - h, yy, cx + h, yy, fill=col, width=w, capstyle="round")
            r = h * 0.22
            c.create_oval(kx - r, yy - r, kx + r, yy + r, fill=col, outline=col, width=0)
    elif kind == "folder":
        c.create_line(cx - h * 0.8, cy + h * 0.6, cx - h * 0.8, cy - h * 0.45, cx - h * 0.2, cy - h * 0.45,
                      cx - h * 0.02, cy - h * 0.2, cx + h * 0.5, cy - h * 0.2, fill=col, width=w,
                      joinstyle="round", capstyle="round")
        c.create_line(cx - h * 0.8, cy + h * 0.6, cx + h * 0.8, cy + h * 0.6, cx + h * 0.8, cy + h * 0.05,
                      cx - h * 0.8, cy + h * 0.05, fill=col, width=w, joinstyle="round")
    elif kind == "chevron":
        c.create_line(cx - h * 0.25, cy - h * 0.5, cx + h * 0.3, cy, cx - h * 0.25, cy + h * 0.5,
                      fill=col, width=w, capstyle="round", joinstyle="round")
    elif kind == "refresh":
        c.create_arc(cx - h * 0.75, cy - h * 0.75, cx + h * 0.75, cy + h * 0.75, start=45, extent=285,
                     style="arc", outline=col, width=w)
        c.create_line(cx + h * 0.2, cy - h * 0.95, cx + h * 0.75, cy - h * 0.72, cx + h * 0.35,
                      cy - h * 0.25, fill=col, width=w, capstyle="round", joinstyle="round")
    elif kind == "plus":
        c.create_line(cx - h * 0.55, cy, cx + h * 0.55, cy, fill=col, width=w, capstyle="round")
        c.create_line(cx, cy - h * 0.55, cx, cy + h * 0.55, fill=col, width=w, capstyle="round")
    elif kind == "check":
        c.create_line(cx - h * 0.55, cy, cx - h * 0.1, cy + h * 0.45, cx + h * 0.6, cy - h * 0.45,
                      fill=col, width=w, capstyle="round", joinstyle="round")
    elif kind == "close":
        c.create_line(cx - h * 0.45, cy - h * 0.45, cx + h * 0.45, cy + h * 0.45, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.45, cy + h * 0.45, cx + h * 0.45, cy - h * 0.45, fill=col, width=w,
                      capstyle="round")
    elif kind == "trash":
        c.create_line(cx - h * 0.7, cy - h * 0.4, cx + h * 0.7, cy - h * 0.4, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.4, cy - h * 0.4, cx - h * 0.4, cy - h * 0.65, cx + h * 0.4, cy - h * 0.65,
                      cx + h * 0.4, cy - h * 0.4, fill=col, width=w, capstyle="round", joinstyle="round")
        c.create_line(cx - h * 0.5, cy - h * 0.25, cx - h * 0.38, cy + h * 0.72, cx + h * 0.38, cy + h * 0.72,
                      cx + h * 0.5, cy - h * 0.25, fill=col, width=w, capstyle="round", joinstyle="round")
    elif kind == "external":
        c.create_line(cx - h * 0.55, cy + h * 0.55, cx + h * 0.55, cy - h * 0.55, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx + h * 0.1, cy - h * 0.55, cx + h * 0.55, cy - h * 0.55, cx + h * 0.55,
                      cy - h * 0.1, fill=col, width=w, capstyle="round", joinstyle="round")
    elif kind == "copy":
        rr(c, cx - h * 0.65, cy - h * 0.7, cx + h * 0.35, cy + h * 0.35, T.s(3), outline=col, width=w)
        rr(c, cx - h * 0.25, cy - h * 0.35, cx + h * 0.7, cy + h * 0.72, T.s(3), outline=col, width=w)
    elif kind == "info":
        circle(c, cx, cy, h * 0.8, outline=col, width=w)
        circle(c, cx, cy - h * 0.32, max(1, w * 0.7), fill=col, outline="")
        c.create_line(cx, cy - h * 0.02, cx, cy + h * 0.38, fill=col, width=w, capstyle="round")
    elif kind == "warning":
        c.create_polygon(cx, cy - h * 0.8, cx + h * 0.82, cy + h * 0.65, cx - h * 0.82, cy + h * 0.65,
                         fill="", outline=col, width=w)
        c.create_line(cx, cy - h * 0.28, cx, cy + h * 0.18, fill=col, width=w, capstyle="round")
        circle(c, cx, cy + h * 0.43, max(1, w * 0.7), fill=col, outline="")
    elif kind == "spark":
        pts = []
        for i in range(8):
            a = math.radians(i * 45 - 90)
            rad = h * (0.9 if i % 2 == 0 else 0.28)
            pts += [cx + rad * math.cos(a), cy + rad * math.sin(a)]
        c.create_polygon(pts, fill=col, outline="")
    elif kind == "wallpaper":  # framed picture
        rr(c, cx - h * 0.75, cy - h * 0.6, cx + h * 0.75, cy + h * 0.6, T.s(3), outline=col, width=w)
        circle(c, cx - h * 0.3, cy - h * 0.22, h * 0.12, fill=col, outline="")
        c.create_line(cx - h * 0.6, cy + h * 0.45, cx - h * 0.1, cy - h * 0.05, cx + h * 0.2, cy + h * 0.25,
                      cx + h * 0.58, cy - h * 0.18, fill=col, width=w, joinstyle="round")
    elif kind == "drive":
        rr(c, cx - h * 0.8, cy - h * 0.5, cx + h * 0.8, cy + h * 0.5, T.s(4), outline=col, width=w)
        circle(c, cx + h * 0.45, cy + h * 0.24, max(1, w * 0.7), fill=col, outline="")
        c.create_line(cx - h * 0.55, cy + h * 0.24, cx + h * 0.05, cy + h * 0.24, fill=col, width=w,
                      capstyle="round")
    elif kind == "protection":  # shield
        c.create_line(cx - h * 0.7, cy - h * 0.55, cx, cy - h * 0.85, cx + h * 0.7, cy - h * 0.55,
                      fill=col, width=w, joinstyle="round", capstyle="round")
        c.create_line(cx - h * 0.7, cy - h * 0.55, cx - h * 0.62, cy + h * 0.12, cx, cy + h * 0.8,
                      cx + h * 0.62, cy + h * 0.12, cx + h * 0.7, cy - h * 0.55, fill=col, width=w,
                      joinstyle="round", capstyle="round")
        c.create_line(cx - h * 0.28, cy + h * 0.05, cx - h * 0.05, cy + h * 0.3, cx + h * 0.34,
                      cy - h * 0.22, fill=col, width=w, joinstyle="round", capstyle="round")
    elif kind == "globe":
        circle(c, cx, cy, h * 0.8, outline=col, width=w)
        c.create_oval(cx - h * 0.36, cy - h * 0.8, cx + h * 0.36, cy + h * 0.8, outline=col, width=w)
        c.create_line(cx - h * 0.8, cy, cx + h * 0.8, cy, fill=col, width=w, capstyle="round")
        c.create_line(cx - h * 0.68, cy - h * 0.4, cx + h * 0.68, cy - h * 0.4, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.68, cy + h * 0.4, cx + h * 0.68, cy + h * 0.4, fill=col, width=w,
                      capstyle="round")
    else:  # page
        rr(c, cx - h * 0.52, cy - h * 0.72, cx + h * 0.52, cy + h * 0.72, T.s(3), outline=col, width=w)
        c.create_line(cx - h * 0.25, cy - h * 0.25, cx + h * 0.25, cy - h * 0.25, fill=col, width=w,
                      capstyle="round")
        c.create_line(cx - h * 0.25, cy + h * 0.1, cx + h * 0.25, cy + h * 0.1, fill=col, width=w,
                      capstyle="round")


# --------------------------------------------------------------- icon pack
ICON_DIR = "assets/icons"
_icon_cache = {}
_icon_missing = set()

FILE_ICONS = {"doc": "document", "pdf": "document", "image": "image", "video": "video",
              "audio": "audio", "archive": "archive", "app": "app", "code": "code",
              "folder": "folder", "other": "document"}
GLYPH_FALLBACK = {"import": "plus", "document": "folder", "image": "folder", "video": "folder",
                  "audio": "folder", "archive": "folder", "app": "folder", "code": "folder"}


def _quantize(color):
    """Snap a hex colour to 16-step channels so spring-driven tints reuse one cache entry."""
    try:
        return "#%02x%02x%02x" % tuple(min(255, int(c) // 16 * 16 + 8) for c in
                                       (int(color[i:i + 2], 16) for i in (1, 3, 5)))
    except Exception:
        return color


def icon_photo(name, size, color):
    """A tinted PNG from assets/icons, cached per name, size and colour.

    Pillow does the alpha mask and the LANCZOS resize. Without Pillow this returns
    None, so every caller can fall back to the drawn glyphs; the shipped builds
    install Pillow so the icon pack is always the one people see.
    """
    size = max(8, int(round(size)))
    color = _quantize(color)
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    if name in _icon_missing:
        return None
    path = A.resource_path(os.path.join(ICON_DIR, name + ".png"))
    if not os.path.isfile(path):
        _icon_missing.add(name)
        return None
    try:
        from PIL import Image, ImageTk
    except Exception:
        _icon_missing.add(name)
        return None
    try:
        src = Image.open(path).convert("RGBA")
        box = src.getchannel("A").getbbox()
        if box:
            src = src.crop(box)
        scale = min(size / max(1, src.width), size / max(1, src.height))
        w = max(1, int(round(src.width * scale)))
        h = max(1, int(round(src.height * scale)))
        alpha = src.resize((w, h), Image.LANCZOS).getchannel("A")
        tinted = Image.new("RGBA", (w, h), color)
        tinted.putalpha(alpha)
        ph = ImageTk.PhotoImage(tinted)
    except Exception:
        return None
    _icon_cache[key] = ph
    return ph


def draw_icon(c, name, cx, cy, sz, col):
    """Draw an icon from the pack; the matching drawn glyph if it is unavailable."""
    ph = icon_photo(name, sz, col)
    if ph is None:
        draw_glyph(c, GLYPH_FALLBACK.get(name, name), cx, cy, col, sz,
                   width=max(1.2, T.s(1.8)))
        return False
    c.create_image(int(round(cx)), int(round(cy)), image=ph, anchor="center")
    return True


def draw_file_icon(c, kind, x, y, size=38):
    """A tinted rounded tile with the file-type icon."""
    fill, ink = tint_fill(kind)
    rr(c, x, y, x + size, y + size, T.s(10), fill=fill, outline="")
    cx, cy = x + size / 2, y + size / 2
    ph = icon_photo(FILE_ICONS.get(kind, "document"), size * 0.56, ink)
    if ph is not None:
        c.create_image(int(round(cx)), int(round(cy)), image=ph, anchor="center")
        return
    if kind in ("video",):
        rr(c, cx - size * 0.22, cy - size * 0.2, cx + size * 0.22, cy + size * 0.2, T.s(3), outline=ink,
           width=T.s(1.6))
        c.create_polygon(cx - size * 0.06, cy - size * 0.1, cx - size * 0.06, cy + size * 0.1,
                         cx + size * 0.14, cy, fill=ink, outline="")
    elif kind == "image":
        rr(c, cx - size * 0.22, cy - size * 0.2, cx + size * 0.22, cy + size * 0.2, T.s(3), outline=ink,
           width=T.s(1.6))
        circle(c, cx - size * 0.08, cy - size * 0.08, size * 0.035, fill=ink, outline="")
        c.create_line(cx - size * 0.17, cy + size * 0.13, cx - size * 0.03, cy - size * 0.01,
                      cx + size * 0.06, cy + size * 0.09, cx + size * 0.17, cy - size * 0.02,
                      fill=ink, width=T.s(1.5), joinstyle="round", capstyle="round")
    elif kind == "audio":
        c.create_line(cx + size * 0.06, cy - size * 0.18, cx + size * 0.06, cy + size * 0.08,
                      fill=ink, width=T.s(1.6), capstyle="round")
        c.create_line(cx + size * 0.06, cy - size * 0.18, cx + size * 0.2, cy - size * 0.23,
                      cx + size * 0.2, cy + size * 0.03, fill=ink, width=T.s(1.6), capstyle="round",
                      joinstyle="round")
        circle(c, cx - size * 0.02, cy + size * 0.11, size * 0.065, fill=ink, outline="")
        circle(c, cx + size * 0.12, cy + size * 0.06, size * 0.065, fill=ink, outline="")
    elif kind == "archive":
        rr(c, cx - size * 0.2, cy - size * 0.2, cx + size * 0.2, cy + size * 0.2, T.s(3), outline=ink,
           width=T.s(1.6))
        c.create_line(cx, cy - size * 0.2, cx, cy + size * 0.06, fill=ink, width=T.s(1.6),
                      dash=(2, 2))
        c.create_line(cx - size * 0.07, cy + size * 0.06, cx + size * 0.07, cy + size * 0.06,
                      fill=ink, width=T.s(1.6), capstyle="round")
    elif kind == "app":
        rr(c, cx - size * 0.22, cy - size * 0.22, cx + size * 0.22, cy + size * 0.22, T.s(3), outline=ink,
           width=T.s(1.6))
        c.create_line(cx - size * 0.22, cy - size * 0.1, cx + size * 0.22, cy - size * 0.1, fill=ink,
                      width=T.s(1.4))
        for i in (-1, 0, 1):
            circle(c, cx + i * size * 0.08, cy - size * 0.16, size * 0.017, fill=ink, outline="")
    elif kind == "code":
        c.create_line(cx - size * 0.05, cy - size * 0.16, cx - size * 0.17, cy, cx - size * 0.05,
                      cy + size * 0.16, fill=ink, width=T.s(1.6), capstyle="round", joinstyle="round")
        c.create_line(cx + size * 0.05, cy - size * 0.16, cx + size * 0.17, cy, cx + size * 0.05,
                      cy + size * 0.16, fill=ink, width=T.s(1.6), capstyle="round", joinstyle="round")
        c.create_line(cx + size * 0.1, cy - size * 0.2, cx - size * 0.1, cy + size * 0.2, fill=ink,
                      width=T.s(1.4), capstyle="round")
    elif kind == "folder":
        c.create_line(cx - size * 0.22, cy + size * 0.16, cx - size * 0.22, cy - size * 0.13,
                      cx - size * 0.06, cy - size * 0.13, cx - size * 0.01, cy - size * 0.06,
                      cx + size * 0.14, cy - size * 0.06, fill=ink, width=T.s(1.6), joinstyle="round",
                      capstyle="round")
        c.create_line(cx - size * 0.22, cy + size * 0.16, cx + size * 0.23, cy + size * 0.16,
                      cx + size * 0.23, cy + size * 0.02, cx - size * 0.22, cy + size * 0.02,
                      fill=ink, width=T.s(1.6), joinstyle="round")
    elif kind == "doc":
        rr(c, cx - size * 0.16, cy - size * 0.22, cx + size * 0.16, cy + size * 0.22, T.s(2.5),
           outline=ink, width=T.s(1.5))
        for i, ww in ((-0.08, 0.24), (0.02, 0.24), (0.12, 0.15)):
            c.create_line(cx - size * 0.09, cy + size * i, cx - size * 0.09 + size * ww, cy + size * i,
                          fill=ink, width=T.s(1.3), capstyle="round")
    else:
        rr(c, cx - size * 0.16, cy - size * 0.22, cx + size * 0.16, cy + size * 0.22, T.s(2.5),
           outline=ink, width=T.s(1.5))
        c.create_line(cx - size * 0.08, cy, cx + size * 0.08, cy, fill=ink, width=T.s(1.3),
                      capstyle="round")


# ---------------------------------------------------------------------- cards
class Card(tk.Canvas):
    """Rounded white surface that redraws itself. Subclasses implement draw()."""
    RADIUS = 18

    def __init__(self, parent, motion, bg=T.BG, radius=None, border=True, **kw):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, **kw)
        self.motion, self.bg = motion, bg
        self.radius = self.RADIUS if radius is None else radius
        self.border = border
        self.W = self.H = 0
        self.reveal = Spring(motion, self, 1.0, response=0.5, eps=0.004)
        self.bind("<Configure>", self._resized)

    def _resized(self, e):
        self.W, self.H = e.width, e.height
        self.redraw()

    def enter(self, delay=0):
        self.reveal.jump(0.0)
        self.motion.later(delay, lambda: self.reveal.to(1.0))

    def redraw(self):
        if self.W < 8 or self.H < 8:
            return
        self.delete("all")
        r = T.s(self.radius)
        # a whisper of depth, never a heavy drop shadow
        rr(self, 1, 2, self.W - 1, self.H - 1, r, fill=T.SHADOW, outline="")
        rr(self, 1, 1, self.W - 2, self.H - 3, r, fill=T.CARD,
           outline=T.LINE if self.border else "")
        self.draw()

    def draw(self):
        pass

    def text(self, x, y, txt, size=10, weight="normal", fill=T.TEXT, anchor="nw", width=None,
             rise=True, bg=T.CARD, **kw):
        t = clamp(self.reveal.value, 0, 1)
        args = dict(text=txt, font=T.F(size, weight), fill=mix(bg, fill, t), anchor=anchor, **kw)
        if width:
            args["width"] = width
        return self.create_text(x, y + ((1 - t) * T.s(7) if rise else 0), **args)

    def fade(self, color, bg=T.CARD):
        return mix(bg, color, clamp(self.reveal.value, 0, 1))


# --------------------------------------------------------------------- button
class Button(tk.Canvas):
    """A quiet desktop button. Press feedback is immediate; hover is a spring."""
    VARIANTS = {
        "primary": (T.INK, "#303036", "#FFFFFF", T.INK),
        "secondary": ("#EFEFF3", "#E5E5EA", T.TEXT, T.LINE2),
        "quiet": (None, T.TRACK, T.SUB, ""),
        "accent": (T.ACCENT, "#00A2BB", "#06323A", T.ACCENT),
        "danger": (T.RED_SOFT, "#FBDDE0", T.RED, T.RED_SOFT),
    }

    def __init__(self, parent, motion, text, command=None, style="secondary", bg=T.BG, h=None,
                 width=None, icon=None, size=10, enabled=True, radius=None):
        self.text_value = text
        self.command = command
        self.style = style
        self.motion = motion
        self.bgc = bg
        self.icon = icon
        self.font_size = size
        self.enabled = enabled
        self.h = h or T.s(38)
        self.radius = radius if radius is not None else T.s(10 if self.h >= T.s(34) else 8)
        pad = T.s(18)
        self.w = width or (measure(text, size, "bold") + pad * 2 + (T.s(22) if icon else 0))
        super().__init__(parent, width=self.w, height=self.h, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2" if enabled else "arrow", takefocus=1 if enabled else 0)
        self.hover = Spring(motion, self, 0.0, response=0.2)
        self.press = Spring(motion, self, 0.0, response=0.13)
        self.focus = Spring(motion, self, 0.0, response=0.2)
        self.bind("<Enter>", lambda e: self.hover.to(1))
        self.bind("<Leave>", lambda e: (self.hover.to(0), self.press.to(0)))
        self.bind("<ButtonPress-1>", self._down)
        self.bind("<ButtonRelease-1>", self._up)
        self.bind("<FocusIn>", lambda e: self.focus.to(1))
        self.bind("<FocusOut>", lambda e: self.focus.to(0))
        self.bind("<Return>", lambda e: self._fire())
        self.bind("<space>", lambda e: self._fire())
        self.redraw()

    def _down(self, e):
        if not self.enabled:
            return
        self.focus_set()
        self.press.to(1)

    def _up(self, e):
        if not self.enabled:
            return
        self.press.to(0)
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h:
            self.command and self.command()

    def _fire(self):
        if self.enabled and self.command:
            self.command()

    def set_text(self, text, width=None):
        self.text_value = text
        if width:
            self.w = width
        else:
            self.w = max(measure(text, self.font_size, "bold") + T.s(36) + (T.s(22) if self.icon else 0),
                         T.s(64))
        self.configure(width=self.w)
        self.redraw()

    def set_enabled(self, on):
        if self.enabled != on:
            self.enabled = on
            self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
            self.hover.to(0)
            self.redraw()

    def redraw(self):
        if not self.w:
            return
        self.delete("all")
        base, hov, fg, border = self.VARIANTS.get(self.style, self.VARIANTS["secondary"])
        if not self.enabled:
            base, hov, fg, border = T.TRACK, T.TRACK, T.FAINT, ""
        base = base if base is not None else self.bgc
        col = mix(base, hov, max(self.hover.value, self.press.value))
        inset = self.press.value * T.s(1.2)
        rr(self, inset, inset, self.w - inset, self.h - inset, self.radius, fill=col,
           outline=border if border and not self.enabled else border)
        if self.focus.value > 0.02:
            rr(self, 1, 1, self.w - 1, self.h - 1, self.radius + 1,
               outline=mix(self.bgc, T.FOCUS, self.focus.value), width=T.s(2))
        tx = self.w / 2
        if self.icon:
            icon_sz = T.s(15)
            total = icon_sz + T.s(8) + measure(self.text_value, self.font_size, "bold")
            x0 = (self.w - total) / 2
            draw_icon(self, self.icon, x0 + icon_sz / 2, self.h / 2, icon_sz, fg)
            tx = x0 + icon_sz + T.s(8) + measure(self.text_value, self.font_size, "bold") / 2
        self.create_text(tx, self.h / 2, text=self.text_value, font=T.F(self.font_size, "bold"), fill=fg,
                         anchor="center")


class IconButton(tk.Canvas):
    def __init__(self, parent, motion, icon, command, bg=T.BG, size=32, color=T.SUB, tip=None):
        self.motion, self.icon, self.command, self.color = motion, icon, command, color
        self.sz = size
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.hover = Spring(motion, self, 0.0, response=0.2)
        self.press = Spring(motion, self, 0.0, response=0.13)
        self.bind("<Enter>", lambda e: self.hover.to(1))
        self.bind("<Leave>", lambda e: (self.hover.to(0), self.press.to(0)))
        self.bind("<ButtonPress-1>", lambda e: (self.focus_set(), self.press.to(1)))
        self.bind("<ButtonRelease-1>", self._up)
        self.bind("<Return>", lambda e: self.command and self.command())
        self.bind("<space>", lambda e: self.command and self.command())
        self.redraw()

    def _up(self, e):
        self.press.to(0)
        if 0 <= e.x <= self.sz and 0 <= e.y <= self.sz and self.command:
            self.command()

    def redraw(self):
        self.delete("all")
        if self.hover.value > 0.01 or self.press.value > 0.01:
            rr(self, 2, 2, self.sz - 2, self.sz - 2, T.s(8),
               fill=mix(self.cget("bg"), T.TRACK, max(self.hover.value, self.press.value)), outline="")
        col = mix(self.color, T.TEXT, max(self.hover.value, self.press.value))
        draw_icon(self, self.icon, self.sz / 2, self.sz / 2, T.s(16), col)


# ------------------------------------------------------------------ nav rail
class NavRail(tk.Canvas):
    ITEMS = [("search", "Search", "search"), ("installers", "Installers", "installers"),
             ("protection", "Protection", "protection"), ("websites", "Websites", "globe"),
             ("blueprint", "Blueprint", "blueprint"), ("settings", "Settings", "settings")]

    def __init__(self, parent, motion, on_select, logo=None, on_notify=None):
        super().__init__(parent, bg=T.SIDEBAR, highlightthickness=0, bd=0)
        self.motion, self.on_select, self.logo = motion, on_select, logo
        self.on_notify = on_notify
        self.unread = 0
        self.bell_hover = False
        self.active, self.hover = 0, -1
        self.W = self.H = 0
        self.pill = Spring(motion, self, 0.0, response=0.34, damping=1.0)
        self.status = ("Index ready", "Starting\u2026", T.FAINT)
        self.bind("<Configure>", self._resized)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<MouseWheel>", lambda e: None)

    def _top(self):
        return T.s(112)

    def _pitch(self):
        return T.s(45)

    def _resized(self, e):
        self.W, self.H = e.width, e.height
        self.redraw()

    def _index_at(self, x, y):
        if not (T.s(10) <= x <= self.W - T.s(10)):
            return -1
        i = (y - self._top()) // self._pitch()
        return int(i) if 0 <= i < len(self.ITEMS) else -1

    def _bell_at(self, x, y):
        return self.W - T.s(46) <= x <= self.W - T.s(10) and T.s(18) <= y <= T.s(62)

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.configure(cursor="hand2" if i >= 0 else "")
            self.redraw()

    def _move(self, e):
        bell = self._bell_at(e.x, e.y)
        if bell != self.bell_hover:
            self.bell_hover = bell
            self.redraw()
        self._set_hover(-1 if bell else self._index_at(e.x, e.y))

    def _press(self, e):
        if self._bell_at(e.x, e.y):
            if self.on_notify:
                self.on_notify()
            return
        i = self._index_at(e.x, e.y)
        if i >= 0:
            self.select(self.ITEMS[i][0])
        elif e.y > self.H - T.s(70) and e.y < self.H - T.s(20):
            self.on_select("settings")

    def set_unread(self, count):
        count = max(0, int(count or 0))
        if count == self.unread:
            return
        self.unread = count
        self.redraw()

    def select(self, key, notify=True):
        try:
            i = [k for k, _, _ in self.ITEMS].index(key)
        except ValueError:
            return
        self.active = i
        self.pill.to(i)
        if notify:
            self.on_select(key)

    def set_status(self, title, sub, color):
        self.status = (title, sub, color)
        self.redraw()

    def redraw(self):
        if self.W < 10:
            return
        self.delete("all")
        W = self.W
        # brand
        if self.logo is not None:
            self.create_image(T.s(22), T.s(24), image=self.logo, anchor="nw")
            tx = T.s(22) + self.logo.width() + T.s(11)
        else:
            rr(self, T.s(22), T.s(24), T.s(54), T.s(56), T.s(9), fill=T.ACCENT, outline="")
            draw_icon(self, "search", T.s(38), T.s(40), T.s(19), "#FFFFFF")
            tx = T.s(66)
        self.create_text(tx, T.s(40), text="ClickScope", font=T.F(14, "bold"), fill=T.TEXT, anchor="w")
        # notification bell, top right of the rail
        bx, by = W - T.s(28), T.s(40)
        if self.bell_hover:
            circle(self, bx, by, T.s(15), fill=T.SIDEBAR_HOVER, outline="")
        bcol = T.TEXT if (self.bell_hover or self.unread) else T.SUB
        self.create_arc(bx - T.s(8), by - T.s(10), bx + T.s(8), by + T.s(5), start=0, extent=180,
                        style="arc", outline=bcol, width=T.s(1.8))
        self.create_line(bx - T.s(8), by - T.s(3), bx - T.s(8), by + T.s(4), fill=bcol, width=T.s(1.8),
                         capstyle="round")
        self.create_line(bx + T.s(8), by - T.s(3), bx + T.s(8), by + T.s(4), fill=bcol, width=T.s(1.8),
                         capstyle="round")
        self.create_line(bx - T.s(10), by + T.s(4), bx + T.s(10), by + T.s(4), fill=bcol, width=T.s(1.8),
                         capstyle="round")
        circle(self, bx, by + T.s(7), T.s(1.9), fill=bcol, outline="")
        if self.unread:
            bx2, by2 = bx + T.s(8), by - T.s(10)
            circle(self, bx2, by2, T.s(5.5), fill=T.RED, outline=T.SIDEBAR, width=T.s(1.4))
            if self.unread > 9:
                self.create_text(bx2, by2, text="9+", font=T.F(6, "bold"), fill="#FFFFFF", anchor="center")
            else:
                self.create_text(bx2, by2, text=str(self.unread), font=T.F(7, "bold"), fill="#FFFFFF",
                                 anchor="center")

        top, pitch = self._top(), self._pitch()
        py = top + self.pill.value * pitch
        if 0 <= self.hover != round(self.pill.value):
            hy = top + self.hover * pitch
            rr(self, T.s(12), hy + 2, W - T.s(12), hy + T.s(40) + 2, T.s(11), fill="#E7E7EC", outline="")
        # selected pill: white, hairline, tiny shadow
        rr(self, T.s(12), py + 3, W - T.s(12), py + T.s(40) + 3, T.s(11), fill="#E8E8ED", outline="")
        rr(self, T.s(12), py, W - T.s(12), py + T.s(40), T.s(11), fill=T.CARD, outline=T.SIDEBAR_LINE)
        for i, (key, label, icon) in enumerate(self.ITEMS):
            t = 1 - min(1.0, abs(self.pill.value - i))
            col = mix(T.SUB, T.TEXT, t)
            cy = top + i * pitch + T.s(20)
            active = t > 0.5
            pr = T.ACCENT_D if active else T.SUB
            draw_icon(self, icon, T.s(35), cy, T.s(19), pr)
            self.create_text(T.s(55), cy, text=label, font=T.F(10, "bold" if t > 0.5 else "normal"),
                             fill=col, anchor="w")

        # bottom status: a quiet system-health line, not a dashboard
        line_y = self.H - T.s(86)
        self.create_line(T.s(20), line_y, W - T.s(20), line_y, fill=T.SIDEBAR_LINE)
        title, sub, color = self.status
        dx, dy = T.s(28), line_y + T.s(28)
        circle(self, dx, dy, T.s(4), fill=color, outline="")
        self.create_text(T.s(42), dy - T.s(7), text=title, font=T.F(9, "bold"), fill=T.TEXT, anchor="w")
        if sub:
            self.create_text(T.s(42), dy + T.s(10), text=ellipsize(sub, 8, "normal", W - T.s(58)),
                             font=T.F(8), fill=T.FAINT, anchor="w")


# --------------------------------------------------------------- search field
class SearchField(tk.Canvas):
    def __init__(self, parent, motion, on_change=None, on_submit=None, on_nav=None, on_reveal=None,
                 bg=T.BG):
        super().__init__(parent, height=T.s(54), bg=bg, highlightthickness=0, bd=0)
        self.motion = motion
        self.on_change, self.on_submit, self.on_nav, self.on_reveal = on_change, on_submit, on_nav, on_reveal
        self.W, self.H = 0, T.s(54)
        self.focus_spring = Spring(motion, self, 0.0, response=0.22)
        self.hover = Spring(motion, self, 0.0, response=0.22)
        self.var = tk.StringVar(master=self)
        self.entry = tk.Entry(self, textvariable=self.var, font=T.F(11), relief="flat", bd=0,
                              bg=T.CARD, fg=T.TEXT, insertbackground=T.TEXT, highlightthickness=0,
                              selectbackground=T.ACCENT_SOFT, selectforeground=T.TEXT)
        self.entry.place(x=T.s(48), y=T.s(15), width=T.s(200), height=T.s(24))
        self._timer = None
        self._hover_clear = False
        self.entry.bind("<Return>", lambda e: self.on_submit and self.on_submit())
        self.entry.bind("<Up>", lambda e: self.on_nav and self.on_nav(-1))
        self.entry.bind("<Down>", lambda e: self.on_nav and self.on_nav(1))
        self.entry.bind("<Control-Return>", lambda e: self.on_reveal and self.on_reveal())
        self.entry.bind("<Escape>", self._escape)
        self.entry.bind("<FocusIn>", lambda e: (self.focus_spring.to(1), self.redraw()))
        self.entry.bind("<FocusOut>", lambda e: (self.focus_spring.to(0), self.redraw()))
        self.var.trace_add("write", self._changed)
        self.bind("<Configure>", self._resized)
        self.bind("<Enter>", lambda e: self.hover.to(1))
        self.bind("<Leave>", lambda e: (self.hover.to(0), self._clear_hover()))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<Motion>", self._move)
        self.redraw()

    def _resized(self, e):
        self.W, self.H = e.width, e.height
        right = T.s(46) if self.var.get() else T.s(80)
        self.entry.place(x=T.s(48), y=(self.H - T.s(24)) // 2, width=max(20, self.W - T.s(48) - right),
                         height=T.s(24))
        self.redraw()

    def _changed(self, *a):
        if self._timer:
            try:
                self.after_cancel(self._timer)
            except Exception:
                pass
        self._timer = self.after(95, self._emit)
        self.redraw()

    def _emit(self):
        self._timer = None
        if self.on_change:
            self.on_change(self.var.get())

    def _escape(self, e):
        if self.var.get():
            self.set_text("")
        else:
            self.entry.selection_clear()

    def _press(self, e):
        self.entry.focus_set()
        w = self.W
        if self.var.get() and e.x >= w - T.s(48):
            self.set_text("")
            return
        self.entry.icursor("end")

    def _move(self, e):
        clear = bool(self.var.get()) and e.x >= self.W - T.s(48)
        if clear != self._hover_clear:
            self._hover_clear = clear
            self.configure(cursor="hand2" if clear else "xterm")
            self.redraw()

    def _clear_hover(self):
        self._hover_clear = False
        self.configure(cursor="")

    def text(self):
        return self.var.get()

    def set_text(self, text):
        self.var.set(text)
        self.entry.icursor("end")
        self.entry.focus_set()
        self.redraw()

    def focus(self):
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def set_enabled(self, on):
        self.entry.configure(state="normal" if on else "disabled")

    def redraw(self):
        if self.W < 20:
            return
        self.delete("all")
        focus = clamp(self.focus_spring.value, 0, 1)
        border = mix(T.LINE2, T.FOCUS, focus)
        shadow = mix(self.cget("bg"), T.SHADOW, 0.7)
        rr(self, 1, 2, self.W - 1, self.H - 1, T.s(14), fill=shadow, outline="")
        rr(self, 1, 1, self.W - 2, self.H - 3, T.s(14), fill=T.CARD, outline=border,
           width=T.s(1.2 + focus * 0.6))
        draw_icon(self, "search", T.s(27), self.H / 2, T.s(18), mix(T.FAINT, T.ACCENT_D, focus))
        if not self.var.get():
            self.create_text(T.s(48), self.H / 2, text="Search for files, folders and apps", font=T.F(11),
                             fill=T.FAINT, anchor="w")
        if self.var.get():
            col = T.SUB if self._hover_clear else T.FAINT
            rr(self, self.W - T.s(42), self.H / 2 - T.s(13), self.W - T.s(16), self.H / 2 + T.s(13),
               T.s(13), fill=T.TRACK if self._hover_clear else "", outline="")
            draw_icon(self, "close", self.W - T.s(29), self.H / 2, T.s(15), col)
        else:
            key_w, key_h = T.s(42), T.s(22)
            x2 = self.W - T.s(16)
            x1 = x2 - key_w
            y1 = self.H / 2 - key_h / 2
            rr(self, x1, y1, x2, y1 + key_h, T.s(6), fill=T.TRACK, outline=T.LINE)
            self.create_text((x1 + x2) / 2, self.H / 2, text="Ctrl K", font=T.F(8, "bold"),
                             fill=T.FAINT, anchor="center")


# --------------------------------------------------------------------- chips
class Chips(tk.Canvas):
    def __init__(self, parent, motion, options, on_change=None, bg=T.BG, h=None):
        super().__init__(parent, height=h or T.s(30), bg=bg, highlightthickness=0, bd=0)
        self.motion, self.options, self.on_change = motion, list(options), on_change
        self.selected = options[0][0] if options else None
        self.hover = -1
        self.W, self.H = 0, h or T.s(30)
        self.boxes = []
        self.bind("<Configure>", self._resized)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<ButtonPress-1>", self._press)
        self.redraw()

    def _resized(self, e):
        self.W, self.H = e.width, e.height
        self.redraw()

    def _layout(self):
        x, boxes = 0, []
        for key, label in self.options:
            w = measure(label, 9, "bold") + T.s(26)
            x1, y1 = x, (self.H - T.s(28)) / 2
            boxes.append((key, x1, y1, x1 + w, y1 + T.s(28)))
            x += w + T.s(6)
        self.boxes = boxes

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.configure(cursor="hand2" if i >= 0 else "")
            self.redraw()

    def _move(self, e):
        self._set_hover(self._index(e.x, e.y))

    def _index(self, x, y):
        for i, (_, x1, y1, x2, y2) in enumerate(self.boxes):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i
        return -1

    def _press(self, e):
        i = self._index(e.x, e.y)
        if i >= 0:
            self.select(self.boxes[i][0])

    def select(self, key, notify=True):
        if key == self.selected:
            return
        self.selected = key
        self.redraw()
        if notify and self.on_change:
            self.on_change(key)

    def redraw(self):
        if self.W < 10:
            return
        self.delete("all")
        self._layout()
        for i, (key, x1, y1, x2, y2) in enumerate(self.boxes):
            on = key == self.selected
            if on:
                fill, fg = T.INK, "#FFFFFF"
            elif i == self.hover:
                fill, fg = T.TRACK, T.TEXT
            else:
                fill, fg = "", T.SUB
            if fill:
                rr(self, x1, y1, x2, y2, T.s(14), fill=fill, outline="")
            self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=dict(self.options)[key],
                             font=T.F(9, "bold" if on else "normal"), fill=fg, anchor="center")


# ------------------------------------------------------------------ chip menu
class ChipButton(tk.Canvas):
    """A small pill that opens a menu, styled like the filter chips."""

    def __init__(self, parent, motion, text, command, bg=T.BG, active=False, h=None, width=None):
        self.motion = motion
        self.text_value = text
        self.command = command
        self.active = bool(active)
        self.bgc = bg
        self.h = h or T.s(28)
        self.w = width or (measure(text, 9, "bold") + T.s(44))
        super().__init__(parent, width=self.w, height=self.h, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.hover = Spring(motion, self, 0.0, response=0.2)
        self.press = Spring(motion, self, 0.0, response=0.13)
        self.bind("<Enter>", lambda e: self.hover.to(1))
        self.bind("<Leave>", lambda e: (self.hover.to(0), self.press.to(0)))
        self.bind("<ButtonPress-1>", lambda e: self.press.to(1))
        self.bind("<ButtonRelease-1>", self._up)
        self.bind("<Return>", lambda e: self.command and self.command())
        self.bind("<space>", lambda e: self.command and self.command())
        self.redraw()

    def _up(self, e):
        self.press.to(0)
        if 0 <= e.x <= self.w and self.command:
            self.command()

    def set_text(self, text, active=None):
        if active is not None:
            self.active = bool(active)
        self.text_value = text
        self.w = measure(text, 9, "bold") + T.s(44)
        self.configure(width=self.w)
        self.redraw()

    def set_active(self, active):
        self.active = bool(active)
        self.redraw()

    def redraw(self):
        self.delete("all")
        if self.active:
            fill, fg, border = T.INK, "#FFFFFF", T.INK
        elif self.hover.value > 0.01:
            fill, fg, border = T.TRACK, T.TEXT, ""
        else:
            fill, fg, border = "", T.SUB, T.LINE2
        rr(self, 1, 1, self.w - 1, self.h - 1, T.s(13), fill=fill, outline=border,
           width=T.s(1))
        tx = T.s(13)
        self.create_text(tx, self.h / 2, text=ellipsize(self.text_value, 9, "bold", self.w - T.s(34)),
                         font=T.F(9, "bold" if self.active else "normal"), fill=fg, anchor="w")
        cx, cy = self.w - T.s(14), self.h / 2
        self.create_line(cx - T.s(3.5), cy - T.s(2), cx, cy + T.s(1.8), cx + T.s(3.5), cy - T.s(2),
                         fill=fg, width=T.s(1.4), capstyle="round", joinstyle="round")


# --------------------------------------------------------------- results view
class ResultsView(Card):
    ROW = 62
    HEAD = 48
    FOOT = 32

    def __init__(self, parent, motion, on_open=None, on_reveal=None, on_menu=None):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.on_open, self.on_reveal, self.on_menu = on_open, on_reveal, on_menu
        self.results, self.query = [], ""
        self.selected, self.hover = -1, -1
        self.scroll = Spring(motion, self, 0.0, response=0.22, eps=0.4)
        self.reveal.jump(1.0)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<Button-3>", self._menu)
        self.bind("<Up>", lambda e: self.move(-1))
        self.bind("<Down>", lambda e: self.move(1))
        self.bind("<Return>", lambda e: self.open_selected())
        self.bind("<Control-Return>", lambda e: self.reveal_selected())

    def _view_h(self):
        return max(0, self.H - self.HEAD - self.FOOT)

    def _max_scroll(self):
        return max(0, len(self.results) * T.s(self.ROW) - self._view_h())

    def set_results(self, results, query=""):
        self.results = list(results)
        self.query = query or ""
        self.selected = 0 if self.results else -1
        self.scroll.jump(0)
        self.redraw()

    def set_query(self, query):
        self.query = query or ""
        self.redraw()

    def _row_at(self, y):
        if not (T.s(self.HEAD) <= y <= self.H - T.s(self.FOOT)):
            return -1
        i = int((y - T.s(self.HEAD) + self.scroll.value) // T.s(self.ROW))
        return i if 0 <= i < len(self.results) else -1

    def _wheel(self, e):
        step = -(e.delta / 120.0) * T.s(self.ROW) * 1.5
        self.scroll.to(clamp(self.scroll.target + step, 0, self._max_scroll()))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.configure(cursor="hand2" if i >= 0 else "")
            self.redraw()

    def _move(self, e):
        self._set_hover(self._row_at(e.y))

    def _click(self, e):
        i = self._row_at(e.y)
        if i >= 0:
            self.selected = i
            self.redraw()

    def _double(self, e):
        i = self._row_at(e.y)
        if i >= 0 and self.on_open:
            self.on_open(self.results[i])

    def _menu(self, e):
        i = self._row_at(e.y)
        if i >= 0:
            self.selected = i
            self.redraw()
            if self.on_menu:
                self.on_menu(self.results[i], e)

    def move(self, delta):
        if not self.results:
            return
        self.selected = int(clamp(self.selected + delta, 0, len(self.results) - 1))
        row = T.s(self.ROW)
        top = self.selected * row
        view = self._view_h()
        if top < self.scroll.target:
            self.scroll.to(top)
        elif top + row > self.scroll.target + view:
            self.scroll.to(top + row - view)
        self.redraw()

    def open_selected(self):
        if 0 <= self.selected < len(self.results) and self.on_open:
            self.on_open(self.results[self.selected])

    def reveal_selected(self):
        if 0 <= self.selected < len(self.results) and self.on_reveal:
            self.on_reveal(self.results[self.selected])

    def draw(self):
        if not self.results:
            cardw = self.W
            self.create_rectangle(T.s(8), 3, cardw - T.s(8), T.s(self.HEAD), fill=T.CARD, outline="")
            self.create_text(T.s(22), T.s(self.HEAD) / 2, text="No matches", font=T.F(10, "bold"),
                             fill=T.TEXT, anchor="w")
            self.create_line(T.s(20), T.s(self.HEAD), cardw - T.s(20), T.s(self.HEAD), fill=T.LINE)
            cy = T.s(self.HEAD) + max(T.s(60), (self.H - T.s(self.HEAD)) * 0.34)
            circle(self, cardw / 2, cy, T.s(22), fill=T.TRACK, outline="")
            draw_icon(self, "search", cardw / 2, cy, T.s(21), T.FAINT)
            self.create_text(cardw / 2, cy + T.s(42), text="Nothing matches that yet",
                             font=T.F(13, "bold"), fill=T.TEXT, anchor="center")
            q = ellipsize(self.query, 9, "normal", min(T.s(420), cardw - T.s(80)))
            msg = f"Try fewer words, or another spelling." if not self.query else f"No file name or folder contains \u201c{q}\u201d."
            self.create_text(cardw / 2, cy + T.s(64), text=msg, font=T.F(9), fill=T.SUB, anchor="center")
            return
        cardw = self.W
        row = T.s(self.ROW)
        top = T.s(self.HEAD)
        view_h = self._view_h()
        # visible rows only, so scrolling stays frame-smooth
        first = max(0, int(self.scroll.value // row) - 1)
        last = min(len(self.results), int((self.scroll.value + view_h) // row) + 2)
        for i in range(first, last):
            r = self.results[i]
            y = top + i * row - self.scroll.value
            if y + row < top - 4 or y > self.H - T.s(self.FOOT) + 4:
                continue
            if i == self.selected:
                rr(self, T.s(8), y + 3, cardw - T.s(8), y + row - 3, T.s(10), fill=T.ACCENT_SOFT,
                   outline="")
            elif i == self.hover:
                rr(self, T.s(8), y + 3, cardw - T.s(8), y + row - 3, T.s(10), fill=T.HOVER, outline="")
            draw_file_icon(self, file_color_kind(r.get("name"), r.get("kind", "other"),
                                                 bool(r.get("is_dir"))), T.s(20), y + T.s(12), T.s(38))
            name_x = T.s(70)
            meta_w = T.s(132)
            self._draw_name(name_x, y + T.s(11), r, cardw - name_x - meta_w - T.s(26))
            sub = display_dir(r)
            self.create_text(name_x, y + T.s(34), text=middle_ellipsize(sub, 9, "normal",
                                                                      cardw - name_x - meta_w - T.s(26)),
                             font=T.F(9), fill=T.SUB, anchor="w")
            meta = "Folder" if r.get("is_dir") else r.get("size_text") or format_size(r.get("size", 0))
            age = r.get("age_text") or ""
            if r.get("protected"):
                draw_icon(self, "protection", cardw - T.s(146), y + T.s(35), T.s(11), T.ACCENT_D)
            self.create_text(cardw - T.s(22), y + T.s(15), text=meta, font=T.F(9, "bold"),
                             fill=T.SUB if i == self.selected else T.FAINT, anchor="e")
            self.create_text(cardw - T.s(22), y + T.s(35), text=age, font=T.F(9), fill=T.FAINT, anchor="e")
            if i < len(self.results) - 1:
                self.create_line(T.s(70), y + row - 1, cardw - T.s(22), y + row - 1, fill=T.LINE)
        # header + footer bands hide rows scrolling underneath
        self.create_rectangle(T.s(8), 3, cardw - T.s(8), top, fill=T.CARD, outline="")
        self.create_rectangle(T.s(8), self.H - T.s(self.FOOT), cardw - T.s(8), self.H - 5, fill=T.CARD,
                              outline="")
        n = len(self.results)
        self.create_text(T.s(22), top / 2, text=f"{n} result{'s' if n != 1 else ''}", font=T.F(10, "bold"),
                         fill=T.TEXT, anchor="w")
        self.create_text(cardw - T.s(22), top / 2, text="Enter opens  \u00b7  Ctrl+Enter shows the folder",
                         font=T.F(8), fill=T.FAINT, anchor="e")
        self.create_line(T.s(20), top, cardw - T.s(20), top, fill=T.LINE)
        self.create_line(T.s(20), self.H - T.s(self.FOOT), cardw - T.s(20), self.H - T.s(self.FOOT),
                         fill=T.LINE)
        if n:
            qhint = f"Selected {self.selected + 1} of {n}" if self.selected >= 0 else ""
            if qhint:
                self.create_text(cardw / 2, self.H - T.s(16), text=qhint, font=T.F(8), fill=T.FAINT,
                                 anchor="center")
        # slim scrollbar
        mx = self._max_scroll()
        if mx > 0:
            frac = view_h / (len(self.results) * row)
            th = max(T.s(34), view_h * frac)
            ty = top + (view_h - th) * (clamp(self.scroll.value, 0, mx) / mx)
            rr(self, cardw - T.s(12), ty, cardw - T.s(8), ty + th, T.s(2), fill=T.LINE2, outline="")

    def _draw_name(self, x, y, r, avail):
        name = r.get("name") or ""
        size, weight = 10, "bold"
        if not self.query or "\u2026" in name:
            self.create_text(x, y, text=ellipsize(name, size, weight, avail), font=T.F(size, weight),
                             fill=T.TEXT, anchor="w")
            return
        tokens = []
        q = self.query.strip()
        if q:
            tokens.append(q)
        tokens += [t for t in q.split() if t.lower() != q.lower()]
        spans = []
        low = name.lower()
        for tok in tokens:
            for m in re_finditer(tok, name):
                spans.append((m.start(), m.end()))
        if not spans:
            self.create_text(x, y, text=ellipsize(name, size, weight, avail), font=T.F(size, weight),
                             fill=T.TEXT, anchor="w")
            return
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        if merged[-1][1] - merged[0][0] > 200:
            merged = merged[:6]
        used = 0.0
        idx = 0
        for a, b in merged:
            if a > idx:
                seg = name[idx:a]
                w = measure(seg, size, weight)
                if used + w > avail - T.s(8):
                    rest = ellipsize(name[idx:], size, weight, max(0, avail - used))
                    self.create_text(x + used, y, text=rest, font=T.F(size, weight), fill=T.TEXT, anchor="w")
                    return
                self.create_text(x + used, y, text=seg, font=T.F(size, weight), fill=T.TEXT, anchor="w")
                used += w
            seg = name[a:b]
            w = measure(seg, size, "bold")
            if used + w > avail - T.s(8):
                rest = ellipsize(name[a:], size, weight, max(0, avail - used))
                self.create_text(x + used, y, text=rest, font=T.F(size, weight), fill=T.TEXT, anchor="w")
                return
            self.create_text(x + used, y, text=seg, font=T.F(size, "bold"), fill=T.TEXT, anchor="w")
            used += w
            idx = b
        if idx < len(name):
            rest = name[idx:]
            w = measure(rest, size, weight)
            if used + w > avail:
                rest = ellipsize(rest, size, weight, max(0, avail - used))
            self.create_text(x + used, y, text=rest, font=T.F(size, weight), fill=T.TEXT, anchor="w")


def re_finditer(token, text):
    import re
    if not token:
        return []
    return list(re.finditer(re.escape(token), text, re.IGNORECASE))


def format_size(n):
    from appdata import human_size
    return human_size(n)


def display_dir(r):
    from appdata import middle_ellipsis
    path = r.get("dir") or ""
    home = os.path.expanduser("~")
    if home and path.lower().startswith(home.lower()):
        path = "~" + path[len(home):]
    return path


# --------------------------------------------------------------------- switch
class Switch(tk.Canvas):
    def __init__(self, parent, motion, on=False, command=None, bg=T.CARD):
        super().__init__(parent, width=T.s(48), height=T.s(28), bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=1)
        self.motion, self.command = motion, command
        self.value = bool(on)
        self.knob = Spring(motion, self, 1.0 if on else 0.0, response=0.24, damping=1.0)
        self.hover = Spring(motion, self, 0.0, response=0.2)
        self.bind("<ButtonPress-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<Enter>", lambda e: self.hover.to(1))
        self.bind("<Leave>", lambda e: self.hover.to(0))
        self.redraw()

    def _toggle(self, e=None):
        self.value = not self.value
        self.knob.to(1.0 if self.value else 0.0)
        if self.command:
            self.command(self.value)

    def set(self, on, notify=False):
        self.value = bool(on)
        self.knob.to(1.0 if on else 0.0)
        if notify and self.command:
            self.command(self.value)

    def redraw(self):
        self.delete("all")
        k = clamp(self.knob.value, 0, 1)
        track = mix("#D9D9E0", T.ACCENT, k)
        rr(self, 2, 4, self.winfo_reqwidth() - 2, self.winfo_reqheight() - 4, T.s(10), fill=track, outline="")
        th = self.winfo_reqheight()
        kr = th / 2 - T.s(5)
        x = T.s(14) + k * (self.winfo_reqwidth() - T.s(28))
        circle(self, x, th / 2, kr, fill="#FFFFFF", outline="#DADDE3")

