"""Global shortcut tests: parsing, validation and a real RegisterHotKey round trip.

Run:
    python tests/test_hotkey.py
"""
import ctypes
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import hotkey as H  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    # Canonical forms and formatting.
    check(H.normalize_shortcut("ctrl+alt+space") == "Ctrl+Alt+Space", "lowercase parse")
    check(H.normalize_shortcut("  SHIFT + Ctrl + f9 ") == "Ctrl+Shift+F9", "order and case")
    check(H.normalize_shortcut("win+shift+s") == "Shift+Win+S", "win modifier")
    check(H.normalize_shortcut("Ctrl+Alt+PageUp") == "Ctrl+Alt+PageUp", "named key")
    check(H.normalize_shortcut("ctrl+alt+1") == "Ctrl+Alt+1", "digit key")
    check(H.normalize_shortcut("Ctrl+Alt+F24") == "Ctrl+Alt+F24", "function key")
    check(H.pretty_shortcut("ctrl+alt+space") == "Ctrl + Alt + Space", "pretty form")
    check(H.pretty_shortcut("not a shortcut") == "not a shortcut", "pretty fallback")

    for bad in ("", "   ", "Space", "Ctrl", "Ctrl+Alt", "Ctrl+Shift", "Shift+A",
                "Ctrl+Banana", "Ctrl++X", "Ctrl+Alt+A+B"):
        try:
            H.normalize_shortcut(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should be rejected")

    print("parsing OK")

    if sys.platform != "win32":
        print("hotkey OK (registration skipped, not Windows)")
        return 0

    fired = threading.Event()
    hk = H.GlobalHotkey(fired.set)
    spec = "Ctrl+Alt+Shift+F13"
    ok, error = hk.start(spec)
    check(ok, f"could not register {spec}: {error}")
    check(hk.active, "hotkey should report active")

    # Deliver the same message Windows sends for a real key press.
    check(ctypes.windll.user32.PostThreadMessageW(hk._tid, H.WM_HOTKEY, 1, 0), "post failed")
    check(fired.wait(3.0), "hotkey callback did not fire")

    hk.stop()
    check(not hk.active, "hotkey should be inactive after stop")

    ok, error = hk.start("Ctrl+Alt+Shift+F14")
    check(ok, f"restart after stop failed: {error}")
    hk.stop()

    bad_ok, bad_error = hk.start("NotAKey")
    check(not bad_ok and bad_error, "invalid spec should report an error")

    fresh = H.GlobalHotkey()
    ok, error = fresh.start(spec)
    check(ok, f"fresh instance registration failed: {error}")
    fresh.stop()
    print("hotkey OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
