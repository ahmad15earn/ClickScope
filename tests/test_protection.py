"""Protection rules: exact items, parent folders, persistence and safe re-matching."""
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import protection as P


def make_home():
    return tempfile.mkdtemp(prefix="clickscope-protect-")


def test_add_remove_and_parent_folder():
    home = make_home()
    try:
        folder = os.path.join(home, "Documents")
        os.makedirs(folder)
        keep = os.path.join(folder, "Thesis.pdf")
        other = os.path.join(home, "notes.txt")
        with open(keep, "wb") as f:
            f.write(b"pdf")
        with open(other, "wb") as f:
            f.write(b"txt")
        store = P.Protection(path=os.path.join(home, "protection.json"))

        store.add(other)
        assert store.is_protected(other)
        assert store.is_protected(other.upper())  # Windows paths compare case-insensitively
        assert not store.is_protected(keep)

        store.add(folder)
        assert store.is_protected(keep), "a protected parent folder must cover its files"
        assert store.is_protected(os.path.join(folder, "not-created-yet.txt"))
        assert not store.is_protected(os.path.join(home, "elsewhere", "notes.txt"))
        entry = store.protected_entry_for(keep)
        assert entry["kind"] == "folder" and entry["path"] == folder

        allowed, blocked = store.filter_paths([keep, other, os.path.join(home, "free.txt")])
        assert keep in blocked and other in blocked
        assert allowed == [os.path.join(home, "free.txt")]

        store.remove(other)
        assert not store.is_protected(other)
        assert store.is_protected(keep)
        store.remove(folder)
        assert not store.is_protected(keep)
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_persists_and_survives_corruption():
    home = make_home()
    try:
        target = os.path.join(home, "keep.zip")
        with open(target, "wb") as f:
            f.write(b"zip")
        path = os.path.join(home, "protection.json")
        first = P.Protection(path=path)
        first.add(target)
        assert os.path.isfile(path + ".bak") or os.path.isfile(path)

        second = P.Protection(path=path)
        assert second.is_protected(target), "protection must survive a restart"

        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        third = P.Protection(path=path)
        assert third.recovered is True
        assert not third.list_entries()
        backups = [n for n in os.listdir(home) if n.startswith("protection.json.corrupt-")]
        assert backups, "the damaged file should be kept aside"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_refresh_only_follows_unambiguous_rename():
    home = make_home()
    try:
        old = os.path.join(home, "lecture.pdf")
        with open(old, "wb") as f:
            f.write(b"same bytes")
        stamp = int(time.time()) - 100
        os.utime(old, (stamp, stamp))
        store = P.Protection(path=os.path.join(home, "protection.json"))
        store.add(old)
        new = os.path.join(home, "lecture-final.pdf")
        os.replace(old, new)
        changed = store.refresh(index=None)
        assert len(changed) == 1, changed
        assert store.is_protected(new)
        assert not store.is_protected(old)

        # Two possible matches with the same name and size must not be guessed.
        a = os.path.join(home, "A")
        b = os.path.join(home, "B")
        c = os.path.join(home, "C")
        for folder in (a, b, c):
            os.makedirs(folder)
        original = os.path.join(a, "unique-setup.exe")
        with open(original, "wb") as f:
            f.write(b"x" * 2048)
        os.utime(original, (stamp, stamp))
        store.add(original)
        os.remove(original)
        rows = [dict(path=os.path.join(b, "unique-setup.exe")),
                dict(path=os.path.join(c, "unique-setup.exe"))]
        for row in rows:
            with open(row["path"], "wb") as f:
                f.write(b"x" * 2048)
            os.utime(row["path"], (stamp, stamp))

        class FakeIndex:
            def find_by_name(self, name, limit=40):
                return [r for r in rows if os.path.basename(r["path"]) == name]

        changed = store.refresh(index=FakeIndex())
        assert changed == [], "two candidates must leave protection untouched"
        assert store.is_protected(original), "the original entry is kept when unsure"
        assert not store.is_protected(rows[0]["path"])
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_summary_counts():
    home = make_home()
    try:
        f = os.path.join(home, "one.txt")
        d = os.path.join(home, "Folder")
        with open(f, "wb") as fh:
            fh.write(b"1")
        os.makedirs(d)
        store = P.Protection(path=os.path.join(home, "protection.json"))
        store.add(f)
        store.add(d)
        summary = store.summary()
        assert summary["total"] == 2 and summary["files"] == 1 and summary["folders"] == 1, summary
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    test_add_remove_and_parent_folder()
    test_persists_and_survives_corruption()
    test_refresh_only_follows_unambiguous_rename()
    test_summary_counts()
    print("protection tests OK")
