"""Protected files and folders: the first rule every cleanup must respect.

Age and size never decide safety on their own. A file can be ten years old and
still be the only copy of something important, so protection is checked before
any installer is ever offered as a cleanup suggestion.

The database is a small JSON file written atomically. Renames and moves are
re-matched by name, size and modified time through the local index when that is
unambiguous; when there is any doubt the entry is left exactly as it was.
"""
import json
import os
import threading
import time

from appdata import APP_DIR

PROTECTION_PATH = os.path.join(APP_DIR, "protection.json")


def norm_path(path):
    try:
        return os.path.normpath(os.path.abspath(os.path.expanduser(str(path or ""))))
    except (OSError, ValueError):
        return ""


def path_key(path):
    return norm_path(path).lower()


def _entry(path, kind="", note=""):
    path = norm_path(path)
    name = os.path.basename(path.rstrip("\\/")) or path
    is_dir = os.path.isdir(path) if kind not in ("file", "folder") else kind == "folder"
    kind = "folder" if is_dir else "file"
    size = mtime = 0
    if path and os.path.exists(path):
        try:
            st = os.stat(path, follow_symlinks=False)
            size = 0 if is_dir else int(st.st_size)
            mtime = int(st.st_mtime)
        except OSError:
            pass
    return dict(path=path, kind=kind, name=name, size=size, mtime=mtime,
                added=int(time.time()), note=str(note or ""))


def _valid_entry(raw):
    if not isinstance(raw, dict):
        return None
    path = norm_path(raw.get("path"))
    if not path:
        return None
    kind = "folder" if raw.get("kind") == "folder" else "file"
    try:
        size = max(0, int(raw.get("size") or 0))
    except (TypeError, ValueError):
        size = 0
    try:
        mtime = max(0, int(raw.get("mtime") or 0))
    except (TypeError, ValueError):
        mtime = 0
    try:
        added = max(0, int(raw.get("added") or 0))
    except (TypeError, ValueError):
        added = 0
    return dict(path=path, kind=kind, name=os.path.basename(path.rstrip("\\/")) or path,
                size=size, mtime=mtime, added=added, note=str(raw.get("note") or "")[:200])


