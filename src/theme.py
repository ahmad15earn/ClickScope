"""ClickScope design tokens: a quiet, Apple-inspired light interface."""
from tkinter import font as tkfont

# surfaces
BG = "#F6F6F8"           # window
SIDEBAR = "#F0F0F3"      # navigation rail
CARD = "#FFFFFF"
LINE = "#EAEAEF"         # hairlines
LINE2 = "#D9D9E0"
SHADOW = "#EFF0F4"
TRACK = "#EFEFF3"        # progress / control tracks
HOVER = "#F4F4F7"
SIDEBAR_HOVER = "#E6E6EB"
SIDEBAR_LINE = "#E4E4EA"

# type
TEXT = "#17171A"
SUB = "#696972"
FAINT = "#9A9AA3"

# brand
ACCENT = "#00B5D1"       # from the logo, used for fills, focus and status
ACCENT_D = "#007C94"     # accessible accent text on white
ACCENT_MID = "#A9EAF3"
ACCENT_SOFT = "#E8F9FC"

# semantic
GREEN = "#1F9D68"
GREEN_SOFT = "#E8F7EF"
AMBER = "#B26A00"
AMBER_SOFT = "#FFF4E3"
RED = "#D93843"
RED_SOFT = "#FDECEE"
INK = "#1B1B1E"
WHITE = "#FFFFFF"
FOCUS = "#0094B0"

# extras kept for the original widget library / tests
PALETTE = ["#00B5D1", "#5B7CFA", "#8E6CF2", "#F472B6", "#FFB020", "#2FCB9A"]
OTHER = "#C9CED6"
LEVEL = {"tip": ACCENT, "info": "#5B7CFA", "good": GREEN, "warn": AMBER}

# tinted file glyphs
DOC_FILL, DOC_INK = "#EDF2FF", "#3B63C7"
IMAGE_FILL, IMAGE_INK = "#EAF8F0", "#1F8A57"
VIDEO_FILL, VIDEO_INK = "#F3EDFF", "#6C49C7"
AUDIO_FILL, AUDIO_INK = "#FFF3E6", "#A96206"
ARCHIVE_FILL, ARCHIVE_INK = "#F5F0E9", "#8A6A3C"
APP_FILL, APP_INK = "#EEF1F5", "#4D5664"
CODE_FILL, CODE_INK = "#E9F8F8", "#0B7E8B"
FOLDER_FILL, FOLDER_INK = "#FFF4DC", "#A46E00"
OTHER_FILL, OTHER_INK = "#F1F1F4", "#70707A"

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
