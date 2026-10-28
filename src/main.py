"""ClickScope entry point."""
import ctypes
import sys
import tkinter as tk
from tkinter import messagebox

_mutex = None


def _single_instance():
    global _mutex
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = k32.CreateMutexW(None, False, "Local\\ClickScopeSingleInstance")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClickScope.App")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not _single_instance():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("ClickScope", "ClickScope is already running.\nCheck your taskbar.")
        return

    import ui
    from core import Store, resource_path
    from winhook import Tracker

    root = tk.Tk()
    root.title("ClickScope")
    root.configure(bg=ui.BG)
    ui.init_scale(root)
    root.geometry(f"{ui.s(980)}x{ui.s(700)}")
    root.minsize(ui.s(860), ui.s(620))
    try:
        root.iconbitmap(resource_path("assets/app.ico"))
    except Exception:
        pass

    store = Store()
    tracker = Tracker(store)
    tracker.start()
    ui.App(root, store, tracker)

    if "--minimized" in sys.argv:
        root.iconify()

    def on_close():
        tracker.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
