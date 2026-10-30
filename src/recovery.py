"""Software recovery: download installers for a list of apps into one folder, in the background.

Uses Windows Package Manager (winget) so every download comes from the official winget repository and is
hash-verified by winget itself. Nothing is installed. Apps without a winget source (paid, Store-only, niche)
are reported as "no automatic source" so the user can fetch them manually.
"""
import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(KB|MB|GB)\s*/\s*(\d+(?:\.\d+)?)\s*(KB|MB|GB)", re.I)
UNIT = {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}

QUEUED, RESOLVING, DOWNLOADING, DONE, FAILED, NOSOURCE, CANCELLED = (
    "queued", "resolving", "downloading", "done", "failed", "nosource", "cancelled")


def winget_path():
    return shutil.which("winget")


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(". ")[:80] or "app"


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def parse_table(text):
    """Parse a winget table (list/search) into [{'Name':..,'Id':..,...}] using the header's column positions."""
    lines = [l.rstrip("\r") for l in text.splitlines()]
    hi = next((i for i, l in enumerate(lines) if re.search(r"\bName\b", l) and re.search(r"\bId\b", l)), None)
    if hi is None:
        return []
    header = lines[hi]
    cols = [(m.group(0), m.start()) for m in re.finditer(r"\S+(?: \S+)*", header)]
    rows = []
    for l in lines[hi + 1:]:
        if not l.strip() or set(l.strip()) <= set("-\u2500 "):
            continue
        row = {}
        for k, (name, start) in enumerate(cols):
            end = cols[k + 1][1] if k + 1 < len(cols) else len(l)
            row[name] = l[start:end].strip()
        if row.get("Name") and row.get("Id"):
            rows.append(row)
    return rows


def parse_progress(buf):
    """Latest 'x MB / y MB' from winget's progress output -> 0..1 (or None)."""
    ms = SIZE_RE.findall(buf[-600:])
    if not ms:
        return None
    a, ua, b, ub = ms[-1]
    done, total = float(a) * UNIT[ua.upper()], float(b) * UNIT[ub.upper()]
    return clamp01(done / total) if total else None


def clamp01(v):
    return max(0.0, min(1.0, v))


