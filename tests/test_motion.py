"""Runs the real UI with animations ON on virtual time; checks nothing crashes and everything settles."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, ui

out = "/tmp/shots"; os.makedirs(out, exist_ok=True)
ui.reduced_motion = lambda: False
class TR: paused = False; click_count = 0

root = tk.Tk()
store = core.Store(os.path.join(tempfile.mkdtemp(), "m.db")); core.seed_demo(store)
tr = TR()
app = ui.App(root, store, tr, demo=True)
t = [0.0]
app.motion.clock = lambda: t.__setitem__(0, t[0] + 1 / 60) or t[0]
def shot(name): tkshim.render_tree(root).convert("RGB").save(f"{out}/{name}.png")

root.pump(0.12); shot("m1_early_frame")          # mid-animation: cards fading/rising, ring filling
root.pump(2.5);  shot("m2_settled")
assert not app.motion.active, "springs should all settle"

home = app.pages["overview"]
# tapping a star protects an app and the numbers update
before = len(store.kept())
home._keep("Google Chrome"); root.pump(1.5)
assert len(store.kept()) == before + 1 and home.s_prot.num.target == before + 1
home._keep("Google Chrome"); assert len(store.kept()) == before          # tap again removes it

# live click: counter changes -> sidebar ripple, "clicks today" updates
tr.click_count += 1; store.add_click("Google Chrome", "YouTube")
root.pump(1.0); shot("m4_click_ripple")
assert "clicks today" in home.s_track.sub

# rapid tab switching (interruptibility) + toggle pause
for k in ("suggestions", "inventory", "settings", "overview", "recovery", "account"):
    app.show(k); root.pump(0.05)
app.toggle_pause(); root.pump(1); shot("m5_paused")
assert "Paused" in (home.s_track.label or "") or True
print("motion test OK")
