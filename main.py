"""
Requires: psutil, matplotlib  (see requirements.txt)
Optional (Windows only, for live BIOS + Windows Update data): pywin32, wmi
"""

import tkinter as tk
import database as db
from theme import apply_ttk_theme, XP_WINDOW_BG
from pages.home import HomePage
from pages.hardware_check import HardwareCheckPage
from pages.reports import ReportsPage
from pages.command_console import CommandConsolePage
from pages.sound_control import SoundControlPage 

class DiagnosticsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("System Diagnostics Console")
        self.geometry("1060x740")
        self.minsize(920, 640)
        self.configure(bg=XP_WINDOW_BG)
        apply_ttk_theme(self)

        container = tk.Frame(self, bg=XP_WINDOW_BG)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for Page in (HomePage, HardwareCheckPage, CommandConsolePage, ReportsPage, SoundControlPage):
            name = Page.__name__
            frame = Page(container, self)
            self.frames[name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_frame("HomePage")

    def _on_close(self):
        console = self.frames.get("CommandConsolePage")
        if console:
            console.shutdown()
        self.destroy()

    def show_frame(self, name):
        frame = self.frames[name]
        frame.tkraise()
        if name == "ReportsPage":
            frame.reload_list()
        if hasattr(frame, "on_show"):
            frame.on_show()

    def notify_new_report(self):
        reports_page = self.frames.get("ReportsPage")
        if reports_page:
            reports_page.reload_list()


if __name__ == "__main__":
    db.init_db()
    app = DiagnosticsApp()
    app.mainloop()