def run_cmd(cmd, on_chunk=None, proc_holder=None):
    """Run a command without a console window, streaming output. Returns (returncode, full_text)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    if proc_holder is not None:
        proc_holder["p"] = p
    text = ""
    while True:
        chunk = p.stdout.read1(512) if hasattr(p.stdout, "read1") else p.stdout.read(512)
        if not chunk:
            break
        s = chunk.decode("utf-8", "ignore")
        text += s
        if on_chunk:
            on_chunk(s)
    return p.wait(), text


class Job:
    def __init__(self, name):
        self.name, self.id = name, None
        self.status, self.progress, self.message, self.folder = QUEUED, 0.0, "Waiting", ""


class RecoveryManager:
    def __init__(self, folder, names, ids=None, runner=None):
        self.folder = folder
        self.jobs = [Job(n) for n in names]
        self.ids = dict(ids or {})            # cached name -> winget id
        self.runner = runner or run_cmd
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.worker = None
        self.cancelled = False
        self._proc = {}
        self._installed = None
        self.winget = winget_path() if runner is None else "winget"

    # ------------------------------------------------------------- control
    def start(self):
        os.makedirs(self.folder, exist_ok=True)
        for j in self.jobs:
            self.q.put(j)
        self._ensure_worker()

    def retry(self, job):
        if job.status in (FAILED, NOSOURCE, CANCELLED):
            job.status, job.progress, job.message = QUEUED, 0.0, "Waiting"
            self.cancelled = False
            self.q.put(job)
            self._ensure_worker()

    def retry_failed(self):
        for j in self.jobs:
            if j.status in (FAILED, CANCELLED):
                self.retry(j)

    def cancel(self):
        self.cancelled = True
        p = self._proc.get("p")
        if p:
            try:
                p.terminate()
            except Exception:
                pass

    def _ensure_worker(self):
        with self.lock:
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()

    @property
    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def counts(self):
        c = {}
        for j in self.jobs:
            c[j.status] = c.get(j.status, 0) + 1
        return c

    # ------------------------------------------------------------ resolving
    def _installed_map(self):
        """name -> winget id for software already installed on this PC (one `winget list` call)."""
        if self._installed is None:
            self._installed = {}
            try:
                rc, out = self.runner([self.winget, "list", "--accept-source-agreements", "--disable-interactivity"])
                for r in parse_table(out):
                    self._installed[norm(r["Name"])] = r["Id"]
            except Exception:
                pass
        return self._installed

    def _resolve(self, job):
        if job.name in self.ids:
            return self.ids[job.name]
        inst = self._installed_map()
        if norm(job.name) in inst:
            return inst[norm(job.name)]
        try:
            rc, out = self.runner([self.winget, "search", job.name, "--count", "5", "--accept-source-agreements",
                                   "--disable-interactivity"])
            for r in parse_table(out):
                if norm(r["Name"]) == norm(job.name):
                    return r["Id"]
        except Exception:
            pass
        return None

    # --------------------------------------------------------------- worker
    def _run(self):
        while True:
            try:
                job = self.q.get_nowait()
            except queue.Empty:
                break
            if self.cancelled:
                job.status, job.message = CANCELLED, "Cancelled"
                continue
            self._do(job)
        self.write_index()

    def _do(self, job):
        if not self.winget:
            job.status = FAILED
            job.message = ("Windows Package Manager (winget) was not found. Install \u201cApp Installer\u201d "
                           "from the Microsoft Store, then press Retry.")
            return
        job.status, job.message = RESOLVING, "Looking for the official installer\u2026"
        wid = self._resolve(job)
        if not wid:
            job.status, job.message = NOSOURCE, "No automatic source found. Download it manually from the vendor."
            return
        job.id = self.ids[job.name] = wid
        job.folder = os.path.join(self.folder, safe_name(job.name))
        os.makedirs(job.folder, exist_ok=True)
        job.status, job.progress, job.message = DOWNLOADING, 0.0, "Starting download\u2026"
        buf = []

        def on_chunk(s):
            buf.append(s)
            p = parse_progress("".join(buf[-6:]))
            if p is not None:
                job.progress = p
                job.message = f"Downloading\u2026 {p:.0%}"
        cmd = [self.winget, "download", "--id", wid, "--exact", "--download-directory", job.folder,
               "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]
        try:
            rc, out = self.runner(cmd, on_chunk, self._proc) if self.runner is run_cmd else self.runner(cmd, on_chunk)
        except Exception as e:
            rc, out = 1, str(e)
        if self.cancelled:
            job.status, job.message = CANCELLED, "Cancelled"
        elif rc == 0 and os.path.isdir(job.folder) and os.listdir(job.folder):
            job.status, job.progress, job.message = DONE, 1.0, "Downloaded"
        else:
            lines = [l.strip() for l in out.replace("\r", "\n").splitlines() if l.strip() and not set(l.strip()) <= set("-\\|/ ")]
            job.status, job.message = FAILED, "Failed: " + (lines[-1][:120] if lines else f"exit code {rc}")

    # ---------------------------------------------------------------- index
    def write_index(self):
        try:
            os.makedirs(self.folder, exist_ok=True)
            lines = [f"ClickScope software recovery  -  {datetime.date.today():%Y-%m-%d}", "",
                     "Each folder holds the official installer for one app. Run them to reinstall.", ""]
            for j in self.jobs:
                files = os.listdir(j.folder) if j.folder and os.path.isdir(j.folder) else []
                mark = {"done": "[x]", "nosource": "[?]"}.get(j.status, "[ ]")
                lines.append(f"{mark} {j.name}  -  {j.status}" + (f"  ({', '.join(files[:3])})" if files else ""))
                if j.status in (FAILED, NOSOURCE):
                    lines.append(f"      {j.message}")
            with open(os.path.join(self.folder, "RECOVERY.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            pass
