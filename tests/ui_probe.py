"""Development probe: build every page off-screen, exercise the wires, quit.

Run with a display available:
    python tests/ui_probe.py
It uses a synthetic home so no real folder is scanned.
"""
import os
import shutil
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
base = tempfile.mkdtemp(prefix="clickscope-ui-")
home = os.path.join(base, "home")
user = os.path.join(base, "user")
for d in (home, user):
    os.makedirs(d, exist_ok=True)
for sub in ("Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos"):
    os.makedirs(os.path.join(user, sub), exist_ok=True)
os.environ["CLICKSCOPE_HOME"] = home
os.environ["USERPROFILE"] = user
os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(user)
os.environ["OneDrive"] = ""
sys.path.insert(0, os.path.join(ROOT, "src"))

import appdata as A
import theme as T
import ui
from filesearch import FileIndex

errors = []


def main():
    root = None
    index = None
    try:
        A.ensure_dirs()
        root = ui.tk.Tk()
        root.withdraw()
        T.init(root)
        root.geometry("1200x820")
        index = FileIndex(path=os.path.join(A.APP_DIR, "index.db"))
        state = A.State(path=os.path.join(A.APP_DIR, "state.json"))
        app = ui.App(root, state, index)
        app.notifications.set_windows(False)
        root.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
        root.deiconify()
        for _ in range(4):
            root.update()

        # Build a tiny index and search it.
        with open(os.path.join(user, "Documents", "probe-report.pdf"), "wb") as f:
            f.write(b"x" * 4096)
        index.build(roots=[user])
        app.show("search")
        app.search._typed("report")
        root.update()
        time.sleep(0.4)
        root.update()
        assert app.search.results.results, "search produced no rows"
        probe_path = app.search.results.results[0]["path"]
        app.search._protect(app.search.results.results[0])
        root.update()
        assert app.protection.is_protected(probe_path), "protect action from search failed"
        app.search._unprotect_now(app.protection.get(probe_path))
        root.update()
        assert not app.protection.is_protected(probe_path), "unprotect action from search failed"

        # Protection page + a protected file.
        app.show("protection")
        root.update()
        app.protection.add(os.path.join(user, "Documents", "probe-report.pdf"))
        app.protection_page.refresh()
        root.update()

        # Website memory + the add/edit dialog.
        app.show("websites")
        root.update()
        app.websites.add("Probe site", "probe.example.com", "Tools")
        app.websites_page.refresh()
        root.update()
        app.websites_page._dialog(None)
        root.update()
        dlg = app.websites_page.dialog
        assert dlg is not None, "add dialog did not open"
        dlg.name.insert(0, "Dialog site")
        dlg.url.insert(0, "dialog.example.com")
        dlg.cat.selected = "Study"
        dlg._save()
        time.sleep(0.15)
        root.update()
        assert any(i["name"] == "Dialog site" for i in app.websites.all()), "dialog save failed"

        # Search filters change the query arguments without breaking results.
        app.show("search")
        app.search._set_size("small")
        app.search._typed("report")
        root.update()
        time.sleep(0.3)
        root.update()
        app.search._set_date("old")
        app.search._set_scope("any")
        root.update()

        # Installers, blueprint and settings pages.
        app.show("installers")
        root.update()
        time.sleep(0.4)
        root.update()
        app.show("blueprint")
        root.update()
        app.show("settings")
        root.update()
        app.settings._set_notifications(False)
        app.settings._set_notifications(True)
        app.settings._set_notification_type("index", False)
        app.settings._set_notification_type("index", True)
        root.update()

        # A verified backup in the temporary home.
        backup = os.path.join(base, "backup.zip")
        A.backup_data(backup)
        assert os.path.isfile(backup)

        # Notification history, panel click-through and target opening.
        app.notifications.set_windows(False)
        app.notify("index", "Probe notification", "Everything is wired.", "settings")
        root.update()
        app.toggle_notifications()
        root.update()
        latest = app.notifications.recent(1)[0]
        app.open_notification(latest)
        root.update()
        assert app.current == "settings", app.current
        app.toggle_notifications()
        root.update()
        app.toggle_notifications()
        root.update()

        # Protocol-style page opening.
        for target in ("clickscope:websites", "clickscope:protection", "clickscope:settings"):
            app.open_target(target)
            root.update()

        # External drive stand-in: disconnect prunes, reconnect indexes only it.
        drive = os.path.join(base, "removable")
        os.makedirs(os.path.join(drive, "Docs"), exist_ok=True)
        with open(os.path.join(drive, "Docs", "driveback.txt"), "wb") as f:
            f.write(b"drive")
        index.build(roots=[user, drive])
        shutil.rmtree(drive, ignore_errors=True)
        app._sync_drives()
        root.update()
        assert not index.search("driveback"), "rows from a missing drive must be pruned"
        os.makedirs(os.path.join(drive, "Docs"), exist_ok=True)
        with open(os.path.join(drive, "Docs", "driveback.txt"), "wb") as f:
            f.write(b"back")
        app._sync_drives()
        deadline = time.time() + 10
        while index.is_building() and time.time() < deadline:
            root.update()
            time.sleep(0.05)
        root.update()
        assert not index.is_building(), "the reconnected drive scan did not finish"
        assert index.search("driveback"), "the reconnected drive was not indexed again"

        app.quit()
    except Exception:
        errors.append(traceback.format_exc())
    finally:
        try:
            if index is not None:
                index.close()
        except Exception:
            pass
        try:
            if root is not None:
                root.destroy()
        except Exception:
            pass
        shutil.rmtree(base, ignore_errors=True)

    if errors:
        print("UI PROBE FAILED")
        for e in errors:
            print(e)
        return 1
    print("UI probe OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
