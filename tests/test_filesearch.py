"""Local search index: full build, prefix search, kind filters and updates."""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from filesearch import FileIndex


def make_tree():
    base = tempfile.mkdtemp(prefix="clickscope-fs-", dir=os.path.dirname(HERE))
    reports = os.path.join(base, "Documents", "Reports")
    pictures = os.path.join(base, "Pictures")
    downloads = os.path.join(base, "Downloads")
    for d in (reports, pictures, downloads):
        os.makedirs(d)
    files = {
        os.path.join(reports, "Annual-Report-2026.pdf"): b"x" * 4096,
        os.path.join(reports, "Report-notes.txt"): b"notes",
        os.path.join(pictures, "holiday-photo.jpg"): b"jpeg",
        os.path.join(downloads, "Setup-Tool.exe"): b"exe",
        os.path.join(downloads, "project.zip"): b"zip",
    }
    for path, body in files.items():
        with open(path, "wb") as f:
            f.write(body)
    return base


def test_build_search_and_update():
    base = make_tree()
    db = os.path.join(tempfile.mkdtemp(prefix="clickscope-db-"), "index.db")
    index = FileIndex(path=db)
    try:
        assert index.build(roots=[base]) is True
        stats = index.stats(cache=False)
        assert stats["state"] == "ready", stats
        assert stats["files"] == 5, stats
        assert stats["dirs"] >= 4, stats

        hits = index.search("report")
        names = [r["name"] for r in hits]
        assert "Annual-Report-2026.pdf" in names, names
        assert "Report-notes.txt" in names, names
        assert all("report" in (r["name"] + r["dir"]).lower() for r in hits), names
        assert hits[0]["name"].lower().startswith("report"), names

        docs = index.search("report", kind="doc")
        assert docs and all(r["kind"] == "doc" for r in docs), docs
        images = index.search("holiday", kind="image")
        assert [r["name"] for r in images] == ["holiday-photo.jpg"], images
        assert index.search("holiday", kind="video") == []

        installers = index.installer_rows()
        assert [r["name"] for r in installers] == ["Setup-Tool.exe"], installers

        new_file = os.path.join(base, "Documents", "Quarterly-Report.docx")
        with open(new_file, "wb") as f:
            f.write(b"docx")
        assert index.index_path(new_file) == 1
        assert "Quarterly-Report.docx" in [r["name"] for r in index.search("quarterly")]

        index.remove_paths([new_file])
        assert index.search("quarterly") == []

        index.clear()
        stats = index.stats(cache=False)
        assert stats["files"] == 0 and stats["dirs"] == 0 and stats["state"] == "idle", stats
        assert index.search("report") == []
    finally:
        index.close()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(os.path.dirname(db), ignore_errors=True)


def test_tiny_query_falls_back_to_substring():
    base = make_tree()
    db = os.path.join(tempfile.mkdtemp(prefix="clickscope-db-"), "index.db")
    index = FileIndex(path=db)
    try:
        index.build(roots=[base])
        # One-character queries are not sent to FTS5, but still match names.
        assert any(r["name"] == "Report-notes.txt" for r in index.search("o"))
    finally:
        index.close()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(os.path.dirname(db), ignore_errors=True)


