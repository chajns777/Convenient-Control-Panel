import time
import tkinter as tk

from theme import (
    XP_WINDOW_BG, XP_TASKBAR_BG, XP_GREEN_START, FONT_UI, FONT_UI_BOLD, FONT_HEADER, gradient_rect
)

ICON_BG = "#6E97C4"

NAV_ITEMS = [
    ("\U0001F5A5", "Hardware\nCheck", "HardwareCheckPage"),
    ("\U0001F4BB", "Command\nConsole", "CommandConsolePage"),
    ("\U0001F4C1", "Report\nArchive", "ReportsPage"),
    ("\U0001F50A", "Sound\nControl", "SoundControlPage"),
    ("\U0001F4BD", "Disk\nAnalyzer", "DiskAnalyzerPage"),
]

class HomePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller

        self.desktop = tk.Canvas(self, highlightthickness=0, bd=0)
        self.desktop.pack(fill="both", expand=True, side="top")
        
        self.desktop.bind("<Configure>", self._on_desktop_resize)

        self.icon_windows = []
        self._init_icons()
        self._build_taskbar()

    def _init_icons(self):
        """Create icon frames and store their window IDs."""
        for glyph, label, page_name in NAV_ITEMS:
            f = tk.Frame(self.desktop, bg=ICON_BG, cursor="hand2", highlightbackground="#1F3F63", highlightthickness=1)
            
            icon_lbl = tk.Label(f, text=glyph, font=("Segoe UI Emoji", 30), bg=ICON_BG, fg="white")
            icon_lbl.pack(pady=(8, 0))
            text_lbl = tk.Label(f, text=label, font=FONT_UI_BOLD, fg="white", bg=ICON_BG, justify="center")
            text_lbl.pack(pady=(2, 8))

            for w in (f, icon_lbl, text_lbl):
                w.bind("<ButtonRelease-1>", lambda e, p=page_name: self.controller.show_frame(p))

            win_id = self.desktop.create_window(0, 100, anchor="n", window=f, width=100)
            self.icon_windows.append(win_id)

    def _on_desktop_resize(self, event=None):
        """Recalculates positions to center all icons dynamically on window resize."""
        w, h = self.desktop.winfo_width(), self.desktop.winfo_height()
        if w < 2 or h < 2:
            return

        self.desktop.delete("bg")
        gradient_rect(self.desktop, 0, 0, w, h, "#3A6EA5", "#A9C8E8", vertical=True)
        self.desktop.create_text(w // 2, 36, text="System Diagnostics Console", font=FONT_HEADER, fill="white", tags="bg")
        self.desktop.create_text(w // 2, 62, text="Windows XP-styled hardware utility", font=FONT_UI, fill="#EAF2FB", tags="bg")
        self.desktop.tag_lower("bg")

        num_icons = len(self.icon_windows)
        spacing = 130 
        total_width = (num_icons - 1) * spacing
        
        start_x = (w // 2) - (total_width // 2)

        for idx, win_id in enumerate(self.icon_windows):
            icon_x = start_x + (idx * spacing)
            self.desktop.coords(win_id, icon_x, 110)

    def _build_taskbar(self):
        bar = tk.Frame(self, bg=XP_TASKBAR_BG, height=34)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        start = tk.Button(
            bar, text="\u25B6 start", font=FONT_UI_BOLD, bg=XP_GREEN_START, 
            fg="white", relief="raised", bd=2, padx=10, 
            command=lambda: self.controller.show_frame("HardwareCheckPage")
        )
        start.pack(side="left", padx=3, pady=2)

        self.clock_lbl = tk.Label(bar, font=FONT_UI, bg="#1941A5", fg="white", padx=8)
        self.clock_lbl.pack(side="right", fill="y", padx=3, pady=3)
        self._tick_clock()

    def _tick_clock(self):
        self.clock_lbl.config(text=time.strftime("%I:%M %p"))
        self.after(1000, self._tick_clock)
