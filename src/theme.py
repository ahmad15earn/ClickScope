"""ClickScope design tokens (light theme only)."""
from tkinter import font as tkfont

BG = "#F5F5F7"          # window
SIDEBAR = "#EDEFF3"
CARD = "#FFFFFF"
LINE = "#E7E9EE"        # hairlines
LINE2 = "#D5D9E0"
SHADOW = "#ECEEF3"
TRACK = "#EEF0F4"
TEXT = "#1D1D1F"
SUB = "#6E6E73"
FAINT = "#A1A1A6"
ACCENT = "#00C2E0"      # from the logo
ACCENT_D = "#0690AB"
ACCENT_MID = "#B4EEF8"
ACCENT_SOFT = "#E3F8FC"
GREEN = "#2BC870"
AMBER = "#FF9F0A"
RED = "#FF453A"
INK = "#1D1D1F"
PALETTE = ["#00C2E0", "#5B7CFA", "#8E6CF2", "#F472B6", "#FFB020", "#2FCB9A"]
OTHER = "#C9CED6"
LEVEL = {"tip": ACCENT, "info": "#5B7CFA", "good": GREEN, "warn": AMBER}

SCALE = 1.0
FAMILY = "Segoe UI"


def init(root):
    """Call once after the Tk root exists."""
    global SCALE, FAMILY
    try:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        SCALE = 1.0
    try:
        fams = set(tkfont.families(root))
        for cand in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI"):
            if cand in fams:
                FAMILY = cand
                break
    except Exception:
        pass


def s(n):
    return int(round(n * SCALE))


def F(size, weight="normal"):
    return (FAMILY, size, weight)
