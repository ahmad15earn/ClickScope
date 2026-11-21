"""The four everyday pages: Search, Installers, Blueprint and Settings."""
import math
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog

import appdata as A
import blueprint as B
import installers as I
import theme as T
from motion import Spring, clamp, mix
from uikit import (Button, Card, Chips, IconButton, ResultsView, SearchField, Switch, circle, draw_file_icon,
                   draw_glyph, ellipsize, line_height, measure, middle_ellipsize, photo, rr)


def count(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "0"


def short_time(ts):
    if not ts:
        return "not yet"
    today = time.strftime("%d %b %Y", time.localtime())
    day = time.strftime("%d %b %Y", time.localtime(ts))
    if day == today:
        return "today at " + time.strftime("%H:%M", time.localtime(ts))
    return A.human_date(ts)


class Page(tk.Frame):
    """Shared page chrome: a quiet title, one line of context, a right slot."""

    def __init__(self, parent, app, title, subtitle):
        super().__init__(parent, bg=T.BG)
        self.app = app
        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=(T.s(40), T.s(36)), pady=(T.s(26), 0))
        left = tk.Frame(head, bg=T.BG)
        left.pack(side="left")
        tk.Label(left, text=title, font=T.F(24, "bold"), fg=T.TEXT, bg=T.BG, anchor="w").pack(anchor="w")
        tk.Label(left, text=subtitle, font=T.F(10), fg=T.SUB, bg=T.BG, anchor="w").pack(
            anchor="w", pady=(T.s(2), 0))
        self.head_right = tk.Frame(head, bg=T.BG)
        self.head_right.pack(side="right", anchor="n", pady=(T.s(5), 0))

    def on_show(self):
        pass


# --------------------------------------------------------------------- search
class SearchIntro(Card):
    """The one card under the search field: first run, progress, or places."""

    def __init__(self, parent, motion, folders, on_build, on_cancel, on_folder):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.mode = "empty"
        self.stats = {}
        self.progress = {}
        self.error = ""
        self.folders = list(folders)
        self.on_build, self.on_cancel, self.on_folder = on_build, on_cancel, on_folder
        self.primary = Button(self, motion, "Index this PC", self._primary, style="primary", bg=T.CARD,
                              h=T.s(40))
        self.phase = 0.0
        self._anim = None
        self.hover = -1
        self.zones = []
        self.reveal.jump(1.0)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.redraw()

    def _primary(self):
        if self.mode == "progress":
            self.on_cancel()
        else:
            self.on_build()

    def set_state(self, stats, progress=None, error=""):
        self.stats, self.progress, self.error = stats or {}, progress or {}, error or ""
        building = bool(progress and progress.get("state") == "scanning")
        next_mode = "progress" if building else ("ready" if self.stats.get("files", 0) else "empty")
        changed = next_mode != self.mode
        self.mode = next_mode
        if changed:
            self.primary.set_text("Stop indexing" if next_mode == "progress" else "Index this PC")
            if next_mode == "progress":
                self._start_anim()
            else:
                self._stop_anim()
            self.phase = 0.0
        self.redraw()

    def _start_anim(self):
        if self._anim is None and self.winfo_exists():
            self._anim = self.after(45, self._tick)

    def _stop_anim(self):
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None

    def _tick(self):
        self._anim = None
        if self.mode == "progress" and self.winfo_exists():
            self.phase = (self.phase + 0.045) % 1.0
            self.redraw()
            self._anim = self.after(45, self._tick)

    def destroy(self):
        self._stop_anim()
        super().destroy()

    def _move(self, e):
        z = self._zone_at(e.x, e.y)
        if z != self.hover:
            self.hover = z
            self.configure(cursor="hand2" if z >= 0 else "")
            self.redraw()

    def _leave(self, e=None):
        if self.hover != -1:
            self.hover = -1
            self.configure(cursor="")
            self.redraw()

    def _zone_at(self, x, y):
        for i, (x1, y1, x2, y2, _, _) in enumerate(self.zones):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return i
        return -1

    def _press(self, e):
        i = self._zone_at(e.x, e.y)
        if i >= 0:
            self.on_folder(self.zones[i][5])

    def _place_primary(self, x, y):
        self.primary.place(x=x, y=y)

    def redraw(self):
        super().redraw()
        if self.W < 40:
            return
        if self.mode == "ready":
            self.primary.place_forget()
            self._draw_ready()
        elif self.mode == "progress":
            self._draw_progress()
        else:
            self._draw_empty()

    # ----- ready
    def _draw_ready(self):
        W, H = self.W, self.H
        pad = T.s(30)
        self.zones = []
        left_w = max(T.s(270), min(T.s(390), W * 0.44))
        gx = int(W * 0.50)
        if W < T.s(680):
            gx = int(W * 0.47)
        # left
        circle(self, pad + T.s(3), T.s(31), T.s(3.5), fill=T.GREEN, outline="")
        self.create_text(pad + T.s(14), T.s(31), text="SEARCH IS READY", font=T.F(8, "bold"),
                         fill=T.GREEN, anchor="w")
        self.text(pad, T.s(50), "Find anything, as you type.", 20, "bold", fill=T.TEXT)
        self.create_text(pad, T.s(84), text="Search every file and folder on this PC.\nNo waiting, no Windows Search.",
                         font=T.F(10), fill=T.SUB, anchor="nw", width=left_w - pad)
        files = self.stats.get("files", 0)
        dirs = self.stats.get("dirs", 0)
        self.text(pad, T.s(132), f"{count(files)} files  \u00b7  {count(dirs)} folders", 9, "bold",
                  fill=T.TEXT)
        self.create_text(pad, T.s(151), text="Last indexed " + short_time(self.stats.get("last_build")),
                         font=T.F(9), fill=T.FAINT, anchor="w")
        # privacy at the bottom
        py = H - T.s(45)
        if py > T.s(175):
            draw_glyph(self, "info", pad + T.s(7), py, T.FAINT, T.s(13), width=T.s(1.4))
            self.create_text(pad + T.s(20), py, text="Names, sizes and dates only. Never file contents.",
                             font=T.F(8), fill=T.FAINT, anchor="w")
        # places
        self.create_text(gx, T.s(27), text="PLACES", font=T.F(8, "bold"), fill=T.FAINT, anchor="w")
        avail = W - gx - pad
        cols = 2
        gap = T.s(8)
        tw = (avail - gap * (cols - 1)) / cols
        th = T.s(61)
        for i, (label, path) in enumerate(self.folders[:6]):
            col, row = i % cols, i // cols
            x = gx + col * (tw + gap)
            y = T.s(43) + row * (th + gap)
            if y + th > H - T.s(18):
                break
            hot = i == self.hover
            rr(self, x, y, x + tw, y + th, T.s(11), fill=T.HOVER if hot else T.TRACK, outline="")
            draw_glyph(self, "folder", x + T.s(18), y + T.s(21), T.FOLDER_INK, T.s(16), width=T.s(1.6))
            self.create_text(x + T.s(32), y + T.s(19), text=ellipsize(label, 9, "bold", tw - T.s(42)),
                             font=T.F(9, "bold"), fill=T.TEXT, anchor="w")
            home = os.path.expanduser("~")
            shown = "~" + path[len(home):] if home and path.lower().startswith(home.lower()) else path
            self.create_text(x + T.s(12), y + T.s(40), text=ellipsize(shown, 8, "normal", tw - T.s(24)),
                             font=T.F(8), fill=T.FAINT, anchor="w")
            self.zones.append((x, y, x + tw, y + th, label, path))

    # ----- empty / first run
    def _draw_empty(self):
        W, H = self.W, self.H
        cx = W / 2
        cy = max(T.s(62), H * 0.27)
        circle(self, cx, cy, T.s(28), fill=T.ACCENT_SOFT, outline="")
        draw_glyph(self, "search", cx, cy, T.ACCENT_D, T.s(23), width=T.s(2))
        self.text(cx, cy + T.s(46), "Make this PC searchable", 20, "bold", fill=T.TEXT, anchor="center")
        body = ("One quiet pass over your drives builds a local index. After that,\n"
                "every file appears the moment you start typing.")
        self.create_text(cx, cy + T.s(72), text=body, font=T.F(10), fill=T.SUB, anchor="n",
                         justify="center", width=min(T.s(470), W - T.s(80)))
        btn_y = cy + T.s(126)
        self.primary.set_text("Index this PC")
        self._place_primary((W - self.primary.w) / 2, btn_y)
        note = "Takes a few minutes. Only names, folders, sizes and dates."
        if self.error:
            note = self.error
        self.create_text(cx, btn_y + self.primary.h + T.s(17), text=note, font=T.F(8),
                         fill=T.RED if self.error else T.FAINT, anchor="center")

    # ----- progress
    def _draw_progress(self):
        W, H = self.W, self.H
        cx = W / 2
        cy = max(T.s(58), H * 0.25)
        self.text(cx, cy, "Indexing this PC\u2026", 20, "bold", fill=T.TEXT, anchor="center")
        p = self.progress or {}
        files, dirs = p.get("files", 0), p.get("dirs", 0)
        self.create_text(cx, cy + T.s(30), text=f"{count(files)} files  \u00b7  {count(dirs)} folders found",
                         font=T.F(9), fill=T.SUB, anchor="center")
        bar_w = min(T.s(440), W - T.s(150))
        bar_x = (W - bar_w) / 2
        bar_y = cy + T.s(56)
        rr(self, bar_x, bar_y, bar_x + bar_w, bar_y + T.s(6), T.s(3), fill=T.TRACK, outline="")
        seg = bar_w * 0.28
        span = bar_w - seg
        pos = (math.sin(self.phase * math.tau) * 0.5 + 0.5) * span
        rr(self, bar_x + pos, bar_y, bar_x + pos + seg, bar_y + T.s(6), T.s(3), fill=T.ACCENT, outline="")
        current = p.get("current") or "Looking through your folders\u2026"
        current = A.middle_ellipsis(current, 70)
        self.create_text(cx, bar_y + T.s(24), text=current, font=T.F(8), fill=T.FAINT, anchor="center")
        btn_y = bar_y + T.s(52)
        self.primary.set_text("Stop indexing")
        self._place_primary((W - self.primary.w) / 2, btn_y)
        self.create_text(cx, btn_y + self.primary.h + T.s(17),
                         text="You can keep using this PC; the index runs in the background.",
                         font=T.F(8), fill=T.FAINT, anchor="center")


class SearchPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Search", "Every file on this PC, in a blink.")
        badge = tk.Canvas(self.head_right, width=T.s(84), height=T.s(26), bg=T.BG, highlightthickness=0)
        badge.pack()
        circle(badge, T.s(7), T.s(13), T.s(3.5), fill=T.GREEN, outline="")
        badge.create_text(T.s(16), T.s(13), text="Local only", font=T.F(8, "bold"), fill=T.SUB, anchor="w")

        wrap = tk.Frame(self, bg=T.BG)
        wrap.pack(fill="x", padx=(T.s(40), T.s(36)), pady=(T.s(19), 0))
        self.field = SearchField(wrap, app.motion, on_change=self._typed, on_submit=self._open_selected,
                                 on_nav=self._nav, on_reveal=self._reveal_selected)
        self.field.pack(fill="x")

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=(T.s(40), T.s(36)), pady=(T.s(11), 0))
        self.kind = app.state.get("search_filter", "all")
        options = [("all", "All"), ("doc", "Documents"), ("image", "Images"), ("video", "Video"),
                   ("audio", "Audio"), ("app", "Apps"), ("archive", "Archives"), ("code", "Code")]
        self.chips = Chips(bar, app.motion, options, on_change=self._filter, h=T.s(30))
        if self.kind not in [k for k, _ in options]:
            self.kind = "all"
        self.chips.selected = self.kind
        self.chips.pack(fill="x")

        self.body = tk.Frame(self, bg=T.BG)
        self.body.pack(fill="both", expand=True, padx=(T.s(40), T.s(36)), pady=(T.s(14), T.s(26)))
        self.intro = SearchIntro(self.body, app.motion, A.known_folders(), self._build, self._cancel,
                                 self._open_folder)
        self.results = ResultsView(self.body, app.motion, on_open=self._open, on_reveal=self._reveal,
                                   on_menu=self._menu)
        self.results.place(x=0, y=0, relwidth=1, relheight=1)
        self.intro.place(x=0, y=0, relwidth=1, relheight=1)
        self._intro_visible = True
        self._query = ""
        self._generation = 0
        self._building = False
        self._poll_id = None
        self._closed = False

    # ----------------------------------------------------------------- state
    def on_show(self):
        self._sync(animate=True)
        self.after(160, self._focus_field)

    def _focus_field(self):
        try:
            self.field.focus()
        except tk.TclError:
            pass

    def _stats(self):
        try:
            return self.app.index.stats(cache=False)
        except Exception:
            return {}

    def _sync(self, animate=False):
        st = self._stats()
        building = self.app.index.is_building()
        self._building = building
        progress = self.app.index.progress() if building else {}
        self.intro.set_state(st, progress)
        if animate and not self._query:
            self.intro.enter()
        self._choose_view()
        if building:
            self._start_poll()
        else:
            self._stop_poll()
        self.app.refresh_status()

    def _choose_view(self):
        q = self._query.strip()
        st = self._stats()
        show_results = bool(q) and (st.get("files", 0) or self._building)
        if show_results:
            if self._intro_visible:
                self.intro.place_forget()
                self.results.place(x=0, y=0, relwidth=1, relheight=1)
                self._intro_visible = False
            tk.Misc.tkraise(self.results)
        else:
            if not self._intro_visible:
                self.results.place_forget()
                self.intro.place(x=0, y=0, relwidth=1, relheight=1)
                self._intro_visible = True
            tk.Misc.tkraise(self.intro)

    def _start_poll(self):
        if self._poll_id is None and not self._closed:
            self._poll_id = self.after(350, self._poll)

    def _stop_poll(self):
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None

    def _poll(self):
        self._poll_id = None
        if self._closed:
            return
        building = self.app.index.is_building()
        st = self._stats()
        progress = self.app.index.progress() if building else {}
        self.intro.set_state(st, progress)
        self.app.refresh_status()
        if building:
            self._poll_id = self.after(350, self._poll)
        else:
            self._built(st)

    # ----------------------------------------------------------------- index
    def _build(self):
        if self.app.index.is_building():
            return
        self._building = True
        try:
            self.app.index.build_async(on_done=lambda ok, st: self.app.post(lambda: self._built(st, ok)))
        except Exception as e:
            self.app.toast(f"Could not start indexing: {e}", "error")
            self._building = False
            return
        self.intro.enter()
        self._sync()
        self.app.refresh_status()

    def _cancel(self):
        self.app.index.cancel()
        self._sync()

    def _built(self, stats=None, ok=True):
        self._building = False
        self._stop_poll()
        self.app.start_watcher()
        self.intro.set_state(self._stats(), {})
        self._choose_view()
        self.app.refresh_status()
        if stats and stats.get("files", 0):
            self.app.toast(f"Index ready \u2014 {count(stats['files'])} files searchable.", "good")
        elif not ok:
            self.app.toast("Indexing stopped early. Search still works with what was found.", "warn")
        if self._query.strip():
            self._search_now(self._query)

    def on_index_changed(self):
        if self.app.index.is_building():
            return
        if not self._query.strip():
            self.intro.set_state(self._stats(), {})
            self._choose_view()
        else:
            self._search_now(self._query)
        self.app.refresh_status()

    # ---------------------------------------------------------------- search
    def _typed(self, text):
        self._query = text or ""
        self._choose_view()
        if not self._query.strip():
            self._generation += 1
            return
        self._search_now(self._query)

    def _filter(self, kind):
        self.kind = kind
        self.app.state.set("search_filter", kind)
        if self._query.strip():
            self._search_now(self._query)

    def _search_now(self, query):
        q = query.strip()
        if not q:
            return
        self._generation += 1
        gen = self._generation
        kind = self.kind
        if self._intro_visible:
            self.results.set_results([], q)
        self.app.jobs.run(lambda: self.app.index.search(q, kind, limit=140),
                          on_done=lambda rows: self._results(gen, q, rows))

    def _results(self, gen, query, rows):
        if gen != self._generation or self._closed:
            return
        for r in rows:
            r["size_text"] = A.human_size(r.get("size"))
            r["age_text"] = A.human_age(r.get("mtime"))
        self._choose_view()
        self.results.set_results(rows, query)

    def _open_selected(self):
        self.results.open_selected()

    def _reveal_selected(self):
        self.results.reveal_selected()

    def _nav(self, delta):
        if not self._intro_visible:
            self.results.move(delta)

    def _open(self, result):
        path = result.get("path") or ""
        if not A.open_path(path):
            self.app.toast("Windows could not open that item.", "error")

    def _reveal(self, result):
        if not A.reveal_path(result.get("path") or ""):
            self.app.toast("Windows could not open that folder.", "error")

    def _open_folder(self, path):
        if not A.open_path(path):
            self.app.toast("That folder isn't available anymore.", "warn")

    def _menu(self, result, event):
        m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TEXT, activebackground=T.ACCENT_SOFT,
                    activeforeground=T.TEXT, font=T.F(9), bd=0)
        m.add_command(label="Open", command=lambda: self._open(result))
        m.add_command(label="Show in folder", command=lambda: self._reveal(result))
        m.add_separator()
        m.add_command(label="Copy full path", command=lambda: self._copy(result.get("path", "")))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _copy(self, text):
        if A.copy_text(text):
            self.app.toast("Path copied.", "good")
        else:
            self.app.toast("Could not copy the path.", "error")

    def destroy(self):
        self._closed = True
        self._stop_poll()
        super().destroy()