class Protection:
    """Thread-safe protection list with atomic writes and a safety backup."""

    def __init__(self, path=None):
        self.path = path or PROTECTION_PATH
        self.lock = threading.RLock()
        self.entries = {}
        self.recovered = False
        self._load()

    # ------------------------------------------------------------------ disk
    def _load(self):
        loaded = None
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
        except FileNotFoundError:
            loaded = {}
        except (OSError, ValueError):
            self.recovered = True
            try:
                if os.path.isfile(self.path):
                    os.replace(self.path, self.path + ".corrupt-%d" % int(time.time()))
            except OSError:
                pass
            loaded = {}
        if not isinstance(loaded, dict):
            loaded = {}
        raw = loaded.get("entries", loaded.get("items", []))
        items = raw.values() if isinstance(raw, dict) else raw
        if isinstance(items, (list, tuple)):
            for item in items:
                entry = _valid_entry(item)
                if entry:
                    self.entries[path_key(entry["path"])] = entry
        elif isinstance(raw, dict):
            for value in raw.values():
                entry = _valid_entry(value)
                if entry:
                    self.entries[path_key(entry["path"])] = entry

    def _write(self):
        data = dict(format="clickscope-protection", version=1,
                    entries={k: dict(v) for k, v in self.entries.items()})
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.isfile(self.path):
                try:
                    import shutil
                    shutil.copy2(self.path, self.path + ".bak")
                except OSError:
                    pass
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    # ----------------------------------------------------------------- access
    def add(self, path, note=""):
        target = norm_path(path)
        if not target:
            raise ValueError("Choose a file or folder first.")
        if not os.path.exists(target):
            raise ValueError("That file or folder is no longer there.")
        entry = _entry(target, note=note)
        with self.lock:
            self.entries[path_key(target)] = entry
            self._write()
        return dict(entry)

    def remove(self, path):
        key = path_key(path)
        with self.lock:
            existed = self.entries.pop(key, None) is not None
            if existed:
                self._write()
        return existed

    def clear(self):
        with self.lock:
            self.entries.clear()
            self._write()

    def get(self, path):
        key = path_key(path)
        with self.lock:
            entry = self.entries.get(key)
            return dict(entry) if entry else None

    def is_protected(self, path):
        """True when the exact item, or any parent folder, is protected."""
        target = norm_path(path)
        if not target:
            return False
        key = target.lower()
        with self.lock:
            if key in self.entries:
                return True
            parent = os.path.dirname(target)
            while parent and parent != target:
                entry = self.entries.get(parent.lower())
                if entry and entry.get("kind") == "folder":
                    return True
                nxt = os.path.dirname(parent)
                if nxt == parent:
                    break
                parent = nxt
        return False

    def protected_entry_for(self, path):
        """The exact entry, or the protected parent folder that covers it."""
        target = norm_path(path)
        if not target:
            return None
        with self.lock:
            entry = self.entries.get(target.lower())
            if entry:
                return dict(entry)
            parent = os.path.dirname(target)
            while parent and parent != target:
                entry = self.entries.get(parent.lower())
                if entry and entry.get("kind") == "folder":
                    return dict(entry)
                nxt = os.path.dirname(parent)
                if nxt == parent:
                    break
                parent = nxt
        return None

    def filter_paths(self, paths):
        """Split a candidate list into (allowed, blocked). Blocked is never offered."""
        allowed, blocked = [], []
        for path in paths or []:
            (blocked if self.is_protected(path) else allowed).append(path)
        return allowed, blocked

    def list_entries(self):
        with self.lock:
            return sorted((dict(v) for v in self.entries.values()),
                          key=lambda e: (e.get("kind") != "folder", e.get("name", "").lower()))

    def counts(self):
        with self.lock:
            folders = sum(1 for e in self.entries.values() if e.get("kind") == "folder")
            return dict(total=len(self.entries), folders=folders,
                        files=len(self.entries) - folders)

    # --------------------------------------------------------------- resilience
    def refresh(self, index=None):
        """Best-effort re-match after a rename or move. Never guesses when ambiguous."""
        changed = []
        with self.lock:
            missing = [dict(e) for e in self.entries.values() if not os.path.exists(e["path"])]
        for old in missing:
            match = self._find_moved(old, index)
            if not match:
                continue
            with self.lock:
                self.entries.pop(path_key(old["path"]), None)
                updated = dict(old)
                updated["path"] = match
                updated["name"] = os.path.basename(match.rstrip("\\/")) or match
                try:
                    st = os.stat(match, follow_symlinks=False)
                    updated["size"] = 0 if updated["kind"] == "folder" else int(st.st_size)
                    updated["mtime"] = int(st.st_mtime)
                except OSError:
                    pass
                self.entries[path_key(match)] = updated
                changed.append(updated)
            if index is None:
                break
        if changed:
            with self.lock:
                self._write()
        return changed

    def _find_moved(self, old, index):
        name = old.get("name") or ""
        if not name:
            return ""
        candidates = []
        if index is not None:
            try:
                candidates = index.find_by_name(name, limit=40)
            except Exception:
                candidates = []
        else:
            # No index: look only in the old folder and on the desktop, never
            # walk a whole drive just to move a marker.
            folders = [os.path.dirname(old["path"]),
                       os.path.join(os.path.expanduser("~"), "Desktop")]
            for folder in folders:
                p = os.path.join(folder, name)
                if os.path.exists(p):
                    candidates.append(dict(path=p, is_dir=os.path.isdir(p)))
        want_dir = old.get("kind") == "folder"
        exact = []
        for row in candidates:
            path = row.get("path") or ""
            if not path or not os.path.exists(path):
                continue
            if os.path.isdir(path) != want_dir:
                continue
            if os.path.normcase(path) == os.path.normcase(old["path"]):
                continue
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            if want_dir:
                # Folder mtimes change with their contents, so the name plus a
                # unique candidate is the only honest signal.
                exact.append(path)
            else:
                same_size = int(st.st_size) == int(old.get("size") or 0)
                near_time = abs(int(st.st_mtime) - int(old.get("mtime") or 0)) <= 8
                if same_size and near_time:
                    exact.append(path)
                elif same_size and os.path.basename(path).lower() == name.lower():
                    exact.append(path)
        # One unambiguous match only. Two candidates means a guess, and guesses
        # are not allowed to weaken protection or cleanup decisions.
        unique = list(dict.fromkeys(exact))
        return unique[0] if len(unique) == 1 else ""

    def summary(self):
        c = self.counts()
        return dict(c, text=f"{c['files']} file{'s' if c['files'] != 1 else ''}, "
                            f"{c['folders']} folder{'s' if c['folders'] != 1 else ''}")
