"""Render the main screens of the real UI to PNGs (headless).  python tests/render.py [outdir]"""
import os, sys, tempfile, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, ui

out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
os.makedirs(out, exist_ok=True)
ui.reduced_motion = lambda: True

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
    shot(root, "1_home")
    app.show("suggestions"); root.pump(2); shot(root, "2_insights")
    app.show("settings"); root.pump(2); shot(root, "3_settings")
    app.show("inventory"); root.pump(2); shot(root, "4_inventory")
    # a fresh install: nothing done yet, day 4 of the 30-day learning window
    root2, store2, app2 = make(demo=False, seed=False)
    store2.set("first_run", (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y-%m-%d"))
    for _ in range(214): store2.add_click("Google Chrome", "YouTube")
    for _ in range(90): store2.add_click("VS Code")
    for _ in range(40): store2.add_click("Figma")
    app2.show("overview"); root2.pump(3); shot(root2, "5_home_fresh")
    app2.show("suggestions"); root2.pump(3); shot(root2, "6_insights_learning")
    # welcome step with the privacy promise
    root3, store3, app3 = make(demo=False, seed=False)
    import cloud_config; cloud_config.SUPABASE_URL = ""
    app3.start_setup(True, 0); root3.pump(1); shot(root3, "7_welcome")
    print("rendered to", out)
