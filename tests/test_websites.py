"""Website Memory: duplicate detection, search, JSON transfer and Firefox import."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import websites as W


def make_memory():
    home = tempfile.mkdtemp(prefix="clickscope-web-")
    return home, W.WebsiteMemory(path=os.path.join(home, "websites.json"))


def test_duplicate_url_normalization():
    home, mem = make_memory()
    try:
        added, existing = mem.add("Example", "example.com")
        assert added and existing is None
        added2, existing2 = mem.add("Example again", "https://www.Example.com/")
        assert added2 is None and existing2 and existing2["id"] == added["id"]
        added3, existing3 = mem.add("Other path", "http://example.com/Path/")
        assert added3, "a different path is a different website"
        assert existing3 is None
        assert W.normalize_url("https://WWW.Example.com") == "https://example.com/"
        assert W.normalize_url("ftp://example.com") == ""
        assert W.valid_url("https://example.com")
        assert not W.valid_url("")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_validation_search_and_update():
    home, mem = make_memory()
    try:
        mem.add("Docs", "docs.example.com/guide", "Work")
        mem.add("Photos", "photos.example.com", "Fun")
        mem.add("Notes", "notes.example.com", "Study")
        try:
            mem.add("Bad", "", "Work")
            raise AssertionError("empty URL should be rejected")
        except ValueError:
            pass
        assert [i["name"] for i in mem.search("example")] == ["Docs", "Notes", "Photos"]
        assert [i["name"] for i in mem.search("guide")] == ["Docs"]
        assert [i["name"] for i in mem.search("", "Fun")] == ["Photos"]
        cats = {key for key, _, _ in mem.categories()}
        assert {"All", "Work", "Fun", "Study"} <= cats

        item = mem.search("Docs")[0]
        mem.update(item["id"], name="Documentation", url="docs.example.com/new", category="Reading")
        changed = mem.search("Documentation")[0]
        assert changed["category"] == "Reading"
        try:
            mem.update(changed["id"], url="photos.example.com")
            raise AssertionError("moving a duplicate URL must fail")
        except ValueError:
            pass
        assert mem.delete(changed["id"])
        assert not mem.search("Documentation")
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_export_import_roundtrip():
    home, mem = make_memory()
    try:
        mem.add("One", "one.example.com", "Work")
        mem.add("Two", "two.example.com", "Fun")
        out = os.path.join(home, "sites.json")
        assert mem.export_json(out) == 2

        other_home, other = make_memory()
        try:
            result = other.import_json(out)
            assert result["added"] == 2 and result["skipped"] == 0, result
            # Importing again is safe and duplicate-aware.
            again = other.import_json(out)
            assert again["added"] == 0 and again["skipped"] == 2, again
            assert [i["name"] for i in other.all()] == ["One", "Two"]
        finally:
            shutil.rmtree(other_home, ignore_errors=True)

        bad = os.path.join(home, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump(dict(format="something-else", items=[]), f)
        try:
            other = W.WebsiteMemory(path=os.path.join(home, "x.json"))
            other.import_json(bad)
            raise AssertionError("a foreign JSON file must be rejected")
        except ValueError:
            pass
    finally:
        shutil.rmtree(home, ignore_errors=True)


def make_places(path):
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT)")
        con.execute("CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER, "
                    "parent INTEGER, title TEXT, dateAdded INTEGER)")
        con.execute("INSERT INTO moz_places (id, url) VALUES (10, 'https://docs.example.com/guide')")
        con.execute("INSERT INTO moz_places (id, url) VALUES (11, 'javascript:void(0)')")
        con.execute("INSERT INTO moz_bookmarks (id, type, parent, title) VALUES (1, 2, 0, 'Work')")
        con.execute("INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) "
                    "VALUES (2, 1, 10, 1, 'Team guide', 1700000000000000)")
        con.execute("INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) "
                    "VALUES (3, 1, 11, 1, 'Script link', 1700000000000000)")
        con.commit()
    finally:
        con.close()


def test_firefox_import():
    home, mem = make_memory()
    try:
        db = os.path.join(home, "places.sqlite")
        make_places(db)
        result = mem.import_firefox([db])
        assert result["added"] == 1, result
        assert result["skipped"] == 0, result
        item = mem.all()[0]
        assert item["name"] == "Team guide" and item["url"] == "https://docs.example.com/guide"
        assert item["category"] == "Work"
        assert item["added"] < 10_000_000_000, "Firefox microseconds must become seconds"
        # The temporary copy is removed; the source database is untouched.
        assert os.path.isfile(db)
        again = mem.import_firefox([db])
        assert again["added"] == 0 and again["skipped"] == 1, again
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    test_duplicate_url_normalization()
    test_validation_search_and_update()
    test_export_import_roundtrip()
    test_firefox_import()
    print("websites tests OK")
