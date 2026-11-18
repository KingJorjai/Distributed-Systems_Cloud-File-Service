"""Shared visual theme for the desktop GUI and the tray icon."""

import tkinter as tk
import tkinter.font as tkfont
import tkinter.ttk as ttk

# EHU / UPV brand palette
EHU_BLUE = "#1565C0"
EHU_BLUE_DARK = "#2E5AAC"
EHU_GREEN = "#5FD790"
EHU_GREEN_DARK = "#3B8719"
EHU_DARK = "#212121"
EHU_CREAM = "#F5F5F0"
EHU_DANGER = "#E42719"
EHU_WARNING = "#C75200"
EHU_INFO = "#2E5AAC"
EHU_GRAY = "#6B6C7E"
EHU_GRAY_LIGHT = "#CDCED9"

BG = EHU_CREAM
FG = EHU_DARK
ACCENT = EHU_BLUE
SUCCESS = EHU_GREEN_DARK
WARNING = EHU_WARNING
DANGER = EHU_DANGER

FONT_STACK = ("EHUSans", "Inter", "Segoe UI", "DejaVu Sans",
              "Helvetica Neue", "Arial")


def pick_font_family():
    try:
        families = set(tkfont.families())
    except Exception:
        families = set()
    for name in FONT_STACK:
        if name in families:
            return name
    return "TkDefaultFont"


def apply(root):
    """Apply the EHU theme to a Tk root window."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    family = pick_font_family()
    style.configure(".", font=(family, 10), background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TButton", padding=(10, 6), font=(family, 10))
    style.configure("Primary.TButton", background=ACCENT, foreground="white")
    style.map("Primary.TButton", background=[("active", EHU_BLUE_DARK)])
    style.configure("TEntry", padding=4)
    style.configure("TCombobox", padding=4)
    style.configure("TNotebook", background=BG)
    style.configure("TNotebook.Tab", padding=(12, 6), font=(family, 10))
    style.map("TNotebook.Tab", background=[("selected", "white")])
    style.configure("Treeview", rowheight=24, font=(family, 10))
    style.configure("Treeview.Heading", font=(family, 10, "bold"))
    style.configure("Status.TLabel", font=(family, 13, "bold"))
    style.configure("Muted.TLabel", foreground=EHU_GRAY)
    root.configure(bg=BG)