"""ClickScope must never contain network code.

Parses every app module and fails if a network import appears. Also checks that the new UI
does not reach back into the retired click-tracking modules.
"""
import ast
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
NETWORK = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib",
           "telnetlib", "xmlrpc", "webbrowser", "websocket", "websockets"}
LEGACY = {"winhook", "core", "cloud", "cloud_config", "recovery", "scanner", "onboarding", "widgets",
          "guide"}
APP = ("appdata.py", "filesearch.py", "installers.py", "blueprint.py", "theme.py", "uikit.py",
       "pages.py", "ui.py", "main.py", "motion.py")

bad, legacy = [], []
for fn in APP:
    path = os.path.join(SRC, fn)
    if not os.path.isfile(path):
        continue
    tree = ast.parse(open(path, encoding="utf-8-sig").read(), filename=fn)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in NETWORK:
                bad.append(f"{fn}: imports {name}")
            if fn in ("pages.py", "ui.py", "main.py") and root in LEGACY:
                legacy.append(f"{fn}: imports {name}")

assert not bad, bad
assert not legacy, legacy
print("no-network check OK:", ", ".join(APP))
