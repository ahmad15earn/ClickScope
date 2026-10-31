"""Ghost cursor choreography, the guided tour and the Recovery page (headless)."""
import os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
from PIL import Image
import core, ui, recovery as rec
from guide import GhostCursor

out = "/tmp/shots"; os.makedirs(out, exist_ok=True)
class TR: paused = False; click_count = 0
root = tk.Tk()
store = core.Store(os.path.join(tempfile.mkdtemp(), "g.db")); core.seed_demo(store)
for n in ("VS Code", "Figma", "Slack", "Word"): store.toggle_keep(n)
app = ui.App(root, store, TR(), demo=True)
t = [0.0]
app.motion.clock = lambda: t.__setitem__(0, t[0] + 1 / 60) or t[0]
root.pump(1)
def shot(name, ghost=None):
    img = tkshim.render_tree(root).convert("RGBA")
    if ghost:
        sub = ghost.cv.render()
        px = sub.load()
        for yy in range(sub.height):
            for xx in range(sub.width):
                if px[xx, yy][:3] == (1, 2, 3):
                    px[xx, yy] = (0, 0, 0, 0)
        m = int(ghost.M * tkshim.K)
        img.paste(sub, (int(ghost.x.value * tkshim.K) - m, int(ghost.y.value * tkshim.K) - m), sub)
    img.convert("RGB").save(f"{out}/{name}.png")

# 1) independent ghost: moves by itself, example-clicks, narrates
g = GhostCursor(root, app.motion, start=(1500, 900))
clicked = []
target = lambda: (330, 400)
g.run([("say", "Click here to continue"), ("move", target), ("click", lambda: clicked.append(1)), ("wait", 0.3), ("park", target)])
root.pump(0.9); shot("g1_flying", g)
root.pump(3)
assert abs(g.x.value - 330) < 4 and abs(g.y.value - 400) < 4 and clicked == [1], (g.x.value, g.y.value, clicked)
g.press.jump(1); shot("g2_arrived", g); g.press.jump(0)
g.stop(); g.close()

# 2) guided tour clicks every tab in order
visited = []
orig = app.show
app.show = lambda k: (visited.append(k), orig(k))[1]
app.start_tour(); root.pump(45)
assert visited[:len(ui.Sidebar.ITEMS)] == [k for k, _ in ui.Sidebar.ITEMS], visited
app.show = orig; root.pump(3)

# 3) recovery page: idle, running (mixed statuses), retry
page = app.pages["recovery"]
app.show("recovery"); page.folder = r"D:\Recovery"; page.update_data(); root.pump(1); shot("r1_idle")
names = ["Google Chrome", "Visual Studio Code", "7-Zip", "Backup Tool Pro", "Zoom", "Obscure Paid App", "Figma", "Slack"]
calls = []
def runner(cmd, on_chunk=None, holder=None):
    if cmd[1] == "list": return 0, ""
    if cmd[1] == "search": return 0, "Name Id Version Match Source\n---\n"
    time.sleep(0.01); return 1, "boom"
m = rec.RecoveryManager(tempfile.mkdtemp(), names, runner=runner)
for j, (st, pr, msg) in zip(m.jobs, [(rec.DONE, 1, "Downloaded"), (rec.DONE, 1, "Downloaded"), (rec.DOWNLOADING, .62, "Downloading\u2026 62%"),
        (rec.FAILED, 0, "Failed: network error"), (rec.QUEUED, 0, "Waiting"), (rec.NOSOURCE, 0, "No automatic source found. Download it manually from the vendor."),
        (rec.QUEUED, 0, "Waiting"), (rec.QUEUED, 0, "Waiting")]):
    j.status, j.progress, j.message = st, pr, msg
page.mgr = m
page.card.redraw(); root.pump(1); shot("r2_running")
# click "Retry" on the failed row
before = m.jobs[3].status
for y1, y2, job, kind in page._actions:
    if kind == "retry":
        page.card.fire("<ButtonPress-1>", x=page.card.W - 40, y=(y1 + y2) / 2)
time.sleep(0.2); m.worker and m.worker.join(2)
assert m.jobs[3].status != before or m.jobs[3].message != "Failed: network error"
# picker
page.mgr = None; page._pick(); root.pump(2); shot("r3_picker")
page._pick_done(); assert page.chosen
print("ghost + tour + recovery OK")
