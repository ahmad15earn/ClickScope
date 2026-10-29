"""Render every screen of the real UI to PNGs (headless).  python tests/render.py [outdir] [--live]"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, ui

out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "/tmp/shots"
os.makedirs(out, exist_ok=True)
ui.reduced_motion = lambda: True          # snap to final state for screenshots

class TR:
    paused = False
    click_count = 0

def make(demo=True, seed=True):
    root = tk.Tk()
    store = core.Store(os.path.join(tempfile.mkdtemp(), "s.db"))
    if seed:
        core.seed_demo(store)
    app = ui.App(root, store, TR(), demo=demo)
    root.pump(3)
    return root, store, app

def shot(root, name):
    tkshim.render_tree(root).convert("RGB").resize((root.w, root.h)).save(f"{out}/{name}.png")

if __name__ == "__main__":
    root, store, app = make()
    shot(root, "1_overview_30d")
    app.set_range("today"); app.seg.select("today", silent=True); root.pump(1); shot(root, "1b_overview_today")
    app.set_range("30d"); app.seg.select("30d", silent=True)
    app.show("graphs"); root.pump(2); shot(root, "2_graphs")
    app.show("suggestions"); root.pump(2); shot(root, "3_suggestions_ready")
    app.show("settings"); root.pump(2); shot(root, "4_settings")
    # fresh install: day 4 of the 30-day learning window, a bit of data
    root2, store2, app2 = make(demo=False, seed=False)
    import datetime
    store2.set("first_run", (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y-%m-%d"))
    for _ in range(214): store2.add_click("Google Chrome", "YouTube")
    for _ in range(90): store2.add_click("VS Code")
    app2.show("suggestions"); root2.pump(3); shot(root2, "5_suggestions_learning")
    app2.show("overview"); root2.pump(3); shot(root2, "6_overview_fresh")
    print("rendered to", out)
