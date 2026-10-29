"""Runs the real UI with animations ON on virtual time; checks nothing crashes and looks right mid-flight."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, ui, motion

out = "/tmp/shots"; os.makedirs(out, exist_ok=True)
ui.reduced_motion = lambda: False
class TR: paused = False; click_count = 0

root = tk.Tk()
store = core.Store(os.path.join(tempfile.mkdtemp(), "m.db")); core.seed_demo(store)
tr = TR()
app = ui.App(root, store, tr, demo=True)
# virtual 60fps clock for springs
t = [0.0]
app.motion.clock = lambda: t.__setitem__(0, t[0] + 1 / 60) or t[0]

def shot(name): tkshim.render_tree(root).convert("RGB").save(f"{out}/{name}.png")

root.pump(0.12); shot("m1_early_frame")          # mid-animation: content still fading/rising, bars growing
root.pump(2.5);  shot("m2_settled")
assert not app.motion.active, "springs should all settle"

# hover tooltip on the activity chart
ch = app.pages["overview"].chart
ch.fire("<Motion>", x=ch.W * 0.6, y=ch.H * 0.6); shot("m3_hover_area")
assert ch.hover is not None
ch.fire("<Leave>")

# live click: counter changes -> sidebar ripple + number count-up, no crash
app.set_range("today"); app.seg.select("today", silent=True); root.pump(1)
before = app.pages["overview"].s_total.num.target
store.add_click("Google Chrome", "YouTube"); tr.click_count += 1
root.pump(0.3); shot("m4_click_ripple"); root.pump(1.5)
assert app.pages["overview"].s_total.num.target == before + 1, "total should update live"

# rapid tab switching (interruptibility) + toggle pause
for k in ("graphs", "suggestions", "settings", "overview", "graphs"):
    app.show(k); root.pump(0.05)
app.toggle_pause(); root.pump(1); shot("m5_paused")
app.pages["graphs"].donut.seg.select("site"); root.pump(2); shot("m6_graphs_sites")
print("motion test OK")
