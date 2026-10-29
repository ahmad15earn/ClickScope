"""A small blue 'cursor companion' that follows the mouse and narrates the setup."""
import tkinter as tk

import theme as T
from motion import Spring
from widgets import measure, rrect

KEY = "#010203"  # colour made transparent on Windows


class CursorGuide:
    BW, BH = 340, 120

    def __init__(self, root, motion, logo_path):
        self.root, self.text, self.alive = root, "", True
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
        try:
            self.logo = tk.PhotoImage(file=logo_path)
        except Exception:
            self.logo = None
        self.x = Spring(motion, self, 0.0, response=0.16, eps=0.5)
        self.y = Spring(motion, self, 0.0, response=0.16, eps=0.5)
        px, py = self._pointer()
        self.x.jump(px + T.s(18))
        self.y.jump(py + T.s(16))
        self._draw()
        self._loop()

    def _pointer(self):
        try:
            return self.root.winfo_pointerxy()
        except Exception:
            return (0, 0)

    def _loop(self):
        if not self.alive:
            return
        px, py = self._pointer()
        self.x.to(px + T.s(18))
        self.y.to(py + T.s(16))
        self.root.after(16, self._loop)

    def redraw(self):  # called by the motion engine each frame
        if self.alive:
            self.win.geometry(f"+{int(self.x.value)}+{int(self.y.value)}")

    def set_text(self, text):
        self.text = text
        self._draw()

    def _draw(self):
        c = self.cv
        c.delete("all")
        lw = self.logo.width() if self.logo else 0
        if self.logo:
            c.create_image(0, 0, image=self.logo, anchor="nw")
        if self.text:
            tw = min(T.s(240), measure(self.text, 10, "bold") + T.s(4))
            lines = max(1, -(-measure(self.text, 10, "bold") // max(tw, 1)))
            bh = T.s(14) + lines * T.s(19)
            rrect(c, lw + T.s(2), T.s(4), lw + T.s(2) + tw + T.s(28), T.s(4) + bh, T.s(14), fill=T.INK, outline="")
            c.create_text(lw + T.s(16), T.s(4) + T.s(7), text=self.text, font=T.F(10, "bold"), fill="#FFFFFF",
                          anchor="nw", width=tw)

    def close(self):
        self.alive = False
        try:
            self.win.destroy()
        except Exception:
            pass
