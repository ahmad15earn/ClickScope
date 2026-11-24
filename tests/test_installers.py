"""Installer heuristics: old setup files, duplicate versions, safe picks."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

import installers as I

NOW = 1_800_000_000


class FakeIndex:
    def __init__(self, rows):
        self.rows = rows

    def has_data(self):
        return bool(self.rows)

    def installer_rows(self):
        return [dict(path=p, size=s, mtime=m) for p, s, m in self.rows]


def row(path, size, age_days):
    return path, size, int(NOW - age_days * 86400)


def test_name_heuristics():
    assert I.looks_like_installer("AppSetup.exe", r"C:\Users\Alex\Downloads\AppSetup.exe", 2_000_000,
                                  skip_system=False)
    assert I.looks_like_installer("PhotoStudio_2024.1_win64.exe",
                                  r"C:\Users\Alex\Downloads\PhotoStudio_2024.1_win64.exe", 2_000_000,
                                  skip_system=False)
    assert I.looks_like_installer("driver.msi", r"C:\Users\Alex\Downloads\driver.msi", 100,
                                  skip_system=False)
    assert not I.looks_like_installer("unins000.exe", r"C:\Users\Alex\Downloads\unins000.exe", 2_000_000,
                                      skip_system=False)
    assert not I.looks_like_installer("holiday.jpg", r"C:\Users\Alex\Pictures\holiday.jpg", 2_000_000,
                                      skip_system=False)
    assert not I.looks_like_installer("random-tool.exe", r"C:\Users\Alex\Downloads\random-tool.exe",
                                      2_000_000, skip_system=False)
    assert not I.looks_like_installer("AppSetup.exe", r"C:\Program Files\App\AppSetup.exe", 2_000_000)
    assert I.looks_like_installer("AppSetup.exe", r"C:\Program Files\App\AppSetup.exe", 2_000_000,
                                  skip_system=False)


def test_normalize_name():
    a = I.normalize_name("PhotoStudio_2024.1_win64.exe")
    b = I.normalize_name("PhotoStudio_2023.2_win64.exe")
    assert a == b == "photostudio", (a, b)
    assert I.normalize_name("App Setup v1.3.exe") == I.normalize_name("App Setup v1.2.exe") == "app"


def test_find_duplicates_and_safe_picks():
    rows = [
        row(r"C:\Users\Alex\Downloads\Installers\PhotoStudio_2024.1_win64.exe", 700_000_000, 400),
        row(r"C:\Users\Alex\Downloads\Installers\PhotoStudio_2023.2_win64.exe", 710_000_000, 700),
        row(r"C:\Users\Alex\Desktop\OldGameSetup.exe", 1_800_000_000, 760),
        row(r"C:\Users\Alex\Downloads\unins000.exe", 2_000_000, 900),
        row(r"C:\Users\Alex\Downloads\random-tool.exe", 1_000_000, 500),
        row(r"C:\Users\Alex\Downloads\AppSetup_1.0_x64.exe", 50_000_000, 5),
    ]
    items = I.find_installers(index=FakeIndex(rows), now=NOW, min_age_days=30, min_bytes=0,
                              skip_system=False)
    names = [i["name"] for i in items]
    assert "unins000.exe" not in names, names
    assert "random-tool.exe" not in names, names
    assert "AppSetup_1.0_x64.exe" not in names, names
    newest = next(i for i in items if i["name"] == "PhotoStudio_2024.1_win64.exe")
    older = next(i for i in items if i["name"] == "PhotoStudio_2023.2_win64.exe")
    assert not newest["duplicate_of"]
    assert older["duplicate_of"] == newest["name"]
    assert older["reason"] == "Older copy"
    assert newest["reason"] == "Older than a year"
    assert older["age_text"] and older["size_text"]
    game = next(i for i in items if i["name"] == "OldGameSetup.exe")
    assert game["large_old"] is True, game
    assert newest["large_old"] is True, newest
    assert older["large_old"] is True, older

    safe = set(I.safe_selection(items))
    assert older["path"] in safe and newest["path"] in safe
    assert game["path"] in safe

    summary = I.summary(items)
    assert summary["count"] == len(items)
    assert summary["bytes"] == sum(i["size"] for i in items)
    assert summary["duplicates"] == 1
    assert summary["large_old"] >= 2, summary

    recent_only = I.find_installers(index=FakeIndex(rows), now=NOW, min_age_days=750, min_bytes=0,
                                    skip_system=False)
    assert [i["name"] for i in recent_only] == ["OldGameSetup.exe"], recent_only


def test_remove_uses_recycle_bin():
    seen = []
    original = I.recycle_bin
    I.recycle_bin = lambda paths: (seen.extend(paths) or len(paths), [])
    try:
        moved, failed = I.remove([r"C:\Users\Alex\Downloads\Old.exe"])
    finally:
        I.recycle_bin = original
    assert (moved, failed) == (1, [])
    assert seen == [r"C:\Users\Alex\Downloads\Old.exe"]


class FakeProtection:
    def __init__(self, protected):
        self.protected = {p.lower() for p in protected}

    def is_protected(self, path):
        return (path or "").lower() in self.protected

    def filter_paths(self, paths):
        allowed, blocked = [], []
        for p in paths:
            (blocked if self.is_protected(p) else allowed).append(p)
        return allowed, blocked


def test_protection_filters_suggestions():
    rows = [
        row(r"C:\Users\Alex\Downloads\KeepThisSetup.exe", 40_000_000, 800),
        row(r"C:\Users\Alex\Downloads\OldSetup.exe", 2_000_000, 500),
    ]
    protection = FakeProtection([r"C:\Users\Alex\Downloads\KeepThisSetup.exe"])
    stats = {}
    items = I.find_installers(index=FakeIndex(rows), now=NOW, min_age_days=30, min_bytes=0,
                              skip_system=False, protection=protection, stats=stats)
    names = [i["name"] for i in items]
    assert "KeepThisSetup.exe" not in names, names
    assert "OldSetup.exe" in names, names
    assert stats["protected_skipped"] == 1, stats
    assert I.safe_selection(items) == [r"C:\Users\Alex\Downloads\OldSetup.exe"]

    listed = I.find_installers(index=FakeIndex(rows), now=NOW, min_age_days=30, min_bytes=0,
                               skip_system=False, protection=protection, include_protected=True)
    keep = next(i for i in listed if i["name"] == "KeepThisSetup.exe")
    assert keep["protected"] is True
    assert keep["path"] not in I.safe_selection(listed)


def test_remove_skips_protected_paths():
    seen = []
    original = I.recycle_bin
    I.recycle_bin = lambda paths: (seen.extend(paths) or len(paths), [])
    try:
        blocked = []
        protection = FakeProtection([r"C:\Users\Alex\Downloads\Keep.exe"])
        moved, failed = I.remove([r"C:\Users\Alex\Downloads\Keep.exe",
                                  r"C:\Users\Alex\Downloads\Old.exe"], protection=protection,
                                 blocked=blocked)
    finally:
        I.recycle_bin = original
    assert moved == 1 and failed == []
    assert seen == [r"C:\Users\Alex\Downloads\Old.exe"]
    assert blocked == [r"C:\Users\Alex\Downloads\Keep.exe"]


if __name__ == "__main__":
    test_name_heuristics()
    test_normalize_name()
    test_find_duplicates_and_safe_picks()
    test_remove_uses_recycle_bin()
    test_protection_filters_suggestions()
    test_remove_skips_protected_paths()
    print("installers tests OK")
