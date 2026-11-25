"""Start Menu app index tests, using stand-in shortcut files."""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import apps as APPS  # noqa: E402


def main():
    base = tempfile.mkdtemp(prefix="clickscope-apps-")
    try:
        menu = os.path.join(base, "Programs")
        os.makedirs(os.path.join(menu, "Work"), exist_ok=True)
        for name in ("Notepad.lnk", "Visual Studio Code.lnk", "Uninstall Tool.lnk",
                     "Readme.lnk", "WinRAR.lnk", "Terminal.exe"):
            folder = os.path.join(menu, "Work") if name == "Terminal.exe" else menu
            os.makedirs(folder, exist_ok=True)
            open(os.path.join(folder, name), "wb").close()

        index = APPS.AppIndex()
        rows, seen = [], set()
        index._walk(menu, 0, rows, seen, 0)
        names = {r["name"] for r in rows}
        assert "Notepad" in names, names
        assert "Visual Studio Code" in names, names
        assert "Terminal" in names, names
        assert "Uninstall Tool" not in names, "clutter should be filtered"
        assert "Readme" not in names, "clutter should be filtered"

        index.items = rows
        assert index.search("note")[0]["name"] == "Notepad"
        assert index.search("code")[0]["name"] == "Visual Studio Code"
        assert index.search("studio")[0]["name"] == "Visual Studio Code"
        assert index.search("zzz") == []
        assert index.search("") == []
        assert len(index.search("a", limit=2)) <= 2
        print("apps OK")
        return 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
