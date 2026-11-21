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
    base = tempfile.mkdtemp(prefix="clickscope-fs-")
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


if __name__ == "__main__":
    test_build_search_and_update()
    test_tiny_query_falls_back_to_substring()
    print("filesearch tests OK")
