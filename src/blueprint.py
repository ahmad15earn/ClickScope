"""PC DNA: a portable map of drives, folders and the current wallpaper.

A snapshot stores only structure, never document contents. Export it as one
.clickdna file, import it on a new PC, and ClickScope can recreate the missing
folder tree and put the wallpaper back.
"""
import ctypes
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import zipfile

from appdata import (IS_WINDOWS, NO_WINDOW, SNAPSHOT_DIR, drive_info, ensure_dirs, fixed_drives,
                     human_date, human_size, known_folders)
from filesearch import SKIP_DIRS, _is_reparse

DNA_FORMAT = "clickscope-dna"
DNA_VERSION = 1
BLUEPRINT_SKIP = set(SKIP_DIRS) | {"program files", "program files (x86)"}
STYLE_NAMES = {"10": "Fill", "6": "Fit", "2": "Stretch", "0": "Center", "22": "Span", "1": "Tile"}


# ------------------------------------------------------------------ wallpaper
def _wallpaper_registry():
    style, tile = "10", "0"
    if not IS_WINDOWS:
        return style, tile
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            try:
                style = str(winreg.QueryValueEx(k, "WallpaperStyle")[0])
            except OSError:
                pass
            try:
                tile = str(winreg.QueryValueEx(k, "TileWallpaper")[0])
            except OSError:
                pass
    except OSError:
        pass
    return style, tile


def current_wallpaper():
    """The image Windows is showing now, its path, style and file size (or None)."""
    if not IS_WINDOWS:
        return None
    try:
        buf = ctypes.create_unicode_buffer(32768)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buf), buf, 0)  # SPI_GETDESKWALLPAPER
        path = buf.value if ok and buf.value else ""
    except Exception:
        path = ""
    if not path or not os.path.isfile(path):
        return None
    style, tile = _wallpaper_registry()
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return dict(path=path, name=os.path.basename(path), ext=os.path.splitext(path)[1].lower() or ".jpg",
                style="Tile" if tile == "1" else STYLE_NAMES.get(style, "Fill"), style_raw=style,
                tile=tile, size=size, size_text=human_size(size))


