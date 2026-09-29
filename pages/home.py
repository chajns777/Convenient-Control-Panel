import time
import tkinter as tk

from theme import (XP_WINDOW_BG, XP_TASKBAR_BG, XP_GREEN_START, FONT_UI,
                    FONT_UI_BOLD, FONT_HEADER, gradient_rect)

ICON_BG = "#6E97C4"


class HomePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller

        self.desktop = tk.Canvas(self, highlightthickness=0, bd=0)
        self.desktop.pack(fill="both", expand=True, side="top")
        self.desktop.bind("<Configure>", self._draw_desktop)

        self._make_icon("\U0001F5A5", "Hardware\nCheck", 40,
                         lambda: self.controller.show_frame("HardwareCheckPage"))
        self._make_icon("\U0001F4C1", "Report\nArchive", 160,
                         lambda: self.controller.show_frame("ReportsPage"))

        self._build_taskbar()

    def _draw_desktop(self, event=None):
        c = self.desktop
        c.delete("bg")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 2 or h < 2:
            return
        gradient_rect(c, 0, 0, w, h, "#3A6EA5", "#A9C8E8", vertical=True)
        c.create_text(w // 2, 36, text="System Diagnostics Console",
                       font=FONT_HEADER, fill="white", tags="bg")
        c.create_text(w // 2, 62, text="Windows XP-styled hardware utility",
                       font=FONT_UI, fill="#EAF2FB", tags="bg")
        c.tag_lower("bg")

    def _make_icon(self, glyph, label, x, command):
        f = tk.Frame(self.desktop, bg=ICON_BG, cursor="hand2",
                     highlightbackground="#1F3F63", highlightthickness=1)
        self.desktop.create_window(x, 100, anchor="n", window=f, width=100)
        icon_lbl = tk.Label(f, text=glyph, font=("Segoe UI Emoji", 30), bg=ICON_BG, fg="white")
        icon_lbl.pack(pady=(8, 0))
        text_lbl = tk.Label(f, text=label, font=FONT_UI_BOLD, fg="white", bg=ICON_BG, justify="center")
        text_lbl.pack(pady=(2, 8))
        for w in (f, icon_lbl, text_lbl):
            w.bind("<Button-1>", lambda e: command())

    def _build_taskbar(self):
        bar = tk.Frame(self, bg=XP_TASKBAR_BG, height=34)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        start = tk.Button(bar, text="\u25B6 start", font=FONT_UI_BOLD, bg=XP_GREEN_START,
                           fg="white", relief="raised", bd=2, padx=10,
                           command=lambda: self.controller.show_frame("HardwareCheckPage"))
        start.pack(side="left", padx=3, pady=2)

        self.clock_lbl = tk.Label(bar, font=FONT_UI, bg="#1941A5", fg="white", padx=8)
        self.clock_lbl.pack(side="right", fill="y", padx=3, pady=3)
        self._tick_clock()

    def _tick_clock(self):
        self.clock_lbl.config(text=time.strftime("%I:%M %p"))
        self.after(1000, self._tick_clock)
