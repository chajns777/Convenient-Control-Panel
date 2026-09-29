import tkinter as tk
from tkinter import ttk

XP_BLUE_DARK    = "#3A4556"  
XP_BLUE_LIGHT   = "#8FAFCB"
XP_BLUE_ACTIVE  = "#7FA1DB"
XP_TITLEBAR_TEXT = "#FFFFFF"
XP_WINDOW_BG    = "#C7CBD1"  
XP_FIELD_BG     = "#E4E7EA"  
XP_BORDER_DARK  = "#7A7F87"  
XP_BORDER_LIGHT = "#EDEFF1"
XP_GREEN_START  = "#3C8C3C"
XP_TASKBAR_BG   = "#7FA1DB"
XP_SELECT_BG    = "#7FA1DB"
XP_TEXT         = "#232629"  
XP_OK_GREEN     = "#1B7A1B"
XP_WARN_ORANGE  = "#B36A00"
XP_ALERT_RED    = "#B00000"

BTN_BG          = "#DDE1E5"  
BTN_BG_HOVER    = "#C3D3E5"  
BTN_BG_ACTIVE   = XP_BLUE_ACTIVE
TAB_BG_INACTIVE = "#B9BFC6"
TAB_BG_ACTIVE   = XP_WINDOW_BG
TAB_TEXT        = "#2A2E33"

FONT_UI      = ("Tahoma", 9)
FONT_UI_BOLD = ("Tahoma", 9, "bold")
FONT_TITLE   = ("Tahoma", 11, "bold")
FONT_MONO    = ("Consolas", 9)
FONT_HEADER  = ("Tahoma", 15, "bold")


def apply_ttk_theme(root):

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=XP_WINDOW_BG)
    style.configure("TLabel", background=XP_WINDOW_BG, font=FONT_UI, foreground=XP_TEXT)
    style.configure("Header.TLabel", font=FONT_HEADER, background=XP_WINDOW_BG, foreground=XP_BLUE_DARK)
    style.configure("TButton", font=FONT_UI, padding=4, background=BTN_BG,
                     foreground=XP_TEXT, borderwidth=1)
    style.map("TButton",
              background=[("pressed", BTN_BG_ACTIVE), ("active", BTN_BG_HOVER)],
              foreground=[("disabled", "#9AA0A6")])

    style.configure("TNotebook", background=XP_WINDOW_BG, tabmargins=(2, 4, 2, 0))
    style.configure("TNotebook.Tab", font=FONT_UI, padding=(12, 5),
                     background=TAB_BG_INACTIVE, foreground=TAB_TEXT)
    style.map("TNotebook.Tab",
              background=[("selected", TAB_BG_ACTIVE), ("active", BTN_BG_HOVER)],
              foreground=[("selected", XP_BLUE_DARK)],
              expand=[("selected", (1, 1, 1, 0))])

    style.configure("Treeview", background=XP_FIELD_BG, fieldbackground=XP_FIELD_BG,
                     font=FONT_UI, rowheight=22, borderwidth=1)
    style.configure("Treeview.Heading", font=FONT_UI_BOLD, background=XP_BLUE_LIGHT,
                     foreground="white", relief="raised")
    style.map("Treeview", background=[("selected", XP_SELECT_BG)], foreground=[("selected", "white")])

    style.configure("Horizontal.TProgressbar", troughcolor=XP_FIELD_BG, background=XP_BLUE_ACTIVE)
    return style


def gradient_rect(canvas, x1, y1, x2, y2, color1, color2, vertical=True, tags=()):

    r1, g1, b1 = canvas.winfo_rgb(color1)
    r2, g2, b2 = canvas.winfo_rgb(color2)
    span = (y2 - y1) if vertical else (x2 - x1)
    steps = max(2, int(span))
    for i in range(steps):
        ratio = i / steps
        nr = int(r1 + (r2 - r1) * ratio) >> 8
        ng = int(g1 + (g2 - g1) * ratio) >> 8
        nb = int(b1 + (b2 - b1) * ratio) >> 8
        color = f"#{nr:02x}{ng:02x}{nb:02x}"
        if vertical:
            canvas.create_line(x1, y1 + i, x2, y1 + i, fill=color, tags=tags)
        else:
            canvas.create_line(x1 + i, y1, x1 + i, y2, fill=color, tags=tags)


def make_titlebar(parent, text, icon_text="\U0001F5A5"):

    bar_h = 30
    canvas = tk.Canvas(parent, height=bar_h, highlightthickness=0, bd=0)
    canvas.pack(fill="x", side="top")

    def redraw(event=None):
        canvas.delete("all")
        w = canvas.winfo_width()
        if w < 2:
            return
        gradient_rect(canvas, 0, 0, w, bar_h, XP_BLUE_DARK, XP_BLUE_LIGHT, vertical=False)
        canvas.create_text(10, bar_h // 2, anchor="w", text=f"{icon_text}  {text}",
                            fill=XP_TITLEBAR_TEXT, font=FONT_UI_BOLD)

    canvas.bind("<Configure>", redraw)
    return canvas


def etched_panel(parent, title=None, **kwargs):

    outer = tk.Frame(parent, bg=XP_WINDOW_BG, **kwargs)
    frame = tk.LabelFrame(outer, text=title or "", bg=XP_WINDOW_BG, fg=XP_BLUE_DARK,
                           font=FONT_UI_BOLD, bd=2, relief="groove", labelanchor="nw")
    frame.pack(fill="both", expand=True, padx=2, pady=2)
    return outer, frame


def xp_button(parent, text, command=None, width=None, bg=BTN_BG, **kw):

    return tk.Button(parent, text=text, command=command, font=FONT_UI,
                      bg=bg, fg=XP_TEXT, activebackground=BTN_BG_HOVER,
                      activeforeground=XP_TEXT, relief="raised",
                      bd=2, padx=8, pady=3, cursor="hand2", width=width, **kw)


def status_dot(parent, status):

    color = {"ok": XP_OK_GREEN, "warn": XP_WARN_ORANGE, "alert": XP_ALERT_RED}.get(status, "#888888")
    c = tk.Canvas(parent, width=14, height=14, bg=XP_WINDOW_BG, highlightthickness=0)
    c.create_oval(2, 2, 12, 12, fill=color, outline=XP_BORDER_DARK)
    return c
