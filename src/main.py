"""ClickScope entry point.  Flags: --minimized (start in taskbar), --demo (sample data, no tracking)."""
import ctypes
import os
import sys
import tkinter as tk
from tkinter import messagebox

_mutex = None


def _single_instance(name):
    global _mutex
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = k32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


class DemoTracker:
    paused = False
    click_count = 0

    def stop(self):
        pass


def main():
    demo = "--demo" in sys.argv
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClickScope.Demo" if demo else "ClickScope.App")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not _single_instance("Local\\ClickScopeDemo" if demo else "Local\\ClickScopeSingleInstance"):
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo("ClickScope", "ClickScope is already running.\nCheck your taskbar.")
        return

    import theme as T
    import ui
    from core import APP_DIR, Store, resource_path, seed_demo

    root = tk.Tk()
    root.title("ClickScope" + (" \u2013 Demo" if demo else ""))
    T.init(root)
    root.geometry(f"{T.s(1120)}x{T.s(740)}")
    root.minsize(T.s(980), T.s(660))
    try:
        root.iconbitmap(resource_path("assets/app.ico"))
    except Exception:
        pass

    if demo:
        os.makedirs(APP_DIR, exist_ok=True)
        path = os.path.join(APP_DIR, "demo.db")
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
        store = Store(path)
        seed_demo(store)
        tracker = DemoTracker()
    else:
        from winhook import Tracker
        store = Store()
        store.first_run()  # starts the 30-day learning window on first launch
        tracker = Tracker(store)
        tracker.start()

    def quit_app():
        tracker.stop()
        root.destroy()

    def on_close():
        """The X button hides the window so tracking continues; Quit in the sidebar exits."""
        if demo:
            return quit_app()
        if store.get("close_hint") != "1":
            store.set("close_hint", "1")
            messagebox.showinfo("ClickScope", "ClickScope keeps counting in the background (minimized to the taskbar).\n\n"
                                              "To exit completely, use \u201cQuit ClickScope\u201d in the sidebar.")
        root.iconify()

    ui.App(root, store, tracker, demo=demo, on_quit=quit_app)
    if "--minimized" in sys.argv and not demo:
        root.iconify()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
