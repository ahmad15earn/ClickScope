"""Local storage: settings persistence, custom location, verified backup, open requests."""
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import appdata as A


def test_state_survives_restart():
    home = tempfile.mkdtemp(prefix="clickscope-state-")
    try:
        path = os.path.join(home, "state.json")
        state = A.State(path=path)
        state.set("keep_running", False)
        state.set("windows_notifications", False)
        state.set("search_scope", "C:\\\\")
        state.ignore_installer(r"C:\Users\Alex\Downloads\Old.exe")
        again = A.State(path=path)
        assert again.get("keep_running") is False
        assert again.get("windows_notifications") is False
        assert again.get("search_scope") == "C:\\\\"
        assert r"C:\Users\Alex\Downloads\Old.exe".lower() in again.ignored_installers()
        with open(path, encoding="utf-8") as f:
            json.load(f)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_relocate_copies_data_and_remembers_location():
    home = tempfile.mkdtemp(prefix="clickscope-move-")
    original = (A.APP_DIR, A.DEFAULT_APP_DIR, A.LOCATION_FILE)
    source = os.path.join(home, "old")
    default = os.path.join(home, "default")
    target = os.path.join(home, "new")
    os.makedirs(os.path.join(source, "blueprints", "snap"), exist_ok=True)
    os.makedirs(os.path.join(source, "wallpapers"), exist_ok=True)
    os.makedirs(default, exist_ok=True)
    for name in ("state.json", "protection.json", "websites.json", "notifications.json"):
        with open(os.path.join(source, name), "w", encoding="utf-8") as f:
            f.write("{}")
    with open(os.path.join(source, "index.db"), "wb") as f:
        f.write(b"index")
    with open(os.path.join(source, "blueprints", "snap", "blueprint.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    with open(os.path.join(source, "wallpapers", "wall.png"), "wb") as f:
        f.write(b"png")
    A.APP_DIR, A.DEFAULT_APP_DIR = source, default
    A.LOCATION_FILE = os.path.join(default, "location.txt")
    try:
        result = A.relocate_storage(target)
        assert result["ok"], result
        assert os.path.isfile(os.path.join(target, "state.json"))
        assert os.path.isfile(os.path.join(target, "blueprints", "snap", "blueprint.json"))
        assert os.path.isfile(os.path.join(target, "wallpapers", "wall.png"))
        assert not os.path.exists(os.path.join(target, "index.db")), "the rebuildable index is not copied"
        with open(A.LOCATION_FILE, encoding="utf-8") as f:
            assert f.read().strip() == os.path.abspath(target)
        # Nothing in the old folder is deleted.
        assert os.path.isfile(os.path.join(source, "state.json"))

        bad = A.relocate_storage(source)
        assert not bad["ok"], "moving into the current folder must be refused"
        assert A.reset_storage_location() is True
        assert not os.path.isfile(A.LOCATION_FILE)
        assert os.path.isfile(os.path.join(target, "state.json")), "reset never deletes copied data"
    finally:
        A.APP_DIR, A.DEFAULT_APP_DIR, A.LOCATION_FILE = original
        shutil.rmtree(home, ignore_errors=True)


def test_backup_is_verified_and_excludes_index():
    home = tempfile.mkdtemp(prefix="clickscope-backup-")
    original = A.APP_DIR
    try:
        A.APP_DIR = home
        for name in ("state.json", "protection.json", "websites.json", "notifications.json"):
            with open(os.path.join(home, name), "w", encoding="utf-8") as f:
                f.write("{}")
        os.makedirs(os.path.join(home, "blueprints", "one"))
        with open(os.path.join(home, "blueprints", "one", "blueprint.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(home, "index.db"), "wb") as f:
            f.write(b"x" * 1024)
        out = os.path.join(home, "backup.zip")
        result = A.backup_data(out)
        assert result["files"] >= 5 and result["size"] > 0
        with zipfile.ZipFile(out) as z:
            assert z.testzip() is None
            names = set(z.namelist())
        assert "backup.json" in names
        assert "state.json" in names and "blueprints/one/blueprint.json" in names
        assert "index.db" not in names, "the rebuildable index should stay out of backups"
        try:
            A.backup_data("")
            raise AssertionError("an empty destination must fail")
        except ValueError:
            pass
    finally:
        A.APP_DIR = original
        shutil.rmtree(home, ignore_errors=True)


def test_open_request_is_consumed_once():
    home = tempfile.mkdtemp(prefix="clickscope-open-")
    original = A.APP_DIR
    try:
        A.APP_DIR = home
        assert A.take_open_request() == ""
        assert A.write_open_request("websites")
        assert A.take_open_request() == "websites"
        assert A.take_open_request() == ""
    finally:
        A.APP_DIR = original
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    test_state_survives_restart()
    test_relocate_copies_data_and_remembers_location()
    test_backup_is_verified_and_excludes_index()
    test_open_request_is_consumed_once()
    print("appdata tests OK")
