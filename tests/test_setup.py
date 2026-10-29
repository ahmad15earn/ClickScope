"""Walks the whole first-run setup with a fake scanner and renders every step."""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, ui

ui.reduced_motion = lambda: True
out = "/tmp/shots"; os.makedirs(out, exist_ok=True)

class Fake:
    APPS = [("Google Chrome", "Google LLC  \u00b7  v126.0"), ("Visual Studio Code", "Microsoft  \u00b7  v1.94"), ("7-Zip", "Igor Pavlov  \u00b7  v23.01"),
            ("Adobe Photoshop 2025", "Adobe  \u00b7  v26.0"), ("Git", "The Git Development Community  \u00b7  v2.46"), ("OBS Studio", "OBS Project  \u00b7  v30.2"),
            ("Telegram Desktop", "Telegram FZ-LLC"), ("Notion", "Notion Labs"), ("Figma", "Figma, Inc."), ("VLC media player", "VideoLAN"),
            ("Backup Tool Pro", "Acme  \u00b7  v4.1"), ("Zoom", "Zoom Video Communications")] + [(f"Utility {i}", "Start Menu") for i in range(20)]
    def scan_apps(self): time.sleep(0.05); return self.APPS
    def detect_browsers(self): return [("Google Chrome", "chromium", "/c"), ("Firefox", "firefox", "/f")]
    def read_sites(self, kind, path): time.sleep(0.05); return [("youtube.com", "412 visits"), ("github.com", "301 visits"), ("mail.google.com", "250 visits"), ("notion.so", "bookmarked")]

class TR: paused = False; click_count = 0; started = False
root = tk.Tk()
store = core.Store(os.path.join(tempfile.mkdtemp(), "o.db"))
started = []
app = ui.App(root, store, TR(), on_ready=lambda: started.append(1))
root.pump(1)
app.start_setup(True, 0, scanner=Fake()); root.pump(1)
sf = app.setup
def shot(n): tkshim.render_tree(root).convert("RGB").save(f"{out}/{n}.png")
shot("s0_welcome")
sf._next(); time.sleep(0.3); root.pump(0.5); shot("s1_scanning")
root.pump(3); assert sf.step == 2, sf.step
sf.list.selected |= {"Google Chrome", "Visual Studio Code", "Backup Tool Pro"}; sf._list_changed(); shot("s2_apps")
sf.list.fire("<Key>", keysym="o", char="o"); sf.list.fire("<Key>", keysym="b", char="b"); shot("s2b_search")
sf.list.fire("<Key>", keysym="Escape", char=""); sf.list.fire("<MouseWheel>", delta=-120); root.pump(1)
sf._next(); assert sf.step == 3
sf.list.selected |= {"0"}; sf._list_changed(); sf._next(); time.sleep(0.3); root.pump(3); assert sf.step == 4, sf.step; shot("s4_sites")
sf.list.selected |= {"github.com", "notion.so"}; sf._list_changed(); sf._next(); assert sf.step == 5; shot("s5_done")
sf._next(); root.pump(1)
assert app.setup is None and started == [1]
assert set(store.kept()) == {"Google Chrome", "Visual Studio Code", "Backup Tool Pro"} and set(store.kept_sites()) == {"github.com", "notion.so"}
assert store.get("onboarded") == "1" and len(store.catalog("app")) == 32
app.show("inventory"); root.pump(1); shot("s6_inventory"); app.pages["inventory"].seg.select("site"); root.pump(1); shot("s7_inventory_sites")
print("setup flow OK")
