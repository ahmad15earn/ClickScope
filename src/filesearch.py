"""ClickScope's local file index: build once, search instantly, stay fresh.

Only metadata is stored: file name, folder, size, modified time and type.
ClickScope never opens, reads or uploads the contents of your files.

The index lives in a SQLite database with an FTS5 name index for fast typing.
A background watcher (Windows ReadDirectoryChangesW) keeps everyday folders
up to date while ClickScope is running.
"""
import ctypes
import json
import os
import queue
import re
import sqlite3
import struct
import threading
import time
from ctypes import wintypes

from appdata import APP_DIR, INDEX_PATH, IS_WINDOWS, fixed_drives, known_folders

# ------------------------------------------------------------------ file kinds
EXT_KINDS = {
    "doc": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".ppt", ".pptx",
            ".md", ".epub", ".pages", ".numbers", ".key", ".one", ".log"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff", ".heic", ".ico",
              ".psd", ".ai", ".raw", ".cr2", ".nef"},
    "video": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".m4v", ".flv", ".mpg", ".mpeg", ".ts"},
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".aiff", ".opus"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".cab", ".tgz", ".zst"},
    "app": {".exe", ".msi", ".msix", ".appx", ".msu", ".lnk", ".bat", ".cmd", ".ps1", ".appref-ms"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".json", ".xml", ".yml", ".yaml",
             ".c", ".cpp", ".cc", ".h", ".hpp", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".sh",
             ".swift", ".kt", ".vue", ".svelte", ".toml", ".ini", ".cfg"},
}
EXT_TO_KIND = {ext: kind for kind, exts in EXT_KINDS.items() for ext in exts}

KIND_LABELS = {"all": "All", "doc": "Documents", "image": "Images", "video": "Video", "audio": "Audio",
               "app": "Apps", "archive": "Archives", "code": "Code"}

SKIP_DIRS = {
    "$recycle.bin", "$windows.~bt", "$windows.~ws", "windows.old", "system volume information", "windows",
    "winsxs", "servicing", "softwaredistribution", "driverstore", "programdata", "recovery", "perflogs",
    "msocache", "config.msi", "appdata", "node_modules", ".git", ".svn", ".hg", "__pycache__", ".venv",
    "venv", ".tox", ".mypy_cache", ".pytest_cache", ".cache", "temp", "tmp", "packages", "prefetch", "assembly",
    ".next", ".nuxt",
}
SKIP_FILES = {"desktop.ini", "thumbs.db", ".ds_store", "iconcache.db"}
SKIP_PREFIX = ("~$", ".~", "~wrl")
EXCLUDED_PATH_PARTS = ("\\windows\\", "\\programdata\\", "\\$recycle.bin\\", "\\system volume information\\",
                       "\\appdata\\")
INSTALLER_EXTS = (".exe", ".msi", ".msix", ".appx", ".msu")

FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def kind_for(ext, is_dir=False):
    if is_dir:
        return "folder"
    return EXT_TO_KIND.get((ext or "").lower(), "other")


def should_skip_dir(name):
    low = (name or "").lower()
    return low in SKIP_DIRS or low.startswith("$") and low.endswith("bin")


def should_skip_file(name):
    low = (name or "").lower()
    return low in SKIP_FILES or low.startswith(SKIP_PREFIX)


def _is_reparse(entry):
    """Skip links/junctions so a scan can never loop, but keep OneDrive placeholders."""
    try:
        if entry.is_symlink():
            return True
        if hasattr(entry, "is_junction") and entry.is_junction():
            return True
    except OSError:
        return True
    return False


