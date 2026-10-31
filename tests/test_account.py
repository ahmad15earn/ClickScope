"""Account page + restore-on-new-PC flow through the real UI (fake Supabase, simulated browser)."""
import json, os, sys, tempfile, threading, time, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "src")]
os.environ["CLICKSCOPE_DEBUG"] = "1"
import tkshim
tkshim.install()
import tkinter as tk
import core, cloud, cloud_config, ui
ui.reduced_motion = lambda: True
exec(open(os.path.join(HERE, "test_cloud.py")).read().split("v, ch = cloud.pkce_pair()")[0].split("import core, cloud, cloud_config")[1])  # fake server + config
out = "/tmp/shots"

def browser(url):
    redirect = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["redirect_to"][0]
    threading.Thread(target=lambda: (time.sleep(0.2), urllib.request.urlopen(redirect + "?code=abc").read()), daemon=True).start()
cloud.webbrowser.open = browser
class TR: paused = False; click_count = 0
def new_app(seed):
    root = tk.Tk(); st = core.Store(os.path.join(tempfile.mkdtemp(), "a.db"))
    if seed:
        st.set_catalog("app", [("Chrome", "Google"), ("7-Zip", "Igor Pavlov"), ("Backup Pro", "Acme")]); st.toggle_keep("7-Zip"); st.toggle_keep("Backup Pro")
        st.set_catalog("site", [("github.com", "301 visits")]); st.toggle_keep_site("github.com")
    app = ui.App(root, st, TR()); root.pump(1); return root, st, app
def shot(root, n): tkshim.render_tree(root).convert("RGB").save(f"{out}/{n}.png")
def wait(root, page):
    for _ in range(60):
        time.sleep(0.1); root.pump(0.2)
        if not page.busy: return
    raise AssertionError("timeout")

# old PC: sign in from the Account tab -> merges and uploads
root, st, app = new_app(True)
app.show("account"); root.pump(1); shot(root, "a1_signed_out")
pg = app.pages["account"]; pg.e_mail.insert(0, "stu@mail.com"); pg.e_pass.insert(0, "secret123"); shot(root, "a1b_form_filled")
pg._email_auth(True); shot(root, "a2_waiting"); wait(root, pg)
assert cloud.signed_in(st) and not pg.err, pg.msg
shot(root, "a3_signed_in")
assert len(DB["items"]) == 4, DB["items"]

# brand-new PC: welcome step -> Restore with Google -> lands on Recovery with everything back
root2, st2, app2 = new_app(False)
app2.start_setup(True, 0); root2.pump(1)
sf = app2.setup; assert sf.restore_btn.mapped
sf._restore(); root2.pump(1)
assert app2.setup is None and app2.tab == "account", app2.tab
pg2 = app2.pages["account"]; pg2.e_mail.insert(0, "stu@mail.com"); pg2.e_pass.insert(0, "secret123"); pg2._email_auth(False); wait(root2, pg2)
assert not pg2.err, pg2.msg
assert app2.tab == "recovery", app2.tab
assert set(st2.kept()) == {"7-Zip", "Backup Pro"} and st2.kept_sites() == ["github.com"]
shot(root2, "a4_restored_recovery")
# not configured -> friendly message, no crash
cloud_config.SUPABASE_URL = ""
root3, st3, app3 = new_app(False); app3.show("account"); root3.pump(1); shot(root3, "a5_not_configured")
print("account flow OK")