# ----------------------------------------------------------------- installers
class InstallerCard(Card):
    HEAD = 108
    ROW = 64
    FOOT = 62

    def __init__(self, parent, motion, on_delete, on_ignore, on_reveal, on_copy):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.items, self.selected = [], set()
        self.busy, self.used_index, self.age, self.error = False, True, 30, ""
        self.hover = -1
        self.spin = 0.0
        self._anim = None
        self.on_delete, self.on_ignore, self.on_reveal, self.on_copy = on_delete, on_ignore, on_reveal, on_copy
        self.scroll = Spring(motion, self, 0.0, response=0.22, eps=0.4)
        self.reveal.jump(1.0)
        self.pick_btn = Button(self, motion, "Select safe picks", self._safe_picks, style="quiet",
                               bg=T.CARD, h=T.s(32), size=9)
        self.trash_btn = Button(self, motion, "Move to Recycle Bin", self._delete, style="primary",
                                bg=T.CARD, h=T.s(38), size=9, icon="trash", enabled=False)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<ButtonPress-1>", self._click)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<Button-3>", self._menu)
        self.bind("<Up>", lambda e: self._move_key(-1))
        self.bind("<Down>", lambda e: self._move_key(1))
        self.redraw()

    # ----------------------------------------------------------------- state
    def set_loading(self, age, used_index=True):
        self.age, self.used_index = age, used_index
        self.items, self.selected, self.busy, self.error = [], set(), True, ""
        self.scroll.jump(0)
        self._start_spin()
        self.redraw()

    def set_items(self, items, age, used_index=True, error=""):
        self.age, self.used_index, self.error = age, used_index, error or ""
        self.items = list(items)
        keep = {i["path"] for i in self.items}
        self.selected &= keep
        self.busy = False
        self._stop_spin()
        self.scroll.jump(0)
        self.hover = -1
        self.redraw()

    def selection(self):
        return [i for i in self.items if i["path"] in self.selected]

    def selection_summary(self):
        chosen = self.selection()
        return len(chosen), sum(i.get("size", 0) for i in chosen)

    def _start_spin(self):
        if self._anim is None and self.winfo_exists():
            self._anim = self.after(60, self._tick)

    def _stop_spin(self):
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None

    def _tick(self):
        self._anim = None
        if self.busy and self.winfo_exists():
            self.spin = (self.spin + 26) % 360
            self.redraw()
            self._anim = self.after(60, self._tick)

    def destroy(self):
        self._stop_spin()
        super().destroy()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self._place_buttons()

    def _place_buttons(self):
        if not self.items or self.busy:
            self.pick_btn.place_forget()
            self.trash_btn.place_forget()
            return
        safe = set(I.safe_selection(self.items))
        label = "Clear safe picks" if safe and safe <= self.selected else "Select safe picks"
        if self.pick_btn.text_value != label:
            self.pick_btn.set_text(label)
        self.pick_btn.place(x=self.W - T.s(24) - self.pick_btn.w, y=T.s(30))
        self.trash_btn.set_enabled(bool(self.selected))
        self.trash_btn.place(x=self.W - T.s(24) - self.trash_btn.w, y=self.H - T.s(51))

    # ------------------------------------------------------------- geometry
    def _view_h(self):
        return max(0, self.H - T.s(self.HEAD) - T.s(self.FOOT))

    def _max_scroll(self):
        return max(0, len(self.items) * T.s(self.ROW) - self._view_h())

    def _row_at(self, y):
        if not (T.s(self.HEAD) <= y <= self.H - T.s(self.FOOT)):
            return -1
        i = int((y - T.s(self.HEAD) + self.scroll.value) // T.s(self.ROW))
        return i if 0 <= i < len(self.items) else -1

    # ---------------------------------------------------------------- input
    def _wheel(self, e):
        if not self.items:
            return
        step = -(e.delta / 120.0) * T.s(self.ROW) * 1.7
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
        if i < 0:
            return
        self.focus_set()
        path = self.items[i]["path"]
        if path in self.selected:
            self.selected.discard(path)
        else:
            self.selected.add(path)
        self.redraw()

    def _double(self, e):
        i = self._row_at(e.y)
        if i >= 0:
            self._reveal(self.items[i])

    def _move_key(self, delta):
        if not self.items:
            return
        if self.hover < 0:
            self.hover = 0
        else:
            self.hover = int(clamp(self.hover + delta, 0, len(self.items) - 1))
        row = T.s(self.ROW)
        top = self.hover * row
        view = self._view_h()
        if top < self.scroll.target:
            self.scroll.to(top)
        elif top + row > self.scroll.target + view:
            self.scroll.to(top + row - view)
        self.redraw()

    def _reveal(self, item):
        self.on_reveal(item["path"])

    def _menu(self, e):
        i = self._row_at(e.y)
        if i < 0:
            return
        it = self.items[i]
        m = tk.Menu(self, tearoff=0, bg=T.CARD, fg=T.TEXT, activebackground=T.ACCENT_SOFT,
                    activeforeground=T.TEXT, font=T.F(9), bd=0)
        m.add_command(label="Show in folder", command=lambda: self._reveal(it))
        m.add_command(label="Copy full path", command=lambda: self.on_copy(it["path"]))
        m.add_separator()
        m.add_command(label="Hide from this list", command=lambda: self.on_ignore(it["path"]))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # -------------------------------------------------------------- actions
    def _safe_picks(self):
        safe = set(I.safe_selection(self.items))
        if not safe:
            return
        if safe <= self.selected:
            self.selected -= safe
        else:
            self.selected |= safe
        self.redraw()

    def _delete(self):
        chosen = self.selection()
        if chosen:
            self.on_delete(chosen)

    # ----------------------------------------------------------------- draw
    def draw(self):
        if self.W < 10:
            return
        if self.items:
            self._draw_list()
        elif self.busy:
            self._draw_loading()
        else:
            self._draw_empty()

    def _draw_header(self):
        W, pad = self.W, T.s(24)
        self.create_text(pad, T.s(17), text="RECLAIMABLE", font=T.F(8, "bold"), fill=T.FAINT, anchor="w")
        total = sum(i.get("size", 0) for i in self.items)
        self.text(pad, T.s(28), A.human_size(total), 25, "bold", fill=T.TEXT)
        n = len(self.items)
        dups = sum(1 for i in self.items if i.get("duplicate_of"))
        bits = [f"{n} old installer{'s' if n != 1 else ''}"]
        if dups:
            bits.append(f"{dups} duplicate version{'s' if dups != 1 else ''}")
        bits.append(f"older than {self.age} days")
        self.create_text(pad, T.s(72), text="  \u00b7  ".join(bits), font=T.F(9), fill=T.SUB, anchor="w")
        if not self.used_index:
            self.create_text(pad, T.s(92), text="Quick scan of everyday folders \u2014 build the search index for a complete list.",
                             font=T.F(8), fill=T.AMBER, anchor="w")
        self.create_line(T.s(20), T.s(self.HEAD), W - T.s(20), T.s(self.HEAD), fill=T.LINE)

    def _draw_list(self):
        W = self.W
        top = T.s(self.HEAD)
        # Backing bands first, so header and footer content sit above them.
        self.create_rectangle(T.s(8), 3, W - T.s(8), top, fill=T.CARD, outline="")
        self.create_rectangle(T.s(8), self.H - T.s(self.FOOT), W - T.s(8), self.H - 5, fill=T.CARD,
                              outline="")
        self._draw_header()
        row = T.s(self.ROW)
        view = self._view_h()
        first = max(0, int(self.scroll.value // row) - 1)
        last = min(len(self.items), int((self.scroll.value + view) // row) + 2)
        for i in range(first, last):
            it = self.items[i]
            y = top + i * row - self.scroll.value
            if y + row < top - 2 or y > top + view + 2:
                continue
            chosen = it["path"] in self.selected
            if chosen:
                rr(self, T.s(8), y + 3, W - T.s(8), y + row - 3, T.s(10), fill=T.ACCENT_SOFT, outline="")
            elif i == self.hover:
                rr(self, T.s(8), y + 3, W - T.s(8), y + row - 3, T.s(10), fill=T.HOVER, outline="")
            # checkbox
            cy = y + row / 2
            bx = T.s(25)
            if chosen:
                rr(self, bx, cy - T.s(9), bx + T.s(18), cy + T.s(9), T.s(5), fill=T.INK, outline="")
                draw_glyph(self, "check", bx + T.s(9), cy, "#FFFFFF", T.s(11), width=T.s(1.8))
            else:
                rr(self, bx, cy - T.s(9), bx + T.s(18), cy + T.s(9), T.s(5), fill=T.CARD,
                   outline=T.LINE2 if i != self.hover else T.SUB)
            draw_file_icon(self, "archive", T.s(57), y + T.s(13), T.s(36))
            # meta on the right
            size_w = T.s(86)
            meta_x = W - T.s(24)
            reason = it.get("reason") or "Old download"
            badge_w = min(T.s(136), measure(reason, 8, "bold") + T.s(16))
            badge_ink, badge_fill = (T.AMBER, T.AMBER_SOFT) if it.get("duplicate_of") else (
                (T.ACCENT_D, T.ACCENT_SOFT) if it.get("age_days", 0) >= 365 else (T.SUB, T.TRACK))
            bx2 = meta_x - size_w
            bx1 = bx2 - badge_w
            rr(self, bx1, cy - T.s(10), bx2, cy + T.s(10), T.s(10), fill=badge_fill, outline="")
            self.create_text((bx1 + bx2) / 2, cy, text=reason, font=T.F(8, "bold"), fill=badge_ink,
                             anchor="center")
            name_x = T.s(104)
            avail = max(T.s(90), bx1 - name_x - T.s(16))
            self.create_text(name_x, y + T.s(12), text=ellipsize(it["name"], 10, "bold", avail),
                             font=T.F(10, "bold"), fill=T.TEXT, anchor="w")
            d = it.get("dir") or ""
            home = os.path.expanduser("~")
            if home and d.lower().startswith(home.lower()):
                d = "~" + d[len(home):]
            self.create_text(name_x, y + T.s(33), text=middle_ellipsize(d, 9, "normal", avail),
                             font=T.F(9), fill=T.SUB, anchor="w")
            self.create_text(meta_x, y + T.s(12), text=it.get("size_text") or A.human_size(it.get("size")),
                             font=T.F(9, "bold"), fill=T.SUB, anchor="e")
            self.create_text(meta_x, y + T.s(33), text=it.get("age_text", ""), font=T.F(9), fill=T.FAINT,
                             anchor="e")
            if i < len(self.items) - 1:
                self.create_line(T.s(104), y + row - 1, W - T.s(24), y + row - 1, fill=T.LINE)
        # bands
        self.create_line(T.s(20), self.H - T.s(self.FOOT), W - T.s(20), self.H - T.s(self.FOOT),
                         fill=T.LINE)
        n_sel, size_sel = self.selection_summary()
        foot_y = self.H - T.s(self.FOOT) / 2
        if n_sel:
            self.create_text(T.s(24), foot_y, text=f"{n_sel} selected", font=T.F(10, "bold"),
                             fill=T.TEXT, anchor="w")
            self.create_text(T.s(24) + measure(f"{n_sel} selected", 10, "bold") + T.s(8), foot_y,
                             text=f"\u00b7  {A.human_size(size_sel)}", font=T.F(9), fill=T.SUB, anchor="w")
        else:
            self.create_text(T.s(24), foot_y, text="Select files to clear, or let ClickScope pick the safe ones.",
                             font=T.F(9), fill=T.FAINT, anchor="w")
        if self._max_scroll() > 0:
            frac = self._view_h() / (len(self.items) * row)
            th = max(T.s(30), self._view_h() * frac)
            ty = top + (self._view_h() - th) * (clamp(self.scroll.value, 0, self._max_scroll())
                                               / self._max_scroll())
            rr(self, W - T.s(12), ty, W - T.s(8), ty + th, T.s(2), fill=T.LINE2, outline="")

    def _draw_loading(self):
        cx, cy = self.W / 2, self.H * 0.42
        self.create_arc(cx - T.s(20), cy - T.s(20), cx + T.s(20), cy + T.s(20), start=self.spin,
                        extent=100, style="arc", outline=T.ACCENT, width=T.s(2.2))
        self.create_text(cx, cy + T.s(42), text="Looking for old installers\u2026", font=T.F(13, "bold"),
                         fill=T.TEXT, anchor="center")
        note = "Checking the search index." if self.used_index else "Reading everyday folders. This can take a moment."
        self.create_text(cx, cy + T.s(65), text=note, font=T.F(9), fill=T.SUB, anchor="center")

    def _draw_empty(self):
        cx, cy = self.W / 2, self.H * 0.40
        if self.error:
            circle(self, cx, cy, T.s(27), fill=T.RED_SOFT, outline="")
            draw_glyph(self, "warning", cx, cy, T.RED, T.s(22), width=T.s(1.8))
            self.create_text(cx, cy + T.s(44), text="Could not finish the scan", font=T.F(13, "bold"),
                             fill=T.TEXT, anchor="center")
            self.create_text(cx, cy + T.s(66), text=self.error, font=T.F(9), fill=T.SUB, anchor="center",
                             width=min(T.s(500), self.W - T.s(80)))
            return
        circle(self, cx, cy, T.s(27), fill=T.GREEN_SOFT, outline="")
        draw_glyph(self, "check", cx, cy, T.GREEN, T.s(23), width=T.s(2))
        self.create_text(cx, cy + T.s(44), text="Nothing old is sitting around", font=T.F(13, "bold"),
                         fill=T.TEXT, anchor="center")
        self.create_text(cx, cy + T.s(66),
                         text=f"No installers older than {self.age} days were found in everyday folders.",
                         font=T.F(9), fill=T.SUB, anchor="center",
                         width=min(T.s(500), self.W - T.s(80)))


class InstallersPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Installers",
                         "Old setup files taking up space. Clear them safely.")
        self.scan_btn = Button(self.head_right, app.motion, "Scan again", self._scan, style="secondary",
                               h=T.s(36), size=9, icon="refresh")
        self.scan_btn.pack()
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=(T.s(40), T.s(36)), pady=(T.s(20), 0))
        tk.Label(bar, text="Older than", font=T.F(9), fg=T.FAINT, bg=T.BG).pack(side="left",
                                                                               pady=(T.s(8), 0))
        age = int(app.state.get("installer_age", 30) or 30)
        if age not in (30, 90, 365):
            age = 30
        self.age = age
        self.chips = Chips(bar, app.motion, [(30, "30 days"), (90, "3 months"), (365, "1 year")],
                           on_change=self._age_changed, h=T.s(30))
        self.chips.selected = age
        self.chips.pack(side="left", fill="x", expand=True, padx=(T.s(10), 0))
        self.hidden_btn = Button(bar, app.motion, "", self._show_hidden, style="quiet", bg=T.BG,
                                 h=T.s(30), size=9)
        self._update_hidden()

        self.body = tk.Frame(self, bg=T.BG)
        self.body.pack(fill="both", expand=True, padx=(T.s(40), T.s(36)), pady=(T.s(13), T.s(26)))
        self.card = InstallerCard(self.body, app.motion, self._ask_delete, self._ignore, self._reveal,
                                  self._copy)
        self.card.place(x=0, y=0, relwidth=1, relheight=1)
        self.loaded = False
        self._scan_id = 0
        self._closed = False

    def on_show(self):
        self._update_hidden()
        if not self.loaded:
            self._scan()
        else:
            self.card.enter()

    def on_index_changed(self):
        self.loaded = False
        if self.winfo_ismapped():
            self._scan()

    def _update_hidden(self):
        ignored = len(self.app.state.ignored_installers())
        if ignored:
            self.hidden_btn.set_text(f"Show {ignored} hidden")
            if not self.hidden_btn.winfo_ismapped():
                self.hidden_btn.pack(side="right")
        else:
            self.hidden_btn.pack_forget()

    def _age_changed(self, age):
        self.age = int(age)
        self.app.state.set("installer_age", self.age)
        self._scan()

    def _scan(self):
        if self._closed:
            return
        self._scan_id += 1
        token = self._scan_id
        self.loaded = True
        try:
            used_index = self.app.index.has_data()
        except Exception:
            used_index = False
        self.card.set_loading(self.age, used_index)
        age = self.age

        def work():
            return I.find_installers(index=self.app.index, min_age_days=age)

        def done(items):
            if self._closed or token != self._scan_id:
                return
            ignored = self.app.state.ignored_installers()
            items = [i for i in items if i["path"].lower() not in ignored]
            self.card.set_items(items, age, used_index)
            self._update_hidden()

        def failed(e):
            if self._closed or token != self._scan_id:
                return
            self.card.set_items([], age, used_index, error=str(e))

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _show_hidden(self):
        self.app.state.set("ignored_installers", [])
        self._update_hidden()
        self._scan()
        self.app.toast("Hidden installers are visible again.", "good")

    def _ask_delete(self, chosen):
        n = len(chosen)
        size = sum(i.get("size", 0) for i in chosen)
        more = "s" if n != 1 else ""
        self.app.confirm(
            f"Move {n} installer{more} to the Recycle Bin?",
            "They will disappear from this list. If you change your mind, open the Recycle Bin and restore them.",
            detail=f"{count(n)} file{more}  \u00b7  {A.human_size(size)}",
            confirm="Move to Recycle Bin",
            on_confirm=lambda: self._remove([i["path"] for i in chosen], n))

    def _remove(self, paths, n):
        def work():
            moved, failed = I.remove(paths)
            try:
                self.app.index.remove_paths(paths)
            except Exception:
                pass
            return moved, failed

        def done(result):
            moved, failed = result
            if moved:
                self.app.toast(f"Moved {moved} installer{'s' if moved != 1 else ''} to the Recycle Bin.", "good")
            if failed:
                self.app.toast(f"{len(failed)} file{'s' if len(failed) != 1 else ''} could not be moved.",
                               "warn")
            self._scan()
            self.app.search.on_index_changed()

        def failed(e):
            self.app.toast(f"Could not move the files: {e}", "error")

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _ignore(self, path):
        self.app.state.ignore_installer(path)
        self.card.items = [i for i in self.card.items if i["path"] != path]
        self.card.selected.discard(path)
        self.card.redraw()
        self._update_hidden()
        self.app.toast("Hidden from the installer list.", "good")

    def _reveal(self, path):
        if not A.reveal_path(path):
            self.app.toast("Could not show that file.", "error")

    def _copy(self, text):
        if A.copy_text(text):
            self.app.toast("Path copied.", "good")

    def destroy(self):
        self._closed = True
        super().destroy()


# ------------------------------------------------------------------ blueprint
class BlueprintCard(Card):
    def __init__(self, parent, motion, on_create, on_cancel, on_restore, on_export):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.record = None
        self.mode = "empty"
        self.progress = (0, "")
        self.phase = 0.0
        self._anim = None
        self.on_create, self.on_cancel, self.on_restore, self.on_export = on_create, on_cancel, on_restore, on_export
        self.new_btn = Button(self, motion, "Create blueprint", self.on_create, style="primary", bg=T.CARD,
                              h=T.s(38), size=9)
        self.restore_btn = Button(self, motion, "Restore folders", lambda: self.on_restore(self.record),
                                  style="secondary", bg=T.CARD, h=T.s(38), size=9)
        self.export_btn = Button(self, motion, "Export\u2026", lambda: self.on_export(self.record),
                                 style="quiet", bg=T.CARD, h=T.s(38), size=9)
        self.cancel_btn = Button(self, motion, "Stop", self.on_cancel, style="secondary", bg=T.CARD,
                                 h=T.s(38), size=9)
        self.reveal.jump(1.0)
        self.redraw()

    def set_record(self, record):
        self.record = record
        self.mode = "record" if record else "empty"
        self._stop_anim()
        self.redraw()

    def set_progress(self, folders=0, current=""):
        self.mode = "progress"
        self.progress = (folders, current or "")
        self._start_anim()
        self.redraw()

    def _start_anim(self):
        if self._anim is None and self.winfo_exists():
            self._anim = self.after(45, self._tick)

    def _stop_anim(self):
        if self._anim is not None:
            try:
                self.after_cancel(self._anim)
            except Exception:
                pass
            self._anim = None

    def _tick(self):
        self._anim = None
        if self.mode == "progress" and self.winfo_exists():
            self.phase = (self.phase + 0.045) % 1.0
            self.redraw()
            self._anim = self.after(45, self._tick)

    def destroy(self):
        self._stop_anim()
        super().destroy()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self._place_buttons()

    def _place_buttons(self):
        for b in (self.new_btn, self.restore_btn, self.export_btn, self.cancel_btn):
            b.place_forget()
        bottom = self.H - T.s(55)
        x = T.s(24)
        if self.mode == "record" and self.record:
            self.new_btn.set_text("New snapshot")
            self.new_btn.place(x=x, y=bottom)
            self.restore_btn.place(x=x + self.new_btn.w + T.s(8), y=bottom)
            self.export_btn.place(x=x + self.new_btn.w + self.restore_btn.w + T.s(16), y=bottom)
        elif self.mode == "progress":
            self.cancel_btn.place(x=x, y=bottom)
        else:
            self.new_btn.set_text("Create blueprint")
            self.new_btn.place(x=x, y=bottom)

    def _illustration(self, record=None):
        if self.W < T.s(500):
            return
        x2, y = self.W - T.s(26), T.s(44)
        w, h = T.s(176), T.s(142)
        x1 = x2 - w
        rr(self, x1, y, x2, y + h, T.s(14), fill="#FAFAFC", outline=T.LINE)
        for i in range(6):
            xx = x1 + T.s(18) + i * T.s(26)
            self.create_line(xx, y + T.s(14), xx, y + h - T.s(14), fill="#F2F3F7")
        for i in range(4):
            yy = y + T.s(24) + i * T.s(28)
            self.create_line(x1 + T.s(14), yy, x2 - T.s(14), yy, fill="#F2F3F7")
        # a tiny folder tree drawn over the grid
        cx = (x1 + x2) / 2
        rr(self, cx - T.s(40), y + T.s(19), cx + T.s(40), y + T.s(43), T.s(7), fill=T.ACCENT_SOFT,
           outline="")
        draw_glyph(self, "folder", cx - T.s(27), y + T.s(31), T.ACCENT_D, T.s(12), width=T.s(1.4))
        self.create_text(cx - T.s(16), y + T.s(31), text="This PC", font=T.F(8, "bold"), fill=T.ACCENT_D,
                         anchor="w")
        if record:
            drives = int(record.get("drives") or 0)
            folders = int(record.get("folders") or 0)
            labels = (f"{drives} drive{'s' if drives != 1 else ''}",
                      f"{count(folders // 1000)}k folders" if folders >= 10000 else f"{count(folders)} folders",
                      "wallpaper" if record.get("wallpaper") else "no wallpaper")
        else:
            labels = ("drives", "folders", "wallpaper")
        glyphs = ("drive", "folder", "wallpaper")
        box_w, gap, box_h = T.s(52), T.s(6), T.s(44)
        bx0 = x1 + (w - (3 * box_w + 2 * gap)) / 2
        by = y + T.s(88)
        self.create_line(cx, y + T.s(43), cx, y + T.s(64), fill="#CBD8DC", width=T.s(1.1))
        centers = [bx0 + i * (box_w + gap) + box_w / 2 for i in range(3)]
        self.create_line(centers[0], y + T.s(64), centers[-1], y + T.s(64), fill="#CBD8DC",
                         width=T.s(1.1))
        for i, (lbl, glyph) in enumerate(zip(labels, glyphs)):
            bx = bx0 + i * (box_w + gap)
            bcx = bx + box_w / 2
            self.create_line(bcx, y + T.s(64), bcx, by, fill="#CBD8DC", width=T.s(1.1))
            rr(self, bx, by, bx + box_w, by + box_h, T.s(7), fill=T.CARD, outline=T.LINE)
            draw_glyph(self, glyph, bcx, by + T.s(15), T.SUB, T.s(14), width=T.s(1.3))
            self.create_text(bcx, by + T.s(33), text=lbl, font=T.F(7, "bold"), fill=T.SUB,
                             anchor="center")

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(24)
        self.create_text(pad, T.s(18), text="PC DNA", font=T.F(8, "bold"), fill=T.FAINT, anchor="w")
        if self.mode == "progress":
            self.text(pad, T.s(38), "Mapping this PC\u2026", 20, "bold", fill=T.TEXT)
            folders, current = self.progress
            self.create_text(pad, T.s(76), text=f"{count(folders)} folders found so far", font=T.F(9),
                             fill=T.SUB, anchor="w")
            bar_w = min(T.s(380), self.W - T.s(48))
            bar_y = T.s(102)
            rr(self, pad, bar_y, pad + bar_w, bar_y + T.s(6), T.s(3), fill=T.TRACK, outline="")
            seg = bar_w * 0.28
            pos = (math.sin(self.phase * math.tau) * 0.5 + 0.5) * (bar_w - seg)
            rr(self, pad + pos, bar_y, pad + pos + seg, bar_y + T.s(6), T.s(3), fill=T.ACCENT, outline="")
            if current:
                self.create_text(pad, bar_y + T.s(24), text=A.middle_ellipsis(current, 64),
                                 font=T.F(8), fill=T.FAINT, anchor="w")
            self.create_text(pad, T.s(158), text="Folder names only. ClickScope never reads your documents.",
                             font=T.F(8), fill=T.FAINT, anchor="w")
            return
        if self.mode == "record" and self.record:
            r = self.record
            self.text(pad, T.s(38), "This PC's blueprint.", 20, "bold", fill=T.TEXT)
            pc = r.get("pc") or "This PC"
            self.create_text(pad, T.s(76), text=f"Saved {A.human_age(r.get('created_ts'))} on {pc}",
                             font=T.F(9), fill=T.SUB, anchor="w")
            bits = [f"{count(r.get('folders', 0))} folders"]
            if r.get("drives"):
                bits.append(f"{r['drives']} drive{'s' if r['drives'] != 1 else ''}")
            bits.append("wallpaper" if r.get("wallpaper") else "no wallpaper")
            self.create_text(pad, T.s(96), text="  \u00b7  ".join(bits), font=T.F(9), fill=T.FAINT,
                             anchor="w")
            self.create_text(pad, T.s(126), text="Restore the folders, the wallpaper, or take it all to a new PC.",
                             font=T.F(9), fill=T.SUB, anchor="w")
            self._illustration(r)
            self.create_text(pad, self.H - T.s(73), text="Contains no document contents.",
                             font=T.F(8), fill=T.FAINT, anchor="w")
            return
        # empty
        self.text(pad, T.s(42), "Keep the shape of this PC.", 20, "bold", fill=T.TEXT)
        self.create_text(pad, T.s(78),
                         text="A blueprint remembers every folder and your wallpaper,\nso a new PC can feel like home.",
                         font=T.F(10), fill=T.SUB, anchor="nw", width=min(T.s(430), self.W - T.s(60)))
        self._illustration()
        self.create_text(pad, self.H - T.s(73), text="Folders and wallpaper only. No documents, ever.",
                         font=T.F(8), fill=T.FAINT, anchor="w")


class WallpaperCard(Card):
    def __init__(self, parent, motion, on_save, on_restore, on_toggle_include):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.motion = motion
        self.current = None
        self.preview = None
        self.preview_photo = None
        self.latest = None
        self.on_save, self.on_restore, self.on_toggle_include = on_save, on_restore, on_toggle_include
        self.save_btn = Button(self, motion, "Save copy", lambda: self.on_save(), style="secondary",
                               bg=T.CARD, h=T.s(36), size=9)
        self.restore_btn = Button(self, motion, "Use saved", lambda: self.on_restore(self.latest),
                                  style="primary", bg=T.CARD, h=T.s(36), size=9, enabled=False)
        self.include = Switch(self, motion, True, command=self.on_toggle_include, bg=T.CARD)
        self.reveal.jump(1.0)
        self.redraw()

    def set_wallpaper(self, current, latest):
        self.current, self.latest = current, latest
        self.restore_btn.set_enabled(bool(latest))
        self.redraw()

    def set_preview(self, path):
        self.preview = path
        self.preview_photo = None
        self.redraw()

    def set_include(self, on):
        self.include.set(on)
        self.redraw()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self._place_buttons()

    def _place_buttons(self):
        self.save_btn.set_enabled(bool(self.current))
        bottom = self.H - T.s(48)
        self.save_btn.place(x=T.s(22), y=bottom)
        self.restore_btn.place(x=T.s(22) + self.save_btn.w + T.s(8), y=bottom)
        self.include.place(x=self.W - T.s(22) - self.include.winfo_reqwidth(), y=self.H - T.s(108))

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(22)
        self.create_text(pad, T.s(18), text="WALLPAPER", font=T.F(8, "bold"), fill=T.FAINT, anchor="w")
        pw = self.W - pad * 2
        ph = T.s(118)
        py = T.s(34)
        if self.preview:
            if self.preview_photo is None:
                self.preview_photo = photo(self.preview, max(10, int(pw)), max(10, int(ph)), T.s(10))
            if self.preview_photo is not None:
                self.create_image(pad, py, image=self.preview_photo, anchor="nw")
            else:
                self._placeholder(pad, py, pw, ph)
        else:
            self._placeholder(pad, py, pw, ph)
        y = py + ph + T.s(14)
        if self.current:
            self.create_text(pad, y, text=ellipsize(self.current.get("name", "Wallpaper"), 10, "bold",
                                                     pw), font=T.F(10, "bold"), fill=T.TEXT, anchor="w")
            style = self.current.get("style", "Fill")
            size = self.current.get("size_text", "")
            sub = "  \u00b7  ".join([x for x in (style, size) if x])
            self.create_text(pad, y + T.s(18), text=sub, font=T.F(8), fill=T.FAINT, anchor="w")
        else:
            self.create_text(pad, y, text="A solid colour", font=T.F(10, "bold"), fill=T.TEXT, anchor="w")
            self.create_text(pad, y + T.s(18), text="Windows isn't using a picture right now.", font=T.F(8),
                             fill=T.FAINT, anchor="w")
        self.create_text(pad, self.H - T.s(100), text="Include in new blueprints", font=T.F(9),
                         fill=T.SUB, anchor="w")
        if self.latest:
            self.create_text(pad, self.H - T.s(66), text="Saved copy available", font=T.F(8), fill=T.GREEN,
                             anchor="w")
        else:
            self.create_text(pad, self.H - T.s(66), text="No saved wallpaper yet", font=T.F(8), fill=T.FAINT,
                             anchor="w")

    def _placeholder(self, x, y, w, h):
        rr(self, x, y, x + w, y + h, T.s(10), fill=T.TRACK, outline="")
        for i, col in enumerate(("#E9EFF0", "#EDF5F2", "#F1EFE7")):
            yy = y + T.s(18) + i * T.s(26)
            self.create_line(x + T.s(18), yy, x + w - T.s(18), yy, fill=col, width=T.s(10),
                             capstyle="round")
        draw_glyph(self, "wallpaper", x + w / 2, y + h / 2, T.FAINT, T.s(30), width=T.s(1.8))


class HistoryCard(Card):
    HEAD = 48
    ROW = 58

    def __init__(self, parent, motion, on_action):
        super().__init__(parent, motion, bg=T.BG, radius=18)
        self.records = []
        self.hover = -1
        self.action_hover = None
        self.zones = []
        self.on_action = on_action
        self.scroll = Spring(motion, self, 0.0, response=0.22, eps=0.4)
        self.reveal.jump(1.0)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._click)
        self.redraw()

    def set_records(self, records):
        self.records = list(records)
        self.scroll.jump(0)
        self.hover = -1
        self.zones = []
        self.redraw()

    def _view_h(self):
        return max(0, self.H - T.s(self.HEAD))

    def _max_scroll(self):
        return max(0, len(self.records) * T.s(self.ROW) - self._view_h())

    def _row_at(self, y):
        if y < T.s(self.HEAD):
            return -1
        i = int((y - T.s(self.HEAD) + self.scroll.value) // T.s(self.ROW))
        return i if 0 <= i < len(self.records) else -1

    def _wheel(self, e):
        if not self.records:
            return
        step = -(e.delta / 120.0) * T.s(self.ROW) * 1.8
        self.scroll.to(clamp(self.scroll.target + step, 0, self._max_scroll()))

    def _zone_at(self, x, y):
        for x1, y1, x2, y2, action, rec in self.zones:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return action, rec
        return None, None

    def _move(self, e):
        action, rec = self._zone_at(e.x, e.y)
        key = (action, id(rec)) if action else None
        row = self._row_at(e.y)
        changed = key != self.action_hover or row != self.hover
        self.action_hover = key
        self.hover = row
        if changed:
            self.configure(cursor="hand2" if action else "")
            self.redraw()

    def _leave(self, e=None):
        if self.hover != -1 or self.action_hover:
            self.hover, self.action_hover = -1, None
            self.configure(cursor="")
            self.redraw()

    def _click(self, e):
        action, rec = self._zone_at(e.x, e.y)
        if action:
            self.on_action(action, rec)

    def draw(self):
        if self.W < 10:
            return
        W, pad = self.W, T.s(22)
        self.create_text(pad, T.s(25), text="History", font=T.F(11, "bold"), fill=T.TEXT, anchor="w")
        if self.records:
            self.create_text(W - pad, T.s(25), text=f"{len(self.records)} saved", font=T.F(8),
                             fill=T.FAINT, anchor="e")
        self.create_line(T.s(18), T.s(self.HEAD), W - T.s(18), T.s(self.HEAD), fill=T.LINE)
        self.zones = []
        if not self.records:
            cy = T.s(self.HEAD) + (self.H - T.s(self.HEAD)) * 0.44
            circle(self, W / 2, cy, T.s(23), fill=T.TRACK, outline="")
            draw_glyph(self, "blueprint", W / 2, cy, T.FAINT, T.s(21), width=T.s(1.7))
            self.create_text(W / 2, cy + T.s(38), text="Nothing saved yet", font=T.F(12, "bold"),
                             fill=T.TEXT, anchor="center")
            self.create_text(W / 2, cy + T.s(58),
                             text="Create a blueprint above, or save just the wallpaper.",
                             font=T.F(8), fill=T.FAINT, anchor="center")
            return
        row = T.s(self.ROW)
        top = T.s(self.HEAD)
        view = self._view_h()
        first = max(0, int(self.scroll.value // row) - 1)
        last = min(len(self.records), int((self.scroll.value + view) // row) + 2)
        for i in range(first, last):
            rec = self.records[i]
            y = top + i * row - self.scroll.value
            if y + row < top - 2 or y > top + view + 2:
                continue
            if i == self.hover:
                rr(self, T.s(8), y + 3, W - T.s(8), y + row - 3, T.s(9), fill=T.HOVER, outline="")
            wp_only = rec.get("kind") == "wallpaper"
            fill, ink = (T.IMAGE_FILL, T.IMAGE_INK) if wp_only else (T.ACCENT_SOFT, T.ACCENT_D)
            rr(self, T.s(20), y + T.s(12), T.s(54), y + T.s(46), T.s(9), fill=fill, outline="")
            draw_glyph(self, "wallpaper" if wp_only else "blueprint", T.s(37), y + T.s(29), ink,
                       T.s(17), width=T.s(1.6))
            title = rec.get("created") or "Saved blueprint"
            pc = rec.get("pc") or ""
            if pc and not wp_only:
                title += f"  \u00b7  {pc}"
            if wp_only:
                sub = "Wallpaper" + (f"  \u00b7  {rec.get('wallpaper_name')}" if rec.get("wallpaper_name") else "")
            else:
                bits = [f"{count(rec.get('folders', 0))} folders"]
                if rec.get("drives"):
                    bits.append(f"{rec['drives']} drive{'s' if rec['drives'] != 1 else ''}")
                if rec.get("wallpaper"):
                    bits.append("wallpaper")
                sub = "  \u00b7  ".join(bits)
            labels = (("Set" if wp_only else "Restore"), "Export", "Delete")
            x = W - T.s(22)
            positions = {}
            for lab in reversed(labels):
                w = measure(lab, 8, "bold")
                x1, x2 = x - w, x
                positions[lab] = (x1, x2)
                x = x1 - T.s(16)
            avail = max(T.s(80), positions[labels[0]][0] - T.s(76))
            self.create_text(T.s(68), y + T.s(17), text=ellipsize(title, 9, "bold", avail),
                             font=T.F(9, "bold"), fill=T.TEXT, anchor="w")
            self.create_text(T.s(68), y + T.s(35), text=middle_ellipsize(sub, 8, "normal", avail),
                             font=T.F(8), fill=T.SUB, anchor="w")
            for lab in labels:
                x1, x2 = positions[lab]
                hot = self.action_hover == (lab, id(rec))
                if lab == "Delete":
                    col = T.RED if hot else T.FAINT
                else:
                    col = T.ACCENT_D if hot else T.SUB
                self.create_text((x1 + x2) / 2, y + T.s(29), text=lab, font=T.F(8, "bold"),
                                 fill=col, anchor="center")
                self.zones.append((x1 - T.s(5), y + T.s(16), x2 + T.s(5), y + T.s(42), lab, rec))
            if i < len(self.records) - 1:
                self.create_line(T.s(68), y + row - 1, W - T.s(22), y + row - 1, fill=T.LINE)


class BlueprintPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Blueprint",
                         "The shape of your PC, ready for a new one.")
        self.import_btn = Button(self.head_right, app.motion, "Import\u2026", self._import, style="secondary",
                                 h=T.s(36), size=9, icon="plus")
        self.import_btn.pack()
        self.top = tk.Frame(self, bg=T.BG, height=T.s(310))
        self.top.pack(fill="x", padx=(T.s(40), T.s(36)), pady=(T.s(19), 0))
        self.top.pack_propagate(False)
        self.top.grid_propagate(False)
        self.top.columnconfigure(0, weight=5, uniform="bp")
        self.top.columnconfigure(1, weight=3, uniform="bp")
        self.top.rowconfigure(0, weight=1)
        self.dna_card = BlueprintCard(self.top, app.motion, self._capture, self._cancel_capture,
                                      self._restore, self._export)
        self.dna_card.grid(row=0, column=0, sticky="nsew", padx=(0, T.s(7)))
        self.wall_card = WallpaperCard(self.top, app.motion, self._save_wallpaper, self._set_wallpaper,
                                       self._toggle_include)
        self.wall_card.grid(row=0, column=1, sticky="nsew", padx=(T.s(7), 0))
        self.history = HistoryCard(self, app.motion, self._history_action)
        self.history.pack(fill="both", expand=True, padx=(T.s(40), T.s(36)), pady=(T.s(14), T.s(26)))
        self._closed = False
        self._capture_stop = None
        self._creating = False
        self._preview_token = 0

    def on_show(self):
        self.refresh()

    def refresh(self):
        if not self.winfo_exists():
            return
        records = B.list_snapshots()
        dna = next((r for r in records if (r.get("kind") or "snapshot") != "wallpaper"), None)
        latest_wall = next((r for r in records if r.get("wallpaper")), None)
        if not self._creating:
            self.dna_card.set_record(dna)
        current = B.current_wallpaper()
        self.wall_card.set_wallpaper(current, latest_wall)
        self.wall_card.set_include(bool(self.app.state.get("include_wallpaper", True)))
        self.history.set_records(records)
        self._load_preview(current)

    def _load_preview(self, current):
        if not current:
            self.wall_card.set_preview(None)
            return
        try:
            stamp = int(os.path.getmtime(current["path"]))
        except OSError:
            stamp = 0
        key = str(abs(hash((current["path"].lower(), stamp))))[-12:]
        cache = os.path.join(A.WALLPAPER_DIR, f"current-{key}.png")
        if os.path.isfile(cache):
            self.wall_card.set_preview(cache)
            return
        self._preview_token += 1
        token = self._preview_token
        path = current["path"]

        def work():
            B.make_thumbnail(path, cache, 900, 500)
            return cache if os.path.isfile(cache) else None

        def done(preview):
            if not self._closed and token == self._preview_token and preview:
                self.wall_card.set_preview(preview)

        self.app.jobs.run(work, on_done=done)

    # ---------------------------------------------------------------- capture
    def _capture(self):
        if self._creating:
            return
        self._creating = True
        self._capture_stop = threading.Event()
        include = bool(self.app.state.get("include_wallpaper", True))
        self.dna_card.set_progress(0, "Reading your drives\u2026")

        def progress(folders, current):
            self.app.post(lambda: self._capture_progress(folders, current))

        def work():
            return B.capture(progress_cb=progress, include_wallpaper=include,
                             stop_event=self._capture_stop)

        def done(record):
            self._creating = False
            self._capture_stop = None
            if not self._closed:
                if record:
                    self.refresh()
                    self.app.toast("Blueprint saved \u2014 folders and wallpaper are safe.", "good")
                else:
                    self.dna_card.set_record(None)
                    self.refresh()
                    self.app.toast("Snapshot stopped. Nothing was saved.", "warn")

        def failed(e):
            self._creating = False
            self._capture_stop = None
            if not self._closed:
                self.dna_card.set_record(None)
                self.refresh()
                self.app.toast(f"Could not save the blueprint: {e}", "error")

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _capture_progress(self, folders, current):
        if self._creating and not self._closed:
            self.dna_card.set_progress(folders, current)

    def _cancel_capture(self):
        if self._capture_stop is not None:
            self._capture_stop.set()
            self.dna_card.set_progress(self.dna_card.progress[0], "Finishing up\u2026")

    # ---------------------------------------------------------------- restore
    def _record_data(self, record):
        try:
            return B.load_snapshot(record or {})
        except Exception as e:
            self.app.toast(f"Could not read this blueprint: {e}", "error")
            return None

    def _restore(self, record):
        if not record:
            return
        data = self._record_data(record)
        if not data:
            return
        if (data.get("kind") or "snapshot") == "wallpaper":
            self._set_wallpaper(record)
            return
        plan = B.folder_plan(data)
        new = [n for _, n in plan if not os.path.isdir(n)]
        if not new:
            self.app.toast("Every folder in this blueprint already exists.", "good")
            return
        detail = f"{count(len(new))} new folders  \u00b7  {count(len(plan))} in the blueprint"
        self.app.confirm(
            f"Recreate {count(len(new))} folders?",
            "Missing folders will be created. Existing folders and files are never renamed, changed or "
            "overwritten. Your old user folders go into this PC's user folder.",
            detail=detail, confirm="Recreate folders",
            on_confirm=lambda: self._restore_now(data))

    def _restore_now(self, data):
        def work():
            return B.restore_folders(data)

        def done(result):
            created, existing = result.get("created", 0), result.get("existing", 0)
            if result.get("errors"):
                self.app.toast(f"Recreated {created} folders, {len(result['errors'])} could not be made.",
                               "warn")
            elif created:
                self.app.toast(f"Recreated {count(created)} folders. {count(existing)} already existed.", "good")
            else:
                self.app.toast("All of those folders already existed.", "good")

        def failed(e):
            self.app.toast(f"Could not recreate the folders: {e}", "error")

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _set_wallpaper(self, record):
        if not record:
            return
        wp = B.wallpaper_path(record)
        if not wp:
            self.app.toast("That blueprint doesn't include a wallpaper.", "warn")
            return
        self.app.confirm(
            "Use this wallpaper?",
            "Windows will switch to the wallpaper saved in this blueprint.",
            detail=f"Saved {record.get('created', 'earlier')}", confirm="Set wallpaper",
            on_confirm=lambda: self._apply_wallpaper(record))

    def _apply_wallpaper(self, record):
        def work():
            return B.restore_wallpaper(record)

        def done(ok):
            if ok:
                self.app.toast("Wallpaper restored.", "good")
                self.refresh()
            else:
                self.app.toast("Windows could not apply that wallpaper.", "error")

        self.app.jobs.run(work, on_done=done)

    # -------------------------------------------------------------- wallpaper
    def _save_wallpaper(self):
        def work():
            return B.save_wallpaper_copy()

        def done(record):
            if record:
                self.refresh()
                self.app.toast("Wallpaper saved with the blueprint.", "good")
            else:
                self.app.toast("Windows isn't using a wallpaper picture right now.", "warn")

        self.app.jobs.run(work, on_done=done)

    def _toggle_include(self, on):
        self.app.state.set("include_wallpaper", bool(on))

    # ------------------------------------------------------------ import/export
    def _export(self, record):
        if not record:
            return
        pc = "".join(c for c in (record.get("pc") or "PC") if c.isalnum() or c in " -_")[:24]
        name = f"ClickScope-{pc}-{time.strftime('%Y-%m-%d')}.clickdna"
        path = filedialog.asksaveasfilename(parent=self, title="Export blueprint", defaultextension=".clickdna",
                                            initialfile=name, filetypes=[("ClickScope blueprint", "*.clickdna"),
                                                                         ("All files", "*.*")])
        if not path:
            return

        def work():
            return B.export_snapshot(record, path)

        def done(out):
            self.app.toast("Blueprint exported. Keep the .clickdna file somewhere safe.", "good")

        def failed(e):
            self.app.toast(f"Could not export: {e}", "error")

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title="Import blueprint",
                                          filetypes=[("ClickScope blueprint", "*.clickdna *.json"),
                                                     ("All files", "*.*")])
        if not path:
            return

        def work():
            return B.import_snapshot(path)

        def done(record):
            self.refresh()
            self.app.toast("Blueprint imported. Restore it whenever you're ready.", "good")

        def failed(e):
            self.app.toast(f"Could not import: {e}", "error")

        self.app.jobs.run(work, on_done=done, on_error=failed)

    def _delete(self, record):
        self.app.confirm(
            "Delete this blueprint?",
            "The snapshot and its saved wallpaper will be removed from ClickScope. An exported .clickdna "
            "file is not affected.",
            detail="You can't undo this.",
            confirm="Delete blueprint", tone="danger",
            on_confirm=lambda: self._delete_now(record))

    def _delete_now(self, record):
        if B.delete_snapshot(record):
            self.refresh()
            self.app.toast("Blueprint deleted.", "good")
        else:
            self.app.toast("Could not delete that blueprint.", "error")

    def _history_action(self, action, record):
        if action == "Delete":
            self._delete(record)
        elif action == "Export":
            self._export(record)
        elif action in ("Restore", "Set"):
            if record.get("kind") == "wallpaper":
                self._set_wallpaper(record)
            else:
                self._restore(record)

    def destroy(self):
        self._closed = True
        if self._capture_stop is not None:
            self._capture_stop.set()
        super().destroy()


# ------------------------------------------------------------------- settings
class IndexCard(Card):
    def __init__(self, parent, motion, on_rebuild, on_clear):
        super().__init__(parent, motion, bg=T.BG, radius=18, height=T.s(252))
        self.motion = motion
        self.stats = {}
        self.building = False
        self.on_rebuild, self.on_clear = on_rebuild, on_clear
        self.rebuild_btn = Button(self, motion, "Rebuild index", self.on_rebuild, style="secondary",
                                  bg=T.CARD, h=T.s(36), size=9, icon="refresh")
        self.clear_btn = Button(self, motion, "Remove index", self.on_clear, style="quiet", bg=T.CARD,
                                h=T.s(36), size=9)
        self.reveal.jump(1.0)
        self.redraw()

    def set_stats(self, stats, building=False):
        self.stats, self.building = stats or {}, building
        self.redraw()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self.clear_btn.set_enabled(not self.building)
            self.rebuild_btn.set_text("View progress" if self.building else "Rebuild index")
            self.rebuild_btn.place(x=self.W - T.s(22) - self.rebuild_btn.w, y=self.H - T.s(51))
            self.clear_btn.place(x=T.s(22), y=self.H - T.s(51))

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(22)
        self.create_text(pad, T.s(20), text="Search index", font=T.F(11, "bold"), fill=T.TEXT, anchor="w")
        files = self.stats.get("files", 0)
        dirs = self.stats.get("dirs", 0)
        state = self.stats.get("state", "idle")
        if self.building or state == "scanning":
            color, label = T.ACCENT, "Indexing now"
        elif files:
            color, label = T.GREEN, "Ready"
        else:
            color, label = T.FAINT, "Not indexed"
        label_w = measure(label, 8, "bold")
        circle(self, self.W - pad - label_w - T.s(10), T.s(21), T.s(3.5), fill=color, outline="")
        self.create_text(self.W - pad, T.s(21), text=label, font=T.F(8, "bold"), fill=T.SUB, anchor="e")
        if files:
            files_text = f"{count(files)} files"
            self.text(pad, T.s(46), files_text, 20, "bold", fill=T.TEXT)
            self.create_text(pad + measure(files_text, 20, "bold") + T.s(14), T.s(59),
                             text=f"{count(dirs)} folders", font=T.F(9), fill=T.SUB, anchor="w")
            self.create_text(pad, T.s(88), text="Last indexed " + short_time(self.stats.get("last_build")),
                             font=T.F(9), fill=T.FAINT, anchor="w")
        else:
            self.text(pad, T.s(46), "Not built yet", 18, "bold", fill=T.TEXT)
            self.create_text(pad, T.s(84), text="Build a local index to search the whole PC.",
                             font=T.F(9), fill=T.FAINT, anchor="w")
        roots = self.stats.get("roots") or []
        if not roots:
            root_text = "all local drives"
        else:
            home = os.path.expanduser("~")
            shown = []
            for r in roots[:4]:
                r = "~" + r[len(home):] if home and r.lower().startswith(home.lower()) else r
                shown.append(r)
            root_text = "  ".join(shown)
        self.create_text(pad, T.s(118), text=ellipsize("Watching " + root_text, 9, "normal",
                                                       self.W - pad * 2), font=T.F(9), fill=T.SUB,
                         anchor="w")
        self.create_text(pad, T.s(138), text="Names, folders, sizes and dates are stored locally.",
                         font=T.F(8), fill=T.FAINT, anchor="w")
        self.create_line(T.s(18), self.H - T.s(70), self.W - T.s(18), self.H - T.s(70), fill=T.LINE)


class BehaviorCard(Card):
    def __init__(self, parent, motion, on_start, on_keep, start_on, keep_on):
        super().__init__(parent, motion, bg=T.BG, radius=18, height=T.s(190))
        self.motion = motion
        self.start_switch = Switch(self, motion, start_on, command=on_start, bg=T.CARD)
        self.keep_switch = Switch(self, motion, keep_on, command=on_keep, bg=T.CARD)
        self.reveal.jump(1.0)
        self.redraw()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self.start_switch.place(x=self.W - T.s(22) - self.start_switch.winfo_reqwidth(), y=T.s(58))
            self.keep_switch.place(x=self.W - T.s(22) - self.keep_switch.winfo_reqwidth(), y=T.s(118))

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(22)
        self.create_text(pad, T.s(20), text="General", font=T.F(11, "bold"), fill=T.TEXT, anchor="w")
        self._row(pad, T.s(60), "Start with Windows", "Open quietly when you sign in.")
        self.create_line(T.s(18), T.s(99), self.W - T.s(18), T.s(99), fill=T.LINE)
        self._row(pad, T.s(120), "Keep ClickScope handy", "Closing the window leaves it in the taskbar.")

    def _row(self, x, y, title, sub):
        self.create_text(x, y, text=title, font=T.F(10, "bold"), fill=T.TEXT, anchor="w")
        self.create_text(x, y + T.s(19), text=sub, font=T.F(8), fill=T.FAINT, anchor="w")


class PrivacyCard(Card):
    def __init__(self, parent, motion):
        super().__init__(parent, motion, bg=T.BG, radius=18, height=T.s(252))
        self.reveal.jump(1.0)
        self.redraw()

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(22)
        self.create_text(pad, T.s(20), text="Your data stays here", font=T.F(11, "bold"), fill=T.TEXT,
                         anchor="w")
        circle(self, pad + T.s(4), T.s(48), T.s(3.5), fill=T.GREEN, outline="")
        self.create_text(pad + T.s(14), T.s(48), text="No account. No cloud. No telemetry.",
                         font=T.F(8, "bold"), fill=T.GREEN, anchor="w")
        rows = [
            (T.ACCENT, "Indexed", "File names, folders, sizes and dates."),
            (T.IMAGE_INK, "Blueprint", "Folder names and your wallpaper picture."),
            (T.RED, "Never", "Document contents, history or passwords."),
        ]
        for i, (col, label, body) in enumerate(rows):
            y = T.s(80) + i * T.s(38)
            circle(self, pad + T.s(4), y, T.s(3), fill=col, outline="")
            self.create_text(pad + T.s(14), y, text=label, font=T.F(9, "bold"), fill=T.TEXT, anchor="w")
            self.create_text(pad + T.s(80), y, text=ellipsize(body, 8, "normal", self.W - pad - T.s(85)),
                             font=T.F(8), fill=T.SUB, anchor="w")
        self.create_line(T.s(18), self.H - T.s(62), self.W - T.s(18), self.H - T.s(62), fill=T.LINE)
        self.create_text(pad, self.H - T.s(39), text="Stored only in this Windows account:",
                         font=T.F(8), fill=T.FAINT, anchor="w")
        self.create_text(pad, self.H - T.s(24), text=ellipsize(A.APP_DIR, 8, "normal", self.W - pad * 2),
                         font=T.F(8), fill=T.SUB, anchor="w")


class AboutCard(Card):
    def __init__(self, parent, motion, on_folder, on_quit):
        super().__init__(parent, motion, bg=T.BG, radius=18, height=T.s(160))
        self.motion = motion
        self._logo = None
        try:
            self._logo = tk.PhotoImage(file=A.resource_path("assets/logo_40.png"))
        except Exception:
            pass
        self.folder_btn = Button(self, motion, "Open data folder", on_folder, style="quiet", bg=T.CARD,
                                 h=T.s(34), size=9)
        self.quit_btn = Button(self, motion, "Quit ClickScope", on_quit, style="secondary", bg=T.CARD,
                               h=T.s(34), size=9)
        self.reveal.jump(1.0)
        self.redraw()

    def redraw(self):
        super().redraw()
        if self.W >= 10:
            self.folder_btn.place(x=T.s(22), y=self.H - T.s(46))
            self.quit_btn.place(x=self.W - T.s(22) - self.quit_btn.w, y=self.H - T.s(46))

    def draw(self):
        if self.W < 10:
            return
        pad = T.s(22)
        if self._logo is not None:
            self.create_image(pad, T.s(18), image=self._logo, anchor="nw")
            tx = pad + T.s(50)
        else:
            rr(self, pad, T.s(18), pad + T.s(34), T.s(52), T.s(8), fill=T.ACCENT, outline="")
            draw_glyph(self, "search", pad + T.s(17), T.s(35), "#FFFFFF", T.s(16), width=T.s(1.8))
            tx = pad + T.s(44)
        self.create_text(tx, T.s(27), text="ClickScope", font=T.F(12, "bold"), fill=T.TEXT, anchor="w")
        self.create_text(tx, T.s(45), text=f"Version {A.VERSION}", font=T.F(8), fill=T.FAINT, anchor="w")
        self.create_text(pad, T.s(70), text="A quieter utility for the PC you use every day.",
                         font=T.F(9), fill=T.SUB, anchor="w")
        self.create_line(T.s(18), self.H - T.s(58), self.W - T.s(18), self.H - T.s(58), fill=T.LINE)


class SettingsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Settings", "A few choices, and everything stays on this PC.")
        wrap = tk.Frame(self, bg=T.BG)
        wrap.pack(fill="both", expand=True, padx=(T.s(40), T.s(36)), pady=(T.s(19), T.s(26)))
        wrap.columnconfigure(0, weight=1, uniform="set")
        wrap.columnconfigure(1, weight=1, uniform="set")
        self.index_card = IndexCard(wrap, app.motion, app.rebuild_index, app.clear_index)
        self.index_card.grid(row=0, column=0, sticky="ew", padx=(0, T.s(7)), pady=(0, T.s(14)))
        self.privacy_card = PrivacyCard(wrap, app.motion)
        self.privacy_card.grid(row=0, column=1, sticky="ew", padx=(T.s(7), 0), pady=(0, T.s(14)))
        self.behavior_card = BehaviorCard(wrap, app.motion, self._set_start, self._set_keep,
                                          app.autostart_enabled(),
                                          bool(app.state.get("keep_running", True)))
        self.behavior_card.grid(row=1, column=0, sticky="ew", padx=(0, T.s(7)))
        self.about_card = AboutCard(wrap, app.motion, self._open_folder, app.quit)
        self.about_card.grid(row=1, column=1, sticky="ew", padx=(T.s(7), 0))

    def on_show(self):
        self._refresh()
        for card in (self.index_card, self.privacy_card, self.behavior_card, self.about_card):
            card.enter()

    def _refresh(self):
        try:
            stats = self.app.index.stats(cache=False)
            building = self.app.index.is_building()
        except Exception:
            stats, building = {}, False
        self.index_card.set_stats(stats, building)

    def on_index_changed(self):
        self._refresh()

    def _set_start(self, on):
        try:
            self.app.set_autostart(on)
            self.app.state.set("autostart", bool(on))
        except Exception as e:
            self.behavior_card.start_switch.set(not on)
            self.app.toast(f"Could not change startup: {e}", "error")
            return
        self.app.toast("ClickScope will start with Windows." if on else "ClickScope won't start with Windows.",
                       "good")

    def _set_keep(self, on):
        self.app.state.set("keep_running", bool(on))
        self.app.toast("Closing the window keeps ClickScope in the taskbar." if on
                       else "Closing the window will quit ClickScope.", "good")

    def _open_folder(self):
        A.ensure_dirs()
        if not A.open_path(A.APP_DIR):
            self.app.toast("Could not open the ClickScope folder.", "error")






