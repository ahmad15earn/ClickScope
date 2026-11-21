"""Find old installers and offer to clear them, safely.

Installers are detected by extension and by name/path heuristics, never by
opening them. Nothing is deleted automatically: the interface asks, and files
are moved to the Recycle Bin so every action can be undone.
"""
import os
import re
import time

from appdata import drive_info, fixed_drives, human_age, human_size, known_folders, recycle_bin

INSTALLER_EXTS = {".exe", ".msi", ".msix", ".appx", ".msu"}
SYSTEM_PARTS = ("\\windows\\", "\\program files\\", "\\program files (x86)\\", "\\programdata\\",
                "\\appdata\\", "\\$recycle.bin\\", "\\system volume information\\", "\\node_modules\\")
INSTALL_WORDS = ("setup", "install", "installer", "update", "upgrade", "redist", "runtime")
ARCH_WORDS = ("x64", "x86", "win32", "win64", "amd64", "arm64", "64bit", "32bit")
VERSION_RE = re.compile(r"(?<![a-z0-9])v?\d+(?:[._]\d+){1,4}(?![a-z0-9])", re.I)
COPY_RE = re.compile(r"\s*\((?:\d+|copy)\)\s*$", re.I)
DATE_RE = re.compile(r"(?<![a-z0-9])(?:19|20)\d{2}[-_.]?\d{2}[-_.]?\d{2}(?![a-z0-9])")
WORD_RE = re.compile(r"setup|installer|install|update|download|copy|final|latest", re.I)
ARCH_RE = re.compile(r"(?<![a-z0-9])(x64|x86|win32|win64|amd64|arm64|64bit|32bit)(?![a-z0-9])", re.I)

SYSTEM_TOP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
              "system volume information", "recovery", "perflogs", "users", "appdata"}


def _under_system(path):
    low = (path or "").lower().replace("/", "\\")
    return any(part in low for part in SYSTEM_PARTS)


def _in_user_place(path):
    low = (path or "").lower().replace("/", "\\")
    if any("\\" + name.lower() in low for name in
           ("downloads", "desktop", "documents", "installers", "software", "setup", "backup")):
        return True
    drive, rest = os.path.splitdrive(path)
    return bool(drive and rest and rest.count("\\") <= 2)


def looks_like_installer(name, path, size=0, min_bytes=256 * 1024, skip_system=True):
    ext = os.path.splitext(name or "")[1].lower()
    if ext not in INSTALLER_EXTS or (skip_system and _under_system(path)):
        return False
    low = (name or "").lower()
    if re.match(r"^(unins|uninstall|unwise|setup_.*\.tmp)", low):
        return False
    if ext != ".exe":
        return True
    if size and size < min_bytes and not any(w in low for w in INSTALL_WORDS):
        return False
    if any(w in low for w in INSTALL_WORDS) or any(w in low for w in ARCH_WORDS):
        return True
    if VERSION_RE.search(low) and _in_user_place(path):
        return True
    return False


def normalize_name(name):
    """A stable key so 'AppSetup_1.2.3_x64.exe' and 'App Setup v1.3.exe' group together."""
    stem = os.path.splitext(name or "")[0].lower()
    stem = COPY_RE.sub("", stem)
    stem = DATE_RE.sub(" ", stem)
    stem = VERSION_RE.sub(" ", stem)
    stem = ARCH_RE.sub(" ", stem)
    stem = re.sub(r"[_\-\.]+", " ", stem)
    stem = WORD_RE.sub(" ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or os.path.splitext(name or "")[0].lower()


def _installer_dict(path, size, mtime, now):
    name = os.path.basename(path)
    age_days = max(0, int((now - (mtime or now)) / 86400))
    return dict(path=path, name=name, dir=os.path.dirname(path), ext=os.path.splitext(name)[1].lower(),
                size=int(size or 0), mtime=int(mtime or 0), age_days=age_days,
                size_text=human_size(size), age_text=human_age(mtime),
                norm=normalize_name(name), duplicate_of="", reason="")


def _scan_folders(progress=None):
    """Fallback when no index exists: everyday folders plus the top of each local disk."""
    seen, files = set(), []
    roots = [p for _, p in known_folders()]
    for drive in fixed_drives():
        try:
            with os.scandir(drive) as it:
                for e in it:
                    if (e.is_dir(follow_symlinks=False) and not e.name.startswith("$")
                            and e.name.lower() not in SYSTEM_TOP):
                        roots.append(e.path)
        except OSError:
            pass
    for root in dict.fromkeys(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth >= 3:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d.lower() not in
                           ("node_modules", ".git", "windows", "program files", "program files (x86)", "appdata")]
            for f in filenames:
                if os.path.splitext(f)[1].lower() in INSTALLER_EXTS:
                    p = os.path.join(dirpath, f)
                    if p.lower() in seen or _under_system(p):
                        continue
                    seen.add(p.lower())
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    files.append((p, st.st_size, st.st_mtime))
                    if progress and len(files) % 100 == 0:
                        progress(len(files))
    return files


def find_installers(index=None, min_age_days=30, now=None, include_recent=False, min_bytes=256 * 1024,
                    skip_system=True):
    """Return installers older than min_age_days, with duplicate versions marked.

    `index` may be a filesearch.FileIndex; its metadata makes this instant.
    """
    now = now or time.time()
    rows = []
    if index is not None:
        try:
            if index.has_data():
                rows = [(r["path"], r["size"], r["mtime"]) for r in index.installer_rows()]
        except Exception:
            rows = []
    if not rows:
        rows = _scan_folders()

    items = []
    for path, size, mtime in rows:
        name = os.path.basename(path)
        if not looks_like_installer(name, path, size, min_bytes, skip_system):
            continue
        it = _installer_dict(path, size, mtime, now)
        if not include_recent and it["age_days"] < min_age_days:
            continue
        items.append(it)

    # Mark older copies of the same installer (same name stem, type and folder).
    groups = {}
    for it in items:
        groups.setdefault((it["norm"], it["ext"], it["dir"].lower()), []).append(it)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x["mtime"], reverse=True)
        newest = group[0]
        for older in group[1:]:
            older["duplicate_of"] = newest["name"]
            older["reason"] = "Older copy"
    for it in items:
        if not it["reason"]:
            if it["age_days"] >= 365:
                it["reason"] = "Older than a year"
            else:
                it["reason"] = "Old download"

    items.sort(key=lambda x: (0 if x["duplicate_of"] else 1, -x["age_days"], -x["size"], x["name"].lower()))
    return items


def summary(items):
    total = sum(i["size"] for i in items)
    return dict(count=len(items), bytes=total, size_text=human_size(total),
                duplicates=sum(1 for i in items if i["duplicate_of"]))


def safe_selection(items):
    """Older duplicate versions plus anything more than a year old."""
    return [i["path"] for i in items if i["duplicate_of"] or i["age_days"] >= 365]


def remove(paths):
    """Move installer files to the Recycle Bin. Returns (moved, failed)."""
    return recycle_bin(list(paths))


def drives():
    return drive_info()
