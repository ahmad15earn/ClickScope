"""The tracking engine must never contain network code. Fails if winhook.py or core.py imports a network module."""
import ast, os, sys
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
FORBIDDEN = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib",
             "xmlrpc", "webbrowser", "websocket", "websockets", "cloud", "recovery", "scanner", "subprocess"}
bad = []
for fn in ("winhook.py", "core.py"):
    tree = ast.parse(open(os.path.join(SRC, fn), encoding="utf-8").read())
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
        for n in names:
            if n.split(".")[0] in FORBIDDEN:
                bad.append(f"{fn}: imports {n}")
assert not bad, bad
print("no-network check OK (winhook.py, core.py)")