def set_wallpaper(path, style="Fill", tile=False):
    """Apply a wallpaper and its fit. Returns True on success."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return False
    if not IS_WINDOWS:
        return False
    style_map = {v: k for k, v in STYLE_NAMES.items()}
    raw = "1" if tile or style == "Tile" else style_map.get(style, "10")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "WallpaperStyle", 0, winreg.REG_SZ, raw)
            winreg.SetValueEx(k, "TileWallpaper", 0, winreg.REG_SZ, "1" if (tile or style == "Tile") else "0")
    except OSError:
        pass
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(0x0014, 0, path, 0x01 | 0x02)  # SPI_SETDESKWALLPAPER
        return bool(ok)
    except Exception:
        return False


def make_thumbnail(src, out_png, width=640, height=360):
    """Cover-crop a 16:9 preview. Pillow when available, otherwise System.Drawing."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(src).convert("RGB")
        img = ImageOps.fit(img, (width, height), method=Image.LANCZOS)
        os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
        img.save(out_png, "PNG")
        return True
    except Exception:
        pass
    if not IS_WINDOWS:
        return False
    try:
        env = os.environ.copy()
        env["CS_SRC"], env["CS_OUT"] = src, out_png
        script = (
            "Add-Type -AssemblyName System.Drawing;"
            "$src=$env:CS_SRC; $out=$env:CS_OUT;"
            "$img=[System.Drawing.Image]::FromFile($src);"
            f"$w={width}; $h={height};"
            "$r=[Math]::Max($w/$img.Width,$h/$img.Height);"
            "$nw=[int][Math]::Ceiling($img.Width*$r); $nh=[int][Math]::Ceiling($img.Height*$r);"
            "$bmp=New-Object System.Drawing.Bitmap $w,$h;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic;"
            "$g.DrawImage($img,[int](($w-$nw)/2),[int](($h-$nh)/2),$nw,$nh);"
            "$bmp.Save($out,[System.Drawing.Imaging.ImageFormat]::Png);"
            "$g.Dispose(); $bmp.Dispose(); $img.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       creationflags=NO_WINDOW, timeout=30, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.isfile(out_png)
    except Exception:
        return False


# ----------------------------------------------------------------- snapshots
def _new_snapshot_dir(prefix="dna"):
    ensure_dirs()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(SNAPSHOT_DIR, f"{prefix}-{stamp}")
    path, i = base, 1
    while os.path.exists(path):
        path = f"{base}-{i}"
        i += 1
    os.makedirs(path)
    return path


def _meta_record(folder):
    meta_path = os.path.join(folder, "meta.json")
    data_path = os.path.join(folder, "blueprint.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = None
    if meta is None:
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            meta = _meta_from_data(data)
        except (OSError, ValueError):
            return None
    meta["dir"] = folder
    meta["data_path"] = data_path
    meta["meta_path"] = meta_path
    return meta


def _meta_from_data(data):
    wp = data.get("wallpaper") or {}
    return dict(created=data.get("created", ""), created_ts=data.get("created_ts", 0),
                pc=data.get("pc", "This PC"), folders=data.get("folder_count", len(data.get("folders") or [])),
                drives=len(data.get("drives") or []), wallpaper=bool(wp.get("file")),
                wallpaper_name=wp.get("name", ""), size=0, kind=data.get("kind", "snapshot"))


def list_snapshots():
    ensure_dirs()
    out = []
    try:
        entries = os.listdir(SNAPSHOT_DIR)
    except OSError:
        return out
    for name in entries:
        folder = os.path.join(SNAPSHOT_DIR, name)
        if not os.path.isdir(folder):
            continue
        rec = _meta_record(folder)
        if rec:
            rec.setdefault("name", name)
            out.append(rec)
    out.sort(key=lambda r: (r.get("created_ts") or 0, r.get("created") or ""), reverse=True)
    return out


def load_snapshot(record_or_path):
    path = record_or_path
    if isinstance(record_or_path, dict):
        path = record_or_path.get("data_path") or os.path.join(record_or_path.get("dir", ""), "blueprint.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != DNA_FORMAT:
        raise ValueError("This file isn't a ClickScope blueprint.")
    return data


def delete_snapshot(record):
    folder = record.get("dir") if isinstance(record, dict) else record
    if folder and os.path.isdir(folder) and os.path.dirname(os.path.abspath(folder)) == os.path.abspath(SNAPSHOT_DIR):
        try:
            shutil.rmtree(folder)
            return True
        except OSError:
            return False
    return False


# -------------------------------------------------------------------- capture
def scan_folders(roots=None, progress_cb=None, stop_event=None):
    roots = [r for r in (roots or fixed_drives()) if os.path.isdir(r)]
    folders, seen = [], set()
    count = 0

    def add(path):
        key = path.lower()
        if key not in seen:
            seen.add(key)
            folders.append(path)

    for root in roots:
        root = os.path.abspath(root)
        add(root)
        stack = [root]
        while stack:
            if stop_event is not None and stop_event.is_set():
                break
            d = stack.pop()
            try:
                with os.scandir(d) as it:
                    for e in it:
                        try:
                            if _is_reparse(e) or not e.is_dir(follow_symlinks=False):
                                continue
                            if e.name.lower() in BLUEPRINT_SKIP:
                                continue
                            p = os.path.join(d, e.name)
                            add(p)
                            stack.append(p)
                        except OSError:
                            continue
            except OSError:
                continue
            count += 1
            if progress_cb and count % 40 == 0:
                try:
                    progress_cb(len(folders), d)
                except Exception:
                    pass
    return folders


def _copy_wallpaper(folder, progress_cb=None):
    info = current_wallpaper()
    if not info:
        return None
    ext = info["ext"] if info["ext"] in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff") else ".jpg"
    dest = os.path.join(folder, "wallpaper" + ext)
    try:
        shutil.copy2(info["path"], dest)
    except OSError:
        return None
    make_thumbnail(dest, os.path.join(folder, "wallpaper_preview.png"))
    return dict(file=os.path.basename(dest), name=info["name"], original_path=info["path"],
                style=info["style"], style_raw=info.get("style_raw", "10"), tile=info.get("tile", "0"),
                size=os.path.getsize(dest))


def capture(progress_cb=None, include_wallpaper=True, stop_event=None, extra_roots=None):
    """Take a new PC DNA snapshot. Returns its metadata record."""
    folder = _new_snapshot_dir("dna")
    if progress_cb:
        try:
            progress_cb(0, "Reading your drives\u2026")
        except Exception:
            pass
    roots = list(dict.fromkeys(fixed_drives() + list(extra_roots or [])))
    folders = scan_folders(roots, progress_cb, stop_event)
    if stop_event is not None and stop_event.is_set():
        shutil.rmtree(folder, ignore_errors=True)
        return None
    if progress_cb:
        try:
            progress_cb(len(folders), "Saving your blueprint\u2026")
        except Exception:
            pass
    now = datetime.datetime.now()
    data = dict(format=DNA_FORMAT, version=DNA_VERSION,
                created=now.strftime("%d %b %Y, %H:%M"), created_ts=int(now.timestamp()),
                pc=os.environ.get("COMPUTERNAME") or socket.gethostname(),
                user=os.environ.get("USERNAME") or os.path.basename(os.path.expanduser("~")),
                home=os.path.expanduser("~"), drives=drive_info(), folders=folders,
                folder_count=len(folders), wallpaper=None)
    if include_wallpaper:
        data["wallpaper"] = _copy_wallpaper(folder, progress_cb)
    data_path = os.path.join(folder, "blueprint.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    meta = _meta_from_data(data)
    meta["size"] = os.path.getsize(data_path)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    rec = _meta_record(folder)
    return rec


def save_wallpaper_copy():
    """Save just the current wallpaper (no folder snapshot)."""
    folder = _new_snapshot_dir("wallpaper")
    info = _copy_wallpaper(folder)
    if not info:
        shutil.rmtree(folder, ignore_errors=True)
        return None
    data = dict(format=DNA_FORMAT, version=DNA_VERSION, kind="wallpaper",
                created=datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
                created_ts=int(datetime.datetime.now().timestamp()),
                pc=os.environ.get("COMPUTERNAME") or socket.gethostname(),
                user=os.environ.get("USERNAME") or "", home=os.path.expanduser("~"),
                drives=drive_info(), folders=[], folder_count=0, wallpaper=info)
    with open(os.path.join(folder, "blueprint.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    meta = _meta_from_data(data)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return _meta_record(folder)


def snapshot_thumbnail(record):
    if not record:
        return None
    for n in ("wallpaper_preview.png",):
        p = os.path.join(record.get("dir", ""), n)
        if os.path.isfile(p):
            return p
    wp = record.get("wallpaper_name") or ""
    folder = record.get("dir", "")
    if wp:
        p = os.path.join(folder, "wallpaper" + os.path.splitext(wp)[1].lower())
        thumb = os.path.join(folder, "wallpaper_preview.png")
        if os.path.isfile(p) and make_thumbnail(p, thumb):
            return thumb
    return None


def wallpaper_path(record):
    wp = record.get("wallpaper_name") or ""
    if not wp:
        return None
    p = os.path.join(record.get("dir", ""), "wallpaper" + os.path.splitext(wp)[1].lower())
    return p if os.path.isfile(p) else None


def wallpaper_style(record):
    return "Fill"


# --------------------------------------------------------------------- export
def export_snapshot(record, out_path):
    """Write one .clickdna zip: blueprint.json, wallpaper and a small README."""
    folder = record["dir"]
    data = load_snapshot(record)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("blueprint.json", json.dumps(data, ensure_ascii=False, indent=1))
        wp = wallpaper_path(record)
        if wp:
            z.write(wp, os.path.basename(wp))
            thumb = snapshot_thumbnail(record)
            if thumb and os.path.isfile(thumb):
                z.write(thumb, "wallpaper_preview.png")
        readme = (
            "ClickScope blueprint\r\n"
            f"Created {data.get('created', '')} on {data.get('pc', '')}\r\n\r\n"
            "This file contains the folder structure of that PC and, when available, its wallpaper.\r\n"
            "It contains no document contents.\r\n\r\n"
            "Open ClickScope on the new PC, go to Blueprint, choose Import, then restore folders\r\n"
            "and wallpaper. Windows and Program Files are left out: reinstall those apps normally.\r\n"
        )
        z.writestr("README.txt", readme)
    return out_path


def import_snapshot(path):
    """Import a .clickdna (or plain blueprint.json) into the local snapshot list."""
    folder = _new_snapshot_dir("imported")
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                try:
                    raw = z.read("blueprint.json")
                except KeyError:
                    raise ValueError("No blueprint.json inside that file.")
                data = json.loads(raw.decode("utf-8"))
                if data.get("format") != DNA_FORMAT:
                    raise ValueError("This file isn't a ClickScope blueprint.")
                with open(os.path.join(folder, "blueprint.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                for name in z.namelist():
                    base = os.path.basename(name)
                    if base.lower().startswith("wallpaper.") and base.lower() != "wallpaper_preview.png":
                        with z.open(name) as src, open(os.path.join(folder, base), "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        break
        else:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("format") != DNA_FORMAT:
                raise ValueError("This file isn't a ClickScope blueprint.")
            with open(os.path.join(folder, "blueprint.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        wp = data.get("wallpaper") or {}
        if wp.get("file"):
            p = os.path.join(folder, "wallpaper" + os.path.splitext(wp["file"])[1].lower())
            if os.path.isfile(p):
                make_thumbnail(p, os.path.join(folder, "wallpaper_preview.png"))
        meta = _meta_from_data(data)
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return _meta_record(folder)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


# -------------------------------------------------------------------- restore
def _map_folder(path, old_home, new_home, drive_letters):
    p = os.path.normpath(path)
    if old_home:
        oh = os.path.normpath(old_home)
        if p.lower() == oh.lower():
            return new_home
        prefix = oh.rstrip("\\/") + os.sep
        if p.lower().startswith(prefix.lower()):
            return os.path.join(new_home, p[len(prefix):])
    drive, rest = os.path.splitdrive(p)
    letter = drive.upper()
    if letter in drive_letters:
        return p
    safe_letter = (letter.rstrip(":") or "PC")
    fallback = os.path.join(new_home, "Restored", safe_letter)
    return os.path.join(fallback, rest.lstrip("\\/"))


def folder_plan(data, new_home=None):
    """Preview where each folder would be recreated: [(old, new)]."""
    new_home = new_home or os.path.expanduser("~")
    old_home = data.get("home") or ""
    have = {d["letter"].upper() for d in drive_info()}
    # A drive letter counted as present if the root exists, even if drive_info is unavailable.
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if os.path.isdir(letter + ":\\"):
            have.add(letter + ":")
    out, seen = [], set()
    for p in data.get("folders") or []:
        try:
            new = _map_folder(p, old_home, new_home, have)
        except Exception:
            continue
        key = new.lower()
        if key not in seen:
            seen.add(key)
            out.append((p, new))
    return out


def restore_folders(data, new_home=None, progress_cb=None, stop_event=None):
    """Create missing folders. Existing folders and files are never touched."""
    plan = folder_plan(data, new_home)
    created = existing = 0
    errors = []
    for i, (_, new) in enumerate(plan):
        if stop_event is not None and stop_event.is_set():
            break
        if os.path.isdir(new):
            existing += 1
        else:
            try:
                os.makedirs(new, exist_ok=True)
                created += 1
            except OSError as e:
                if len(errors) < 5:
                    errors.append(f"{new}: {e}")
        if progress_cb and i % 50 == 0:
            try:
                progress_cb(i + 1, len(plan))
            except Exception:
                pass
    return dict(created=created, existing=existing, total=len(plan), errors=errors)


def restore_wallpaper(record):
    p = wallpaper_path(record)
    if not p:
        return False
    style = "Fill"
    try:
        data = load_snapshot(record)
        style = (data.get("wallpaper") or {}).get("style", "Fill")
    except Exception:
        pass
    return set_wallpaper(p, style)


def stats_text(record):
    if not record:
        return ""
    bits = [f"{record.get('folders', 0):,} folder{'s' if record.get('folders', 0) != 1 else ''}"]
    if record.get("drives"):
        bits.append(f"{record['drives']} drive{'s' if record['drives'] != 1 else ''}")
    if record.get("wallpaper"):
        bits.append("wallpaper")
    return "  \u00b7  ".join(bits)


def drive_rows():
    return drive_info()
