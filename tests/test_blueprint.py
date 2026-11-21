"""PC DNA: folder mapping, restore, export/import and snapshot safety."""
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import blueprint as B


def make_data(home, folders):
    return dict(format=B.DNA_FORMAT, version=B.DNA_VERSION, created="21 Nov 2026, 12:00",
                created_ts=int(time.time()), pc="ALEX", user="alex", home=home,
                drives=[dict(letter="C:", label="System", total=1, free=1)],
                folders=folders, folder_count=len(folders),
                wallpaper=dict(file="wallpaper.png", name="alpine.png", style="Fill", size=12))


def test_folder_mapping():
    old, new = r"C:\Users\Alex", r"C:\Users\Sam"
    assert B._map_folder(r"C:\Users\Alex", old, new, set()) == new
    assert B._map_folder(r"C:\Users\Alex\Documents\Projects", old, new, set()) == \
        os.path.join(new, "Documents", "Projects")
    assert B._map_folder(r"D:\Games\Steam", old, new, {"D:"}) == r"D:\Games\Steam"
    assert B._map_folder(r"Q:\Archive", old, new, set()) == \
        os.path.join(new, "Restored", "Q", "Archive")


def test_plan_and_restore_creates_only_folders():
    source = tempfile.mkdtemp(prefix="clickscope-dna-home-")
    target = tempfile.mkdtemp(prefix="clickscope-dna-new-")
    missing = next(ch for ch in "QWXYZ" if not os.path.isdir(ch + ":\\"))
    try:
        old_home = os.path.join(source, "Alex")
        data = make_data(old_home, [
            old_home,
            os.path.join(old_home, "Documents"),
            os.path.join(old_home, "Documents", "Projects"),
            missing + r":\Archive",
        ])
        original_drives = B.drive_info
        B.drive_info = lambda: []
        try:
            plan = B.folder_plan(data, target)
            restored = [new for _, new in plan]
            assert target in restored
            assert os.path.join(target, "Documents", "Projects") in restored
            fallback = os.path.join(target, "Restored", missing, "Archive")
            assert fallback in restored

            result = B.restore_folders(data, target)
            assert result["created"] == 3, result
            assert result["existing"] == 1, result
            assert result["errors"] == []
            assert os.path.isdir(os.path.join(target, "Documents", "Projects"))
            assert os.path.isdir(fallback)
            for _, _, files in os.walk(target):
                assert not files, "restore copied document files"
            # Existing folders are counted, never rewritten.
            again = B.restore_folders(data, target)
            assert again["created"] == 0 and again["existing"] == 4, again
        finally:
            B.drive_info = original_drives
    finally:
        shutil.rmtree(source, ignore_errors=True)
        shutil.rmtree(target, ignore_errors=True)


def test_export_import_and_delete():
    original_snapshots = B.SNAPSHOT_DIR
    temp_root = tempfile.mkdtemp(prefix="clickscope-dna-")
    B.SNAPSHOT_DIR = os.path.join(temp_root, "blueprints")
    os.makedirs(B.SNAPSHOT_DIR)
    source = os.path.join(temp_root, "source")
    os.makedirs(source)
    try:
        data = make_data(r"C:\Users\Alex", [r"C:\Users\Alex", r"C:\Users\Alex\Documents"])
        with open(os.path.join(source, "blueprint.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c6360000000020001e221bc330000000049454e44ae426082")
        with open(os.path.join(source, "wallpaper.png"), "wb") as f:
            f.write(png)
        with open(os.path.join(source, "wallpaper_preview.png"), "wb") as f:
            f.write(png)
        record = dict(dir=source, data_path=os.path.join(source, "blueprint.json"),
                      wallpaper_name="wallpaper.png")

        out = os.path.join(temp_root, "Alex.clickdna")
        B.export_snapshot(record, out)
        with zipfile.ZipFile(out) as z:
            names = set(z.namelist())
        assert {"blueprint.json", "wallpaper.png", "README.txt"} <= names, names

        imported = B.import_snapshot(out)
        assert imported["wallpaper"] is True
        assert imported["wallpaper_name"] == "alpine.png", imported
        assert os.path.isfile(os.path.join(imported["dir"], "wallpaper.png"))
        listing = B.list_snapshots()
        assert any(r["dir"] == imported["dir"] for r in listing), listing

        assert B.delete_snapshot(imported) is True
        assert not os.path.isdir(imported["dir"])
        foreign = os.path.join(temp_root, "elsewhere")
        os.makedirs(foreign)
        assert B.delete_snapshot(foreign) is False
    finally:
        B.SNAPSHOT_DIR = original_snapshots
        shutil.rmtree(temp_root, ignore_errors=True)


def test_invalid_import_leaves_no_folder():
    original_snapshots = B.SNAPSHOT_DIR
    temp_root = tempfile.mkdtemp(prefix="clickscope-dna-bad-")
    B.SNAPSHOT_DIR = os.path.join(temp_root, "blueprints")
    os.makedirs(B.SNAPSHOT_DIR)
    try:
        bad = os.path.join(temp_root, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            json.dump(dict(format="something-else"), f)
        before = set(os.listdir(B.SNAPSHOT_DIR))
        try:
            B.import_snapshot(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid blueprint was accepted")
        assert set(os.listdir(B.SNAPSHOT_DIR)) == before
    finally:
        B.SNAPSHOT_DIR = original_snapshots
        shutil.rmtree(temp_root, ignore_errors=True)


def test_stats_text():
    record = dict(folders=42180, drives=2, wallpaper=True)
    assert B.stats_text(record) == "42,180 folders  \u00b7  2 drives  \u00b7  wallpaper"
    assert B.stats_text(dict(folders=1, drives=1, wallpaper=False)) == \
        "1 folder  \u00b7  1 drive"


if __name__ == "__main__":
    test_folder_mapping()
    test_plan_and_restore_creates_only_folders()
    test_export_import_and_delete()
    test_invalid_import_leaves_no_folder()
    test_stats_text()
    print("blueprint tests OK")