class FileIndex:
    """One local metadata index. Safe to use from the UI thread and background threads."""

    def __init__(self, path=None, extra_roots=None):
        os.makedirs(os.path.dirname(path or INDEX_PATH), exist_ok=True)
        self.path = path or INDEX_PATH
        self.extra_roots = [p for p in (extra_roots or []) if p]
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=8)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.execute("PRAGMA temp_store=MEMORY")
            self.db.execute("PRAGMA cache_size=-12000")
        except sqlite3.DatabaseError:
            pass
        self._make_schema()
        self._stats_cache = (0.0, None)
        self._stop = None
        self._thread = None
        self._building = False
        self._progress = dict(state="idle", files=0, dirs=0, current="", started=0.0, done=0.0,
                              total_estimate=0, error="")
        self._watch_stop = None
        self._watch_threads = []
        self._watch_handles = []
        self._watch_queue = None
        self._watch_worker = None
        self.on_change = None
        self._load_state()

    # ------------------------------------------------------------------ schema
    def _make_schema(self):
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS files(
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                name_lower TEXT NOT NULL,
                dir TEXT NOT NULL,
                dir_lower TEXT NOT NULL,
                ext TEXT NOT NULL DEFAULT '',
                size INTEGER NOT NULL DEFAULT 0,
                mtime INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL DEFAULT 'other',
                is_dir INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS files_name ON files(name_lower);
            CREATE INDEX IF NOT EXISTS files_kind ON files(kind);
            CREATE INDEX IF NOT EXISTS files_ext ON files(ext);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            """)
            self._make_fts()
            self.db.commit()

    def _make_fts(self):
        try:
            self.db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(name, dir, content='');
            CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                INSERT INTO files_fts(rowid, name, dir) VALUES (new.id, new.name, new.dir);
            END;
            CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, name, dir) VALUES ('delete', old.id, old.name, old.dir);
            END;
            CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
                INSERT INTO files_fts(files_fts, rowid, name, dir) VALUES ('delete', old.id, old.name, old.dir);
                INSERT INTO files_fts(rowid, name, dir) VALUES (new.id, new.name, new.dir);
            END;
            """)
            self.fts_ok = True
        except sqlite3.DatabaseError:
            self.fts_ok = False

    def _reset_index(self):
        """Empty everything and recreate the mirror table (fast path for a full rebuild)."""
        with self.lock:
            self.db.executescript("""
            DROP TRIGGER IF EXISTS files_ai;
            DROP TRIGGER IF EXISTS files_ad;
            DROP TRIGGER IF EXISTS files_au;
            DROP TABLE IF EXISTS files_fts;
            DELETE FROM files;
            """)
            self.db.commit()
            self._make_fts()
            self._stats_cache = (0.0, None)

    def _load_state(self):
        st = self._meta("state") or "idle"
        if st == "scanning":  # previous run was interrupted
            st = "partial"
        last = float(self._meta("last_build") or 0)
        self._progress.update(state=st, done=last)
        self._stats_cache = (0.0, None)

    # ------------------------------------------------------------------- meta
    def _meta(self, key, default=None):
        with self.lock:
            r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def _set_meta(self, key, value):
        with self.lock:
            self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
            self.db.commit()

    # ------------------------------------------------------------------ stats
    def default_roots(self):
        return list(dict.fromkeys(fixed_drives() + list(self.extra_roots)))

    def stats(self, cache=True):
        now = time.time()
        if cache and now - self._stats_cache[0] < 1.0 and self._stats_cache[1]:
            return dict(self._stats_cache[1])
        with self.lock:
            total = self.db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            dirs = self.db.execute("SELECT COUNT(*) FROM files WHERE is_dir=1").fetchone()[0]
            installed = self.db.execute("SELECT COUNT(*) FROM files WHERE is_dir=0").fetchone()[0]
        st = self._progress.get("state") or "idle"
        if st == "idle" and installed:
            st = self._meta("state") or "ready"
        data = dict(total=int(total), dirs=int(dirs), files=int(installed), state=st,
                    last_build=float(self._meta("last_build") or 0),
                    roots=json.loads(self._meta("roots") or "[]"),
                    progress=dict(self._progress))
        self._stats_cache = (now, data)
        return dict(data)

    def has_data(self):
        return self.stats(cache=False)["files"] > 0

    def is_building(self):
        return self._building

    def progress(self):
        with self.lock:
            return dict(self._progress)

    def _invalidate(self):
        self._stats_cache = (0.0, None)

    # ------------------------------------------------------------------- build
    def build_async(self, roots=None, on_done=None):
        if self._building:
            return False
        self._stop = threading.Event()
        self._building = True
        self._thread = threading.Thread(target=self._build_worker, args=(roots, on_done), daemon=True,
                                        name="ClickScopeIndex")
        self._thread.start()
        return True

    def _build_worker(self, roots, on_done):
        ok = False
        try:
            ok = self.build(roots=roots, stop_event=self._stop)
        except Exception as e:  # never take the app down because one folder refused to read
            with self.lock:
                self._progress.update(state="partial", error=str(e), done=time.time())
            self._set_meta("state", "partial")
        finally:
            self._building = False
        try:
            if on_done:
                on_done(ok, self.stats(cache=False))
        except Exception:
            pass

    def build(self, roots=None, reset=True, stop_event=None, progress_cb=None):
        """Synchronous full scan. roots defaults to every fixed local drive."""
        self._invalidate()
        roots = [r for r in (roots or self.default_roots()) if os.path.isdir(r)]
        stop = stop_event or threading.Event()
        if reset:
            self._reset_index()
        with self.lock:
            self._progress.update(state="scanning", files=0, dirs=0, current="", started=time.time(),
                                  done=0.0, error="", total_estimate=0)
        self._set_meta("state", "scanning")
        batch = []
        counters = dict(files=0, dirs=0, last_ui=0.0)

        def flush():
            if not batch:
                return
            with self.lock:
                self.db.executemany(
                    "INSERT INTO files(path,name,name_lower,dir,dir_lower,ext,size,mtime,kind,is_dir) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(path) DO UPDATE SET name=excluded.name, name_lower=excluded.name_lower, "
                    "dir=excluded.dir, dir_lower=excluded.dir_lower, ext=excluded.ext, size=excluded.size, "
                    "mtime=excluded.mtime, kind=excluded.kind, is_dir=excluded.is_dir", batch)
                self.db.commit()
            batch.clear()
            self._invalidate()

        def add(path, name, is_dir):
            try:
                st = os.stat(path, follow_symlinks=False)
                size = 0 if is_dir else int(st.st_size)
                mtime = int(st.st_mtime)
            except OSError:
                return
            ext = "" if is_dir else os.path.splitext(name)[1].lower()
            d = os.path.dirname(path)
            batch.append((path, name, name.lower(), d, d.lower(), ext, size, mtime,
                          kind_for(ext, is_dir), 1 if is_dir else 0))
            if is_dir:
                counters["dirs"] += 1
            else:
                counters["files"] += 1

        def progress(current):
            now = time.time()
            with self.lock:
                self._progress.update(files=counters["files"], dirs=counters["dirs"], current=current)
            if progress_cb and (now - counters["last_ui"] > 0.25):
                counters["last_ui"] = now
                try:
                    progress_cb(dict(self.progress()))
                except Exception:
                    pass

        for root in roots:
            if stop.is_set():
                break
            root = os.path.abspath(root)
            add(root, os.path.basename(root.rstrip("\\/")) or root, True)
            stack = [root]
            while stack and not stop.is_set():
                d = stack.pop()
                try:
                    with os.scandir(d) as it:
                        for e in it:
                            if stop.is_set():
                                break
                            try:
                                if _is_reparse(e):
                                    continue
                                if e.is_dir(follow_symlinks=False):
                                    if should_skip_dir(e.name):
                                        continue
                                    path = os.path.join(d, e.name)
                                    add(path, e.name, True)
                                    stack.append(path)
                                elif e.is_file(follow_symlinks=False):
                                    if should_skip_file(e.name):
                                        continue
                                    add(os.path.join(d, e.name), e.name, False)
                            except OSError:
                                continue
                except OSError:
                    continue
                if len(batch) >= 800:
                    flush()
                    progress(d)
                else:
                    progress(d)
        flush()
        cancelled = stop.is_set()
        state = "partial" if cancelled else "ready"
        with self.lock:
            self._progress.update(state=state, done=time.time(), current="")
        self._set_meta("state", state)
        self._set_meta("last_build", int(time.time()))
        self._set_meta("roots", json.dumps(roots))
        self._invalidate()
        return not cancelled

    def cancel(self):
        if self._stop is not None:
            self._stop.set()

    def clear(self):
        """Forget every indexed name. Settings' 'Remove index' uses this."""
        self._building = False
        self._reset_index()
        self._set_meta("state", "idle")
        self._set_meta("last_build", 0)
        self._set_meta("roots", "[]")
        with self.lock:
            self._progress.update(state="idle", files=0, dirs=0, current="", started=0.0, done=0.0,
                                  total_estimate=0, error="")
        self._invalidate()

    # ------------------------------------------------------------------ update
    @staticmethod
    def _excluded(path):
        low = (path or "").lower()
        return any(part in low for part in EXCLUDED_PATH_PARTS)

    def _delete_prefix(self, path):
        prefix = path.rstrip("\\/") + os.sep
        with self.lock:
            self.db.execute("DELETE FROM files WHERE path = ? OR substr(path, 1, ?) = ?",
                            (path, len(prefix), prefix))
            self.db.commit()
        self._invalidate()

    def index_path(self, path, stop_event=None):
        """Add or refresh one file/folder. Safe to call from the watcher."""
        if not path or self._excluded(path):
            return 0
        if not os.path.exists(path):
            self._delete_prefix(path)
            return 0
        rows = []
        dirs = 0

        def add_one(p, name, is_dir):
            try:
                st = os.stat(p, follow_symlinks=False)
                size = 0 if is_dir else int(st.st_size)
                mtime = int(st.st_mtime)
            except OSError:
                return
            ext = "" if is_dir else os.path.splitext(name)[1].lower()
            rows.append((p, name, name.lower(), os.path.dirname(p), os.path.dirname(p).lower(), ext, size,
                         mtime, kind_for(ext, is_dir), 1 if is_dir else 0))

        if os.path.isdir(path):
            if should_skip_dir(os.path.basename(path)):
                return 0
            self._delete_prefix(path)
            add_one(path, os.path.basename(path) or path, True)
            dirs += 1
            stack = [path]
            while stack:
                if stop_event is not None and stop_event.is_set():
                    break
                d = stack.pop()
                try:
                    with os.scandir(d) as it:
                        for e in it:
                            try:
                                if _is_reparse(e):
                                    continue
                                if e.is_dir(follow_symlinks=False):
                                    if should_skip_dir(e.name):
                                        continue
                                    p = os.path.join(d, e.name)
                                    add_one(p, e.name, True)
                                    dirs += 1
                                    stack.append(p)
                                elif e.is_file(follow_symlinks=False):
                                    if not should_skip_file(e.name):
                                        add_one(os.path.join(d, e.name), e.name, False)
                            except OSError:
                                continue
                except OSError:
                    continue
                if len(rows) >= 500:
                    self._upsert(rows)
        else:
            if should_skip_file(os.path.basename(path)):
                return 0
            add_one(path, os.path.basename(path), False)
        self._upsert(rows)
        self._invalidate()
        return len(rows)

    def _upsert(self, rows):
        if not rows:
            return
        with self.lock:
            self.db.executemany(
                "INSERT INTO files(path,name,name_lower,dir,dir_lower,ext,size,mtime,kind,is_dir) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET name=excluded.name, name_lower=excluded.name_lower, "
                "dir=excluded.dir, dir_lower=excluded.dir_lower, ext=excluded.ext, size=excluded.size, "
                "mtime=excluded.mtime, kind=excluded.kind, is_dir=excluded.is_dir", rows)
            self.db.commit()
        self._invalidate()

    def remove_paths(self, paths):
        for p in paths:
            self._delete_prefix(p)
        self._invalidate()

    def installer_rows(self):
        q = ("SELECT path,name,dir,ext,size,mtime FROM files WHERE is_dir=0 AND ext IN (?,?,?,?,?)")
        with self.lock:
            return [dict(r) for r in self.db.execute(q, INSTALLER_EXTS).fetchall()]

    # ------------------------------------------------------------------ search
    @staticmethod
    def _fts_query(q):
        tokens = re.findall(r"[0-9A-Za-z_]+", (q or "").lower())
        if not tokens:
            return ""
        return " AND ".join(f'"{t}"*' for t in tokens)

    @staticmethod
    def _like_escape(s):
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _rows_to_dicts(self, rows):
        return [dict(r) for r in rows]

    def search(self, query, kind=None, limit=120):
        q = (query or "").strip()
        if not q:
            return []
        kind = kind if kind and kind != "all" else None
        ql = q.lower()
        results, seen = [], set()

        # 1) FTS5 prefix search: fast for every keystroke.
        fts_q = self._fts_query(q)
        if self.fts_ok and fts_q and q.isascii() and len(q) >= 2:
            sql = ("SELECT f.path,f.name,f.dir,f.ext,f.size,f.mtime,f.kind,f.is_dir "
                   "FROM files_fts JOIN files f ON f.id=files_fts.rowid WHERE files_fts MATCH ?")
            args = [fts_q]
            if kind:
                sql += " AND f.kind = ?"
                args.append(kind)
            sql += " ORDER BY bm25(files_fts, 8.0, 1.5) LIMIT ?"
            args.append(max(limit, 60))
            try:
                with self.lock:
                    rows = self.db.execute(sql, args).fetchall()
                for r in self._rows_to_dicts(rows):
                    results.append(r)
                    seen.add(r["path"])
            except sqlite3.DatabaseError:
                pass

        # 2) Substring search: catches "port" inside "report" and non-ASCII names.
        need_more = len(results) < min(limit, 40) or not fts_q or not q.isascii()
        if need_more:
            tokens = [t for t in re.split(r"\s+", ql) if t]
            clauses, args = [], []
            for t in tokens:
                pat = "%" + self._like_escape(t) + "%"
                clauses.append("(name_lower LIKE ? ESCAPE '\\' OR dir_lower LIKE ? ESCAPE '\\')")
                args += [pat, pat]
            sql = ("SELECT path,name,dir,ext,size,mtime,kind,is_dir FROM files WHERE " +
                   (" AND ".join(clauses) if clauses else "1=1"))
            if kind:
                sql += " AND kind = ?"
                args.append(kind)
            sql += " LIMIT 1500"
            try:
                with self.lock:
                    rows = self.db.execute(sql, args).fetchall()
                for r in self._rows_to_dicts(rows):
                    if r["path"] not in seen:
                        results.append(r)
                        seen.add(r["path"])
            except sqlite3.DatabaseError:
                pass

        def score(r):
            name = (r["name"] or "").lower()
            d = (r["dir"] or "").lower()
            if name == ql:
                return 0
            if name.startswith(ql):
                return 1
            if ql in name:
                return 2
            tokens = [t for t in re.split(r"\s+", ql) if t]
            if tokens and all(t in name for t in tokens):
                return 2
            if ql in d:
                return 3
            if tokens and all(t in d for t in tokens):
                return 4
            return 5

        results.sort(key=lambda r: (score(r), 0 if r["is_dir"] else 1, -(r["mtime"] or 0), r["name"].lower()))
        return results[:limit]

    # ----------------------------------------------------------------- watcher
    def start_watcher(self, on_change=None):
        if not IS_WINDOWS or self._watch_stop is not None:
            return False
        roots = [p for _, p in known_folders()]
        if not roots:
            return False
        self.on_change = on_change
        self._watch_stop = threading.Event()
        self._watch_queue = queue.Queue()
        self._watch_handles = []
        for p in roots:
            t = threading.Thread(target=self._watch_loop, args=(p,), daemon=True, name="ClickScopeWatch")
            t.start()
            self._watch_threads.append(t)
        self._watch_worker = threading.Thread(target=self._watch_changes, daemon=True,
                                              name="ClickScopeWatchWorker")
        self._watch_worker.start()
        return True

    def stop_watcher(self):
        if self._watch_stop is None:
            return
        self._watch_stop.set()
        for h in list(self._watch_handles):
            try:
                k32 = ctypes.windll.kernel32
                k32.CancelIoEx(ctypes.c_void_p(h), None)
                k32.CloseHandle(ctypes.c_void_p(h))
            except Exception:
                pass
        if self._watch_queue is not None:
            try:
                self._watch_queue.put(None)
            except Exception:
                pass
        self._watch_stop = None

    def _watch_loop(self, root):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                              wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                              wintypes.LPVOID, wintypes.LPVOID]
        k32.ReadDirectoryChangesW.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        FILE_LIST_DIRECTORY = 0x0001
        FILE_SHARE_READ, FILE_SHARE_WRITE, FILE_SHARE_DELETE = 0x1, 0x2, 0x4
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        NOTIFY = 0x1 | 0x2 | 0x8 | 0x10  # file name, dir name, last write, size
        handle = k32.CreateFileW(root, FILE_LIST_DIRECTORY,
                                 FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, None,
                                 OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
        if not handle or handle == wintypes.HANDLE(-1).value:
            return
        self._watch_handles.append(handle)
        buf = ctypes.create_string_buffer(64 * 1024)
        try:
            while self._watch_stop is not None and not self._watch_stop.is_set():
                n = wintypes.DWORD()
                ok = k32.ReadDirectoryChangesW(handle, buf, len(buf), True, NOTIFY, ctypes.byref(n), None, None)
                if not ok or not n.value:
                    if self._watch_stop is not None and self._watch_stop.is_set():
                        break
                    time.sleep(0.3)
                    continue
                raw = buf.raw[:n.value]
                off = 0
                while True:
                    nxt, action, namelen = struct.unpack_from("III", raw, off)
                    name = raw[off + 12:off + 12 + namelen].decode("utf-16-le", "ignore")
                    full = os.path.join(root, name)
                    if not self._excluded(full) and self._watch_queue is not None:
                        self._watch_queue.put((full, action))
                    if nxt == 0:
                        break
                    off += nxt
        except Exception:
            pass
        finally:
            try:
                k32.CloseHandle(handle)
            except Exception:
                pass

    def _watch_changes(self):
        """Debounce bursts of file events, then apply them off the UI thread."""
        pending = {}
        last = time.time()
        while self._watch_stop is not None and not self._watch_stop.is_set():
            try:
                item = self._watch_queue.get(timeout=0.4)
            except queue.Empty:
                item = None
            if item is None:
                if pending and time.time() - last > 1.0:
                    self._apply_pending(pending)
                    pending, last = {}, time.time()
                continue
            path, action = item
            if action == 4:  # old name of a rename
                pending[(path, 2)] = True
            else:
                pending[(path, action)] = True
            last = time.time()
            if len(pending) > 400:
                self._apply_pending(pending)
                pending, last = {}, time.time()
        if pending:
            self._apply_pending(pending)

    def _apply_pending(self, pending):
        changed = False
        for (path, action) in pending:
            try:
                if action == 2:  # removed / old rename
                    self._delete_prefix(path)
                    changed = True
                elif os.path.exists(path):
                    if self.index_path(path, self._watch_stop):
                        changed = True
            except Exception:
                continue
        self._invalidate()
        if changed and self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ------------------------------------------------------------------- close
    def close(self):
        self.cancel()
        self.stop_watcher()
        try:
            with self.lock:
                self.db.commit()
                self.db.close()
        except sqlite3.Error:
            pass