def test_filters_scopes_and_dates():
    base = make_tree()
    db = os.path.join(tempfile.mkdtemp(prefix="clickscope-db-"), "index.db")
    index = FileIndex(path=db)
    try:
        reports = os.path.join(base, "Documents", "Reports")
        pictures = os.path.join(base, "Pictures")
        now = time.time()
        old = os.path.join(reports, "Annual-Report-2026.pdf")
        os.utime(old, (now - 500 * 86400, now - 500 * 86400))
        fresh = os.path.join(pictures, "holiday-photo.jpg")
        os.utime(fresh, (now - 2 * 86400, now - 2 * 86400))
        big = os.path.join(base, "Documents", "big-report.zip")
        with open(big, "wb") as f:
            f.write(b"z" * 3000)
        index.build(roots=[base])

        scoped = index.search("report", scope=reports)
        assert scoped and all(os.path.normcase(r["path"]).startswith(os.path.normcase(reports)) for r in scoped)

        assert index.search("report", scope=pictures) == []
        assert index.search("", scope=reports), "browsing a folder with no query should list its files"

        small = index.search("report", max_size=100)
        assert [r["name"] for r in small] == ["Report-notes.txt"], small
        large = index.search("report", min_size=1000)
        assert {r["name"] for r in large} == {"Annual-Report-2026.pdf", "big-report.zip"}, large

        recent = index.search("report", min_mtime=int(now - 30 * 86400))
        assert "Annual-Report-2026.pdf" not in [r["name"] for r in recent], recent
        old_only = index.search("report", max_mtime=int(now - 400 * 86400))
        assert [r["name"] for r in old_only] == ["Annual-Report-2026.pdf"], old_only
    finally:
        index.close()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(os.path.dirname(db), ignore_errors=True)


def test_roots_survive_disconnect_and_reconnect():
    base = make_tree()
    second = tempfile.mkdtemp(prefix="clickscope-second-root-")
    os.makedirs(os.path.join(second, "Docs"), exist_ok=True)
    with open(os.path.join(second, "Docs", "still-here.txt"), "wb") as f:
        f.write(b"keep")
    db = os.path.join(tempfile.mkdtemp(prefix="clickscope-db-"), "index.db")
    index = FileIndex(path=db)
    try:
        index.build(roots=[base, second])
        assert os.path.abspath(base) in [os.path.abspath(r) for r in index.stats(cache=False)["roots"]]

        shutil.rmtree(base, ignore_errors=True)
        result = index.sync_roots()
        assert os.path.abspath(base) in [os.path.abspath(r) for r in result["missing"]], result
        assert index.stats(cache=False)["files"] == 1, "only rows for a missing drive are pruned"

        os.makedirs(os.path.join(base, "Docs"))
        with open(os.path.join(base, "Docs", "reconnected.txt"), "wb") as f:
            f.write(b"back")
        result = index.sync_roots()
        assert os.path.abspath(base) in [os.path.abspath(r) for r in result["added"]], result
        assert os.path.abspath(base) in [os.path.abspath(r) for r in
                                         index.stats(cache=False)["offline_roots"]], \
            "a reconnected drive stays pending until its scan finishes"

        index.build(roots=[base], reset=False, preserve_roots=True)
        assert "reconnected.txt" in [r["name"] for r in index.search("reconnected")]
        assert "still-here.txt" in [r["name"] for r in index.search("still-here")], \
            "an incremental reconnect scan must keep the rest of the index"
        stats = index.stats(cache=False)
        assert not [r for r in stats["offline_roots"] if os.path.abspath(r) == os.path.abspath(base)]
        assert {os.path.abspath(r) for r in stats["roots"]} >= {os.path.abspath(base),
                                                                os.path.abspath(second)}
    finally:
        index.close()
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(second, ignore_errors=True)
        shutil.rmtree(os.path.dirname(db), ignore_errors=True)


def test_corrupt_index_is_rebuilt_without_losing_the_old_file():
    base = make_tree()
    home = tempfile.mkdtemp(prefix="clickscope-bad-db-")
    db = os.path.join(home, "index.db")
    try:
        with open(db, "wb") as f:
            f.write(b"this is definitely not sqlite" * 200)
        index = FileIndex(path=db)
        try:
            assert index.recovered is True
            assert index.corrupt_backup and os.path.isfile(index.corrupt_backup)
            assert index.build(roots=[base]) is True
            assert index.search("report"), "the rebuilt index must be usable"
        finally:
            index.close()
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    test_build_search_and_update()
    test_tiny_query_falls_back_to_substring()
    test_filters_scopes_and_dates()
    test_roots_survive_disconnect_and_reconnect()
    test_corrupt_index_is_rebuilt_without_losing_the_old_file()
    print("filesearch tests OK")
