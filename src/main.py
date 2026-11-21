"""ClickScope entry point.

Flags:
  --minimized   start in the taskbar (used by "Start with Windows")
  --demo        use a separate sample-safe folder instead of your real index
  --smoke       close automatically after a moment (development check)
"""
import ctypes
import os
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox

_mutex = None


def _single_instance(name):
    global _mutex
    if not sys.platform == "win32":
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        _mutex = k32.CreateMutexW(None, False, name)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _center(root, width, height):
    try:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(width, sw - 60), min(height, sh - 80)
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20)
        root.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        root.geometry(f"{width}x{height}")


def main():
    demo = "--demo" in sys.argv
    if demo and "CLICKSCOPE_HOME" not in os.environ:
        os.environ["CLICKSCOPE_HOME"] = os.path.join(tempfile.gettempdir(), "ClickScopeDemo")
    if "--smoke" in sys.argv and "CLICKSCOPE_HOME" not in os.environ:
        os.environ["CLICKSCOPE_HOME"] = os.path.join(tempfile.gettempdir(), "ClickScopeSmoke")

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ClickScope.Demo" if demo else "ClickScope.App")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not _single_instance("Local\\ClickScope2Demo" if demo else "Local\\ClickScope2SingleInstance"):
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("ClickScope", "ClickScope is already running.\nCheck your taskbar.")
        r.destroy()
        return

    import appdata as A
    import theme as T
    import ui

    A.ensure_dirs()
    root = tk.Tk()
    root.withdraw()
    T.init(root)
    root.title("ClickScope" + (" \u2013 Demo" if demo else ""))
    _center(root, T.s(1210), T.s(825))
    root.minsize(min(T.s(1020), root.winfo_screenwidth() - 60),
                 min(T.s(700), root.winfo_screenheight() - 80))

    state = A.State()
    index = ui_index = None
    try:
        from filesearch import FileIndex
        index = ui_index = FileIndex(extra_roots=state.index_roots())
    except Exception as e:
        messagebox.showerror("ClickScope", f"ClickScope could not open its local index:\n{e}")
        root.destroy()
        return

    app = ui.App(root, state, index)
    root.deiconify()
    if "--minimized" in sys.argv:
        root.iconify()
    if "--smoke" in sys.argv:
        root.after(1800, app.quit)
    try:
        root.mainloop()
    finally:
        try:
            ui_index.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
