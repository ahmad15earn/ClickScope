"""Notifications: quiet history, type settings, caps and never touching files."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import notifications as N


def make_store():
    home = tempfile.mkdtemp(prefix="clickscope-notify-")
    return home, N.Notifications(path=os.path.join(home, "notifications.json"), windows=False)


def test_emit_and_settings():
    home, store = make_store()
    try:
        item = store.emit("index", "Index ready", "10 files", "search")
        assert item and item["title"] == "Index ready"
        assert store.unread_count() == 1
        assert store.recent()[0]["id"] == item["id"]

        store.set_type("index", False)
        assert store.emit("index", "Should not appear") is None
        assert store.unread_count() == 1

        store.set_enabled(False)
        assert store.emit("errors", "Nope") is None
        store.set_enabled(True)
        store.set_type("index", True)

        store.mark_read(item["id"])
        assert store.unread_count() == 0
        assert all(i["read"] for i in store.recent())

        store.emit("websites", "Website added", "example.com", "websites")
        assert store.unread_count() == 1
        settings = store.settings()
        assert settings["enabled"] is True and settings["windows"] is False
        assert set(settings["types"]) == set(N.TYPE_KEYS)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_persist_and_clear():
    home, store = make_store()
    try:
        store.emit("protection", "Protected", "thesis.pdf kept out", "protection")
        path = store.path
        again = N.Notifications(path=path, windows=False)
        assert again.unread_count() == 1
        assert again.recent()[0]["title"] == "Protected"
        again.clear()
        assert again.recent() == []
        empty = N.Notifications(path=path, windows=False)
        assert empty.recent() == []
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_history_is_capped():
    home, store = make_store()
    try:
        for i in range(140):
            store.emit("index", f"Event {i}")
        assert len(store.recent(limit=500)) == 120
        assert store.recent(limit=1)[0]["title"] == "Event 139"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_corrupt_history_is_preserved():
    home, store = make_store()
    try:
        with open(store.path, "w", encoding="utf-8") as f:
            f.write("{broken")
        again = N.Notifications(path=store.path, windows=False)
        assert again.recent() == []
        assert [n for n in os.listdir(home) if n.startswith("notifications.json.corrupt-")]
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_notifications_never_move_files():
    home, store = make_store()
    try:
        victim = os.path.join(home, "important.pdf")
        with open(victim, "wb") as f:
            f.write(b"keep me")
        store.emit("installers", "Old installers found", "1 file", "installers")
        store.emit("duplicates", "Duplicate", "1 copy", "installers")
        assert os.path.isfile(victim)
        assert open(victim, "rb").read() == b"keep me"
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    test_emit_and_settings()
    test_persist_and_clear()
    test_history_is_capped()
    test_corrupt_history_is_preserved()
    test_notifications_never_move_files()
    print("notifications tests OK")
