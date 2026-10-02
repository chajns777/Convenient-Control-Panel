import os
import json
import time
import psutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from theme import (
    XP_WINDOW_BG,
    XP_FIELD_BG,
    XP_SELECT_BG,
    FONT_UI,
    FONT_UI_BOLD,
    FONT_MONO,
    XP_OK_GREEN,
    XP_WARN_ORANGE,
    XP_ALERT_RED,
    make_titlebar,
    etched_panel,
    xp_button,
)

try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False


class SoundControlPage(tk.Frame):
    """
    Windows XP-styled Audio Control Center with Per-App Volume & Focus Mode Profiles
    """
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller

        self.profiles = {
            "Default": {
                "out_vol": 70,
                "in_vol": 80,
                "trigger_app": "None",
                "apps": {"chrome.exe": 80, "spotify.exe": 60, "discord.exe": 80}
            },
            "Focus Mode": {
                "out_vol": 30,
                "in_vol": 0,
                "trigger_app": "code.exe",
                "apps": {"spotify.exe": 20, "discord.exe": 0, "chrome.exe": 0}
            },
            "Gaming / Stream": {
                "out_vol": 100,
                "in_vol": 90,
                "trigger_app": "obs64.exe",
                "apps": {"discord.exe": 100, "chrome.exe": 10}
            }
        }
        self.active_profile_name = "Default"
        self.app_controls = {}

        make_titlebar(self, "Sound & Audio Profile Manager", "\U0001F50A")

        self._build_toolbar()
        self._build_profile_panel()
        self._build_body()

        self._start_process_watcher()

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        bar.pack(fill="x", padx=4, pady=(4, 0))
        
        xp_button(bar, "\u2190 Home", command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)
        xp_button(bar, "\U0001F504 Refresh App List", command=self.refresh_app_mixer).pack(side="left", padx=3, pady=3)

        self.filter_var = tk.StringVar(value="All Process Apps")
        filter_combo = ttk.Combobox(
            bar, textvariable=self.filter_var, 
            values=["All Process Apps", "Active Audio Streams Only"], 
            state="readonly", width=22, font=FONT_UI
        )
        filter_combo.pack(side="right", padx=6, pady=3)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_app_mixer())

    def _build_profile_panel(self):
        outer, panel = etched_panel(self, "Audio Focus & Profile Selector")
        outer.pack(fill="x", padx=4, pady=4)

        tk.Label(panel, text="Active Profile:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(side="left", padx=(10, 5), pady=6)

        self.profile_var = tk.StringVar(value=self.active_profile_name)
        options = list(self.profiles.keys())
        self.profile_menu = tk.OptionMenu(panel, self.profile_var, *options, command=self._on_profile_selected)
        self.profile_menu.config(font=FONT_UI, bg=XP_WINDOW_BG, activebackground=XP_WINDOW_BG, bd=1)
        self.profile_menu.pack(side="left", padx=5, pady=6)

        self.profile_status_lbl = tk.Label(
            panel, 
            text="[Mode: Manual]", 
            font=FONT_UI, 
            fg=XP_OK_GREEN, 
            bg=XP_WINDOW_BG
        )
        self.profile_status_lbl.pack(side="left", padx=15)

    def _build_body(self):
        body = tk.Frame(self, bg=XP_WINDOW_BG)
        body.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        left_outer, left_panel = etched_panel(body, "Master Hardware Devices")
        left_outer.pack(side="left", fill="both", expand=False, padx=(0, 2))
        left_outer.config(width=280)

        tk.Label(left_panel, text="Master Output Volume:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(anchor="w", padx=10, pady=(10, 2))
        self.out_scale = tk.Scale(
            left_panel, from_=0, to=100, orient="horizontal", 
            bg=XP_WINDOW_BG, highlightthickness=0, command=self._set_master_out
        )
        self.out_scale.set(70)
        self.out_scale.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(left_panel, text="Master Input Gain (Mic):", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(anchor="w", padx=10, pady=(10, 2))
        self.in_scale = tk.Scale(
            left_panel, from_=0, to=100, orient="horizontal", 
            bg=XP_WINDOW_BG, highlightthickness=0, command=self._set_master_in
        )
        self.in_scale.set(80)
        self.in_scale.pack(fill="x", padx=10, pady=(0, 10))

        right_outer, right_panel = etched_panel(body, "System Application Volume Mixer")
        right_outer.pack(side="right", fill="both", expand=True, padx=(2, 0))

        canvas = tk.Canvas(right_panel, bg=XP_WINDOW_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        self.mixer_scroll_frame = tk.Frame(canvas, bg=XP_WINDOW_BG)

        self.mixer_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.mixer_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)

        self.refresh_app_mixer()

    def refresh_app_mixer(self):
        for w in self.mixer_scroll_frame.winfo_children():
            w.destroy()

        self.app_controls.clear()
        filter_mode = self.filter_var.get()
        apps = self._get_all_detected_apps(filter_active_only=(filter_mode == "Active Audio Streams Only"))

        if not apps:
            tk.Label(self.mixer_scroll_frame, text="No processes matching criteria found.", font=FONT_UI, bg=XP_WINDOW_BG).pack(padx=10, pady=10)
            return

        for idx, app in enumerate(apps):
            app_name = app["name"]
            
            row = tk.Frame(self.mixer_scroll_frame, bg=XP_WINDOW_BG)
            row.pack(fill="x", padx=5, pady=3, anchor="w")

            lbl = tk.Label(row, text=app_name[:20], font=FONT_UI_BOLD, bg=XP_WINDOW_BG, width=18, anchor="w")
            lbl.pack(side="left", padx=5)

            scale = tk.Scale(
                row, from_=0, to=100, orient="horizontal", 
                bg=XP_WINDOW_BG, highlightthickness=0, length=220,
                command=lambda val, name=app_name: self._set_app_volume(name, val)
            )
            scale.set(app["volume"])
            scale.pack(side="left", padx=5)

            mute_var = tk.BooleanVar(value=app.get("muted", False))
            chk = tk.Checkbutton(
                row, text="Mute", variable=mute_var, bg=XP_WINDOW_BG, font=FONT_UI,
                command=lambda name=app_name, var=mute_var: self._toggle_app_mute(name, var.get())
            )
            chk.pack(side="left", padx=5)

            self.app_controls[app_name] = {"scale": scale, "mute_var": mute_var}

    def _get_all_detected_apps(self, filter_active_only=False):
        """Discovers running software processes and queries Windows Audio Endpoint sessions."""
        discovered_apps = {}

        if PYCAW_AVAILABLE:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    if s.Process and s.Process.name():
                        pname = s.Process.name()
                        vol_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                        discovered_apps[pname] = {
                            "name": pname,
                            "volume": int(vol_ctl.GetMasterVolume() * 100),
                            "muted": bool(vol_ctl.GetMute())
                        }
            except Exception:
                pass

        if not filter_active_only:
            try:
                for proc in psutil.process_iter(['name']):
                    pname = proc.info['name']
                    if pname and pname.endswith('.exe') and pname not in discovered_apps:
                        if pname.lower() not in ["svchost.exe", "conhost.exe", "explorer.exe", "system"]:
                            discovered_apps[pname] = {
                                "name": pname,
                                "volume": 75,
                                "muted": False
                            }
            except Exception:
                pass

        return list(discovered_apps.values())

    def apply_profile(self, profile_name: str):
        if profile_name not in self.profiles:
            return

        prof = self.profiles[profile_name]
        self.active_profile_name = profile_name
        self.profile_var.set(profile_name)

        self.out_scale.set(prof["out_vol"])
        self.in_scale.set(prof["in_vol"])

        for app_exe, vol in prof.get("apps", {}).items():
            self._set_app_volume(app_exe, vol)
            if app_exe in self.app_controls:
                self.app_controls[app_exe]["scale"].set(vol)

        self.profile_status_lbl.config(
            text=f"[Active Profile: {profile_name}]",
            fg=XP_OK_GREEN
        )

    def _on_profile_selected(self, choice):
        self.apply_profile(choice)

    def _start_process_watcher(self):
        def watch_loop():
            while True:
                try:
                    procs = {p.info['name'].lower() for p in psutil.process_iter(['name']) if p.info['name']}
                    for name, data in self.profiles.items():
                        trigger_exe = data.get("trigger_app", "").lower()
                        if trigger_exe != "none" and trigger_exe in procs:
                            if self.active_profile_name != name:
                                self.after(0, lambda n=name: self.apply_profile(n))
                                break
                except Exception:
                    pass
                time.sleep(3)

        threading.Thread(target=watch_loop, daemon=True).start()

    def _set_master_out(self, val):
        pass

    def _set_master_in(self, val):
        pass

    def _set_app_volume(self, app_name: str, value: str):
        if PYCAW_AVAILABLE:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    if s.Process and s.Process.name().lower() == app_name.lower():
                        vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                        vol.SetMasterVolume(float(value) / 100.0, None)
            except Exception:
                pass

    def _toggle_app_mute(self, app_name: str, is_muted: bool):
        if PYCAW_AVAILABLE:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for s in sessions:
                    if s.Process and s.Process.name().lower() == app_name.lower():
                        vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                        vol.SetMute(is_muted, None)
            except Exception:
                pass
