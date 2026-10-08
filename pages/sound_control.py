"""
Backends (chosen automatically):
  * Windows : pycaw + comtypes   (pip install pycaw comtypes)
              per-app volume/mute, device volume/mute/gain.
  * Linux   : PulseAudio / PipeWire through the `pactl` command
              (package: pulseaudio-utils, or pipewire-pulse). No Python deps.
              per-app volume/mute, device volume/mute/gain, default device.
  * macOS   : osascript + system_profiler (built in).
              Device volume / mic gain apply to the DEFAULT device only, and
              per-app volume is NOT possible on macOS without a virtual audio
              driver, so the mixer is shown read-only there.
              Optional: `brew install switchaudio-osx` enables changing the
              default device from this page.

 Limits:
  * Windows cannot change the default device through public APIs, so that
    button is disabled there (use Windows Sound settings).
  * Linux only has per-app entries for apps that currently own an audio
    stream; Windows keeps an entry for every app that has opened audio.
"""

import copy
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import psutil

from theme import (
    XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_UI_BOLD, FONT_MONO,
    XP_OK_GREEN, XP_WARN_ORANGE, XP_ALERT_RED, XP_BLUE_DARK,
    make_titlebar, etched_panel, xp_button,
)

PROFILE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sound_profiles.json")
FILTER_ALL = "All Audio Apps"
FILTER_PLAYING = "Currently Playing Only"


def norm_app(name):
    n = (name or "").strip().lower()
    for suf in (".exe", ".app"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n


class BackendUnavailable(Exception):
    pass


class AudioBackend:
    name = "None"
    per_app = False
    per_app_note = ""
    can_set_default = False

    def thread_init(self):
        pass

    def thread_done(self):
        pass


    def list_apps(self, playing_only=False):
        return []

    def set_app_volume(self, key, pct):
        raise NotImplementedError

    def set_app_mute(self, key, muted):
        raise NotImplementedError

    def list_devices(self, kind):
        return []

    def set_device_volume(self, kind, dev_id, pct):
        raise NotImplementedError

    def set_device_mute(self, kind, dev_id, muted):
        raise NotImplementedError

    def set_default_device(self, kind, dev_id):
        raise NotImplementedError


class UnavailableBackend(AudioBackend):
    def __init__(self, reason):
        self.name = "Unavailable"
        self.reason = reason


class WindowsBackend(AudioBackend):
    name = "Windows (Core Audio / pycaw)"
    per_app = True
    can_set_default = False

    def __init__(self):
        try:
            import comtypes
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IMMDeviceEnumerator
            try:
                from pycaw.constants import CLSID_MMDeviceEnumerator
            except ImportError:
                from pycaw.pycaw import CLSID_MMDeviceEnumerator
        except ImportError as exc:
            raise BackendUnavailable(f"Missing package ({exc}). Run: pip install pycaw comtypes")
        self.comtypes = comtypes
        self.cast, self.POINTER, self.CLSCTX_ALL = cast, POINTER, CLSCTX_ALL
        self.AudioUtilities = AudioUtilities
        self.IAudioEndpointVolume = IAudioEndpointVolume
        self.IMMDeviceEnumerator = IMMDeviceEnumerator
        self.CLSID = CLSID_MMDeviceEnumerator

    def thread_init(self):
        self.comtypes.CoInitialize()

    def thread_done(self):
        try:
            self.comtypes.CoUninitialize()
        except Exception:
            pass

    def _sessions(self):
        out = []
        for s in self.AudioUtilities.GetAllSessions():
            try:
                if s.Process and s.Process.name():
                    out.append((s.Process.name(), s))
            except Exception:
                continue
        return out

    def list_apps(self, playing_only=False):
        apps = {}
        for pname, s in self._sessions():
            playing = getattr(s, "State", 0) == 1
            if pname in apps:
                apps[pname]["playing"] = apps[pname]["playing"] or playing
                continue
            try:
                vc = s.SimpleAudioVolume
                apps[pname] = {"key": pname, "name": pname,
                               "volume": int(round(vc.GetMasterVolume() * 100)),
                               "muted": bool(vc.GetMute()), "playing": playing}
            except Exception:
                continue
        res = list(apps.values())
        if playing_only:
            res = [a for a in res if a["playing"]]
        return res

    def set_app_volume(self, key, pct):
        for pname, s in self._sessions():
            if norm_app(pname) == norm_app(key):
                s.SimpleAudioVolume.SetMasterVolume(max(0, min(100, pct)) / 100.0, None)

    def set_app_mute(self, key, muted):
        for pname, s in self._sessions():
            if norm_app(pname) == norm_app(key):
                s.SimpleAudioVolume.SetMute(1 if muted else 0, None)

    def _enum(self):
        return self.comtypes.CoCreateInstance(
            self.CLSID, self.IMMDeviceEnumerator, self.comtypes.CLSCTX_INPROC_SERVER)

    def _endpoint(self, dev):
        iface = dev.Activate(self.IAudioEndpointVolume._iid_, self.CLSCTX_ALL, None)
        return self.cast(iface, self.POINTER(self.IAudioEndpointVolume))

    def list_devices(self, kind):
        flow = 0 if kind == "output" else 1
        enum = self._enum()
        names = {}
        try:
            for d in self.AudioUtilities.GetAllDevices():
                names[d.id] = d.FriendlyName
        except Exception:
            pass
        try:
            default_id = enum.GetDefaultAudioEndpoint(flow, 0).GetId()
        except Exception:
            default_id = None
        coll = enum.EnumAudioEndpoints(flow, 1)  
        out = []
        for i in range(coll.GetCount()):
            dev = coll.Item(i)
            did = dev.GetId()
            vol, muted, ok = None, False, False
            try:
                ep = self._endpoint(dev)
                vol = int(round(ep.GetMasterVolumeLevelScalar() * 100))
                muted = bool(ep.GetMute())
                ok = True
            except Exception:
                pass
            out.append({"id": did, "name": names.get(did, did), "volume": vol, "muted": muted,
                        "is_default": did == default_id, "can_set_volume": ok, "can_mute": ok})
        return out

    def _device(self, dev_id):
        return self._endpoint(self._enum().GetDevice(dev_id))

    def set_device_volume(self, kind, dev_id, pct):
        self._device(dev_id).SetMasterVolumeLevelScalar(max(0, min(100, pct)) / 100.0, None)

    def set_device_mute(self, kind, dev_id, muted):
        self._device(dev_id).SetMute(1 if muted else 0, None)


class LinuxBackend(AudioBackend):
    name = "Linux (PulseAudio / PipeWire via pactl)"
    per_app = True
    can_set_default = True

    def __init__(self):
        if not shutil.which("pactl"):
            raise BackendUnavailable("'pactl' not found. Install pulseaudio-utils (or pipewire-pulse).")
        self._env = dict(os.environ, LC_ALL="C")

    def _run(self, *args):
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5, env=self._env)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "pactl failed")
        return r.stdout

    def _json(self, *args):
        return json.loads(self._run("--format=json", *args))

    @staticmethod
    def _pct(vol):
        vals = [c.get("value", 0) for c in (vol or {}).values()]
        return int(round(sum(vals) / len(vals) / 65536 * 100)) if vals else None

    def _inputs(self):
        res = []
        for d in self._json("list", "sink-inputs"):
            p = d.get("properties", {})
            name = p.get("application.name") or p.get("application.process.binary") or p.get("media.name")
            if not name or p.get("application.id") == "org.PulseAudio.pavucontrol":
                continue
            res.append({"index": d["index"], "name": name,
                        "binary": p.get("application.process.binary", ""),
                        "volume": self._pct(d.get("volume")), "muted": bool(d.get("mute")),
                        "playing": not d.get("corked", False)})
        return res

    def list_apps(self, playing_only=False):
        apps = {}
        for i in self._inputs():
            a = apps.setdefault(i["name"], {"key": i["name"], "name": i["name"], "volume": i["volume"],
                                            "muted": i["muted"], "playing": False})
            a["playing"] = a["playing"] or i["playing"]
        res = list(apps.values())
        return [a for a in res if a["playing"]] if playing_only else res

    def _matching(self, key):
        k = norm_app(key)
        return [i for i in self._inputs() if norm_app(i["name"]) == k or norm_app(i["binary"]) == k]

    def set_app_volume(self, key, pct):
        for i in self._matching(key):
            self._run("set-sink-input-volume", str(i["index"]), f"{max(0, min(100, pct))}%")

    def set_app_mute(self, key, muted):
        for i in self._matching(key):
            self._run("set-sink-input-mute", str(i["index"]), "1" if muted else "0")

    def list_devices(self, kind):
        what = "sinks" if kind == "output" else "sources"
        default = self._run("get-default-sink" if kind == "output" else "get-default-source").strip()
        out = []
        for d in self._json("list", what):
            if kind == "input" and (d.get("monitor_of_sink") or d["name"].endswith(".monitor")):
                continue
            out.append({"id": d["name"], "name": d.get("description") or d["name"],
                        "volume": self._pct(d.get("volume")), "muted": bool(d.get("mute")),
                        "is_default": d["name"] == default, "can_set_volume": True, "can_mute": True})
        return out

    def set_device_volume(self, kind, dev_id, pct):
        cmd = "set-sink-volume" if kind == "output" else "set-source-volume"
        self._run(cmd, dev_id, f"{max(0, min(100, pct))}%")

    def set_device_mute(self, kind, dev_id, muted):
        cmd = "set-sink-mute" if kind == "output" else "set-source-mute"
        self._run(cmd, dev_id, "1" if muted else "0")

    def set_default_device(self, kind, dev_id):
        self._run("set-default-sink" if kind == "output" else "set-default-source", dev_id)


class MacBackend(AudioBackend):
    name = "macOS (osascript / system_profiler)"
    per_app = False
    per_app_note = ("macOS has no built-in per-app volume control. Apps are listed for reference only; "
                    "use a virtual driver (e.g. Background Music) if you need this.")

    def __init__(self):
        if not shutil.which("osascript"):
            raise BackendUnavailable("'osascript' not found.")
        self._switch = shutil.which("SwitchAudioSource")
        self.can_set_default = bool(self._switch)

    @staticmethod
    def _run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or "command failed")
        return r.stdout

    def _settings(self):
        txt = self._run(["osascript", "-e", "get volume settings"])

        def grab(key):
            m = re.search(key + r":(\w+)", txt)
            return int(m.group(1)) if m and m.group(1).isdigit() else None
        return {"out": grab("output volume"), "in": grab("input volume"),
                "muted": "output muted:true" in txt}

    def list_apps(self, playing_only=False):
        if playing_only:
            return []  
        names = set()
        roots = ("/Applications/", os.path.expanduser("~/Applications/"), "/System/Applications/")
        for p in psutil.process_iter(["exe"]):
            exe = p.info.get("exe") or ""
            if exe.startswith(roots):
                m = re.search(r"/([^/]+)\.app/Contents/MacOS/", exe)
                if m and "helper" not in m.group(1).lower():
                    names.add(m.group(1))
        return [{"key": n, "name": n, "volume": None, "muted": False, "playing": False}
                for n in sorted(names, key=str.lower)]

    def list_devices(self, kind):
        data = json.loads(self._run(["system_profiler", "SPAudioDataType", "-json"]))
        items = []
        for group in data.get("SPAudioDataType", []):
            items.extend(group.get("_items", []))
        s = self._settings()
        res = []
        for it in items:
            if kind == "output" and "coreaudio_device_output" not in it:
                continue
            if kind == "input" and "coreaudio_device_input" not in it:
                continue
            flag = "coreaudio_default_audio_output_device" if kind == "output" \
                else "coreaudio_default_audio_input_device"
            is_def = it.get(flag) == "spaudio_yes"
            vol = (s["out"] if kind == "output" else s["in"]) if is_def else None
            res.append({"id": it["_name"], "name": it["_name"], "volume": vol,
                        "muted": s["muted"] if (is_def and kind == "output") else False,
                        "is_default": is_def, "can_set_volume": is_def and vol is not None,
                        "can_mute": is_def and kind == "output"})
        return res

    def set_device_volume(self, kind, dev_id, pct):
        pct = max(0, min(100, pct))
        what = "output" if kind == "output" else "input"
        self._run(["osascript", "-e", f"set volume {what} volume {pct}"])

    def set_device_mute(self, kind, dev_id, muted):
        if kind != "output":
            raise RuntimeError("macOS cannot mute inputs; set the gain to 0 instead.")
        self._run(["osascript", "-e", f"set volume output muted {'true' if muted else 'false'}"])

    def set_default_device(self, kind, dev_id):
        if not self._switch:
            raise RuntimeError("Install SwitchAudioSource (brew install switchaudio-osx) to change defaults.")
        self._run([self._switch, "-t", "output" if kind == "output" else "input", "-s", dev_id])


def create_backend():
    try:
        system = platform.system()
        if system == "Windows":
            return WindowsBackend()
        if system == "Linux":
            return LinuxBackend()
        if system == "Darwin":
            return MacBackend()
        return UnavailableBackend(f"Unsupported OS: {system}")
    except BackendUnavailable as exc:
        return UnavailableBackend(str(exc))
    except Exception as exc:
        return UnavailableBackend(f"Audio backend failed to start: {exc}")


DEFAULT_PROFILES = {
    "Default": {"out_vol": 70, "in_vol": 80, "trigger_app": "",
                "apps": {"chrome.exe": {"volume": 80, "muted": False},
                         "spotify.exe": {"volume": 60, "muted": False},
                         "discord.exe": {"volume": 80, "muted": False}}},
    "Focus Mode": {"out_vol": 30, "in_vol": 0, "trigger_app": "code.exe",
                   "apps": {"spotify.exe": {"volume": 20, "muted": False},
                            "discord.exe": {"volume": 0, "muted": True},
                            "chrome.exe": {"volume": 0, "muted": True}}},
    "Gaming / Stream": {"out_vol": 100, "in_vol": 90, "trigger_app": "obs64.exe",
                        "apps": {"discord.exe": {"volume": 100, "muted": False},
                                 "chrome.exe": {"volume": 10, "muted": False}}},
}


def _clean_profile(p):
    apps = {}
    for k, v in (p.get("apps") or {}).items():
        if isinstance(v, dict):
            apps[k] = {"volume": int(v.get("volume", 50)), "muted": bool(v.get("muted", False))}
        else:
            apps[k] = {"volume": int(v), "muted": False}
    trig = p.get("trigger_app") or ""
    return {"out_vol": p.get("out_vol"), "in_vol": p.get("in_vol"),
            "trigger_app": "" if trig.lower() == "none" else trig, "apps": apps}


def load_profiles():
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        profs = {n: _clean_profile(p) for n, p in data.items() if isinstance(p, dict)}
        if profs:
            return profs
    except (OSError, ValueError):
        pass
    return copy.deepcopy(DEFAULT_PROFILES)


def make_scrollable(parent):
    canvas = tk.Canvas(parent, bg=XP_WINDOW_BG, highlightthickness=0)
    sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=XP_WINDOW_BG)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
    canvas.configure(yscrollcommand=sb.set)

    def wheel(e):
        if e.num == 4:
            d = -1
        elif e.num == 5:
            d = 1
        else:
            d = -1 if e.delta > 0 else 1
        canvas.yview_scroll(d, "units")

    def enter(_e):
        canvas.bind_all("<MouseWheel>", wheel)
        canvas.bind_all("<Button-4>", wheel)
        canvas.bind_all("<Button-5>", wheel)

    def leave(_e):
        x, y = canvas.winfo_pointerxy()
        w = canvas.winfo_containing(x, y)
        while w is not None:
            if w is canvas:
                return
            w = w.master
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.unbind_all(seq)

    canvas.bind("<Enter>", enter)
    canvas.bind("<Leave>", leave)
    canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
    sb.pack(side="right", fill="y", pady=5)
    return inner


class ProfileEditor(tk.Toplevel):
    def __init__(self, page, profile_name, running_apps):
        super().__init__(page)
        self.page = page
        self.original_name = profile_name
        data = copy.deepcopy(page.profiles[profile_name]) if profile_name else \
            {"out_vol": None, "in_vol": None, "trigger_app": "", "apps": {}}

        self.title("Edit Audio Profile" if profile_name else "New Audio Profile")
        self.configure(bg=XP_WINDOW_BG)
        self.geometry("580x640")
        self.minsize(520, 520)
        self.transient(page.winfo_toplevel())

        top = tk.Frame(self, bg=XP_WINDOW_BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Profile name:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(side="left")
        self.name_var = tk.StringVar(value=profile_name or "")
        tk.Entry(top, textvariable=self.name_var, font=FONT_UI, width=32).pack(side="left", padx=8)

        outer, panel = etched_panel(self, "Device levels (applied to the default devices)")
        outer.pack(fill="x", padx=10, pady=4)
        self.out_on = tk.BooleanVar(value=data["out_vol"] is not None)
        self.out_v = tk.IntVar(value=data["out_vol"] if data["out_vol"] is not None else 70)
        self.in_on = tk.BooleanVar(value=data["in_vol"] is not None)
        self.in_v = tk.IntVar(value=data["in_vol"] if data["in_vol"] is not None else 80)
        for text, on, var in (("Set output volume", self.out_on, self.out_v),
                              ("Set microphone level", self.in_on, self.in_v)):
            row = tk.Frame(panel, bg=XP_WINDOW_BG)
            row.pack(fill="x", padx=6, pady=2)
            tk.Checkbutton(row, text=text, variable=on, bg=XP_WINDOW_BG, font=FONT_UI,
                           width=20, anchor="w").pack(side="left")
            tk.Scale(row, from_=0, to=100, orient="horizontal", variable=var, bg=XP_WINDOW_BG,
                     highlightthickness=0, length=260).pack(side="left", padx=6)

        outer, panel = etched_panel(self, "Auto-switch trigger (optional)")
        outer.pack(fill="x", padx=10, pady=4)
        row = tk.Frame(panel, bg=XP_WINDOW_BG)
        row.pack(fill="x", padx=6, pady=6)
        tk.Label(row, text="Activate when this app runs:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left")
        self.trigger_var = tk.StringVar(value=data["trigger_app"])
        names = sorted({a["key"] for a in running_apps} | set(data["apps"].keys()), key=str.lower)
        ttk.Combobox(row, textvariable=self.trigger_var, values=[""] + names,
                     width=26, font=FONT_UI).pack(side="left", padx=8)

        outer, panel = etched_panel(self, "Applications - tick to include, then set the volume")
        outer.pack(fill="both", expand=True, padx=10, pady=4)
        self.list_frame = make_scrollable(panel)
        self.rows = {}

        for key, cfg in data["apps"].items():
            self._add_row(key, True, cfg["volume"], cfg["muted"])
        for a in running_apps:
            if norm_app(a["key"]) not in {norm_app(k) for k in self.rows}:
                self._add_row(a["key"], False, a["volume"] if a["volume"] is not None else 50, False)
        if not self.rows:
            tk.Label(self.list_frame, text="No audio apps detected - add one by name below.",
                     font=FONT_UI, bg=XP_WINDOW_BG).pack(padx=8, pady=8)

        add = tk.Frame(self, bg=XP_WINDOW_BG)
        add.pack(fill="x", padx=10, pady=2)
        tk.Label(add, text="Add app by name:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left")
        self.add_var = tk.StringVar()
        e = tk.Entry(add, textvariable=self.add_var, font=FONT_UI, width=26)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _e: self._add_by_name())
        xp_button(add, "Add", command=self._add_by_name).pack(side="left")

        btns = tk.Frame(self, bg=XP_WINDOW_BG)
        btns.pack(fill="x", padx=10, pady=10)
        xp_button(btns, "Cancel", command=self.destroy).pack(side="right", padx=3)
        xp_button(btns, "Save && Apply", command=lambda: self._save(apply=True)).pack(side="right", padx=3)
        xp_button(btns, "Save", command=lambda: self._save(apply=False)).pack(side="right", padx=3)

        self.grab_set()
        self.focus_set()

    def _add_row(self, key, include, volume, muted):
        row = tk.Frame(self.list_frame, bg=XP_WINDOW_BG)
        row.pack(fill="x", padx=4, pady=2)
        inc, vol, mut = tk.BooleanVar(value=include), tk.IntVar(value=int(volume)), tk.BooleanVar(value=muted)
        tk.Checkbutton(row, text=key[:24], variable=inc, bg=XP_WINDOW_BG, font=FONT_UI_BOLD,
                       width=22, anchor="w").pack(side="left")
        tk.Scale(row, from_=0, to=100, orient="horizontal", variable=vol, bg=XP_WINDOW_BG,
                 highlightthickness=0, length=170).pack(side="left", padx=4)
        tk.Checkbutton(row, text="Mute", variable=mut, bg=XP_WINDOW_BG, font=FONT_UI).pack(side="left")
        self.rows[key] = {"include": inc, "vol": vol, "mute": mut}

    def _add_by_name(self):
        name = self.add_var.get().strip()
        if not name:
            return
        if norm_app(name) in {norm_app(k) for k in self.rows}:
            messagebox.showinfo("Already listed", f"'{name}' is already in the list.", parent=self)
            return
        self._add_row(name, True, 50, False)
        self.add_var.set("")

    def _save(self, apply):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name required", "Give the profile a name.", parent=self)
            return
        if name != self.original_name and name in self.page.profiles:
            messagebox.showwarning("Name in use", f"A profile called '{name}' already exists.", parent=self)
            return
        apps = {k: {"volume": r["vol"].get(), "muted": r["mute"].get()}
                for k, r in self.rows.items() if r["include"].get()}
        prof = {"out_vol": self.out_v.get() if self.out_on.get() else None,
                "in_vol": self.in_v.get() if self.in_on.get() else None,
                "trigger_app": self.trigger_var.get().strip(), "apps": apps}
        self.page.store_profile(self.original_name, name, prof)
        self.destroy()
        if apply:
            self.page.apply_profile(name)


class SoundControlPage(tk.Frame):

    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller
        self.backend = create_backend()

        self.profiles = load_profiles()
        self.active_profile_name = next(iter(self.profiles))
        self._pre_auto_profile = None
        self._last_match = None

        self.devices = {"output": [], "input": []}
        self.dev_widgets = {}
        self._loading = False
        self._deb = {}
        self._results = queue.Queue()
        self._cycle_busy = False
        self._mixer_sig = None

        make_titlebar(self, "Sound & Audio Profile Manager", "\U0001F50A")
        self._build_toolbar()
        self._build_profile_panel()

        self.msg_lbl = tk.Label(self, text="", font=FONT_UI, bg=XP_WINDOW_BG, anchor="w")
        self.msg_lbl.pack(fill="x", side="bottom", padx=8, pady=2)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)
        self.tab_mixer = tk.Frame(nb, bg=XP_WINDOW_BG)
        self.tab_devices = tk.Frame(nb, bg=XP_WINDOW_BG)
        nb.add(self.tab_mixer, text="App Volume Mixer")
        nb.add(self.tab_devices, text="Input / Output Devices")
        self._build_mixer_tab()
        self._build_devices_tab(self.tab_devices)

        if isinstance(self.backend, UnavailableBackend):
            self._set_msg(f"Audio control unavailable: {self.backend.reason}", "alert")
            return

        self._pump()
        self.refresh_all()
        self.after(3000, self._cycle)

    def _set_msg(self, text, level="ok"):
        color = {"ok": XP_OK_GREEN, "warn": XP_WARN_ORANGE, "alert": XP_ALERT_RED}[level]
        self.msg_lbl.config(text=text, fg=color)

    def _run_async(self, work, done=None):
        def runner():
            self.backend.thread_init()
            try:
                result, err = work(), None
            except Exception as exc:
                result, err = None, exc
            finally:
                self.backend.thread_done()
            self._results.put((done, result, err))
        threading.Thread(target=runner, daemon=True).start()

    def _pump(self):
        try:
            while True:
                done, result, err = self._results.get_nowait()
                if done:
                    done(result, err)
                elif err:
                    self._set_msg(str(err), "alert")
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _debounce(self, key, fn, delay=150):
        if key in self._deb:
            self.after_cancel(self._deb[key])
        self._deb[key] = self.after(delay, fn)

    def _report(self, _result, err):
        if err:
            self._set_msg(str(err), "alert")

    def on_show(self):
        if not isinstance(self.backend, UnavailableBackend):
            self.refresh_all()

    def refresh_all(self):
        self.refresh_app_mixer()
        self.refresh_devices()

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        bar.pack(fill="x", padx=4, pady=(4, 0))
        xp_button(bar, "\u2190 Home", command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)
        xp_button(bar, "\U0001F504 Refresh", command=self.refresh_all).pack(side="left", padx=3, pady=3)
        tk.Label(bar, text=f"Backend: {self.backend.name}", font=FONT_UI, bg=XP_WINDOW_BG,
                 fg=XP_BLUE_DARK).pack(side="right", padx=8)

    def _build_profile_panel(self):
        outer, panel = etched_panel(self, "Audio Profiles")
        outer.pack(fill="x", padx=4, pady=4)
        row = tk.Frame(panel, bg=XP_WINDOW_BG)
        row.pack(fill="x", padx=6, pady=6)

        tk.Label(row, text="Profile:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(side="left", padx=(4, 4))
        self.profile_var = tk.StringVar(value=self.active_profile_name)
        self.profile_combo = ttk.Combobox(row, textvariable=self.profile_var, state="readonly",
                                          values=list(self.profiles), width=22, font=FONT_UI)
        self.profile_combo.pack(side="left", padx=4)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_profile(self.profile_var.get()))

        xp_button(row, "New...", command=lambda: self._open_editor(None)).pack(side="left", padx=2)
        xp_button(row, "Edit...", command=lambda: self._open_editor(self.profile_var.get())).pack(side="left", padx=2)
        xp_button(row, "Delete", command=self.delete_profile).pack(side="left", padx=2)

        self.auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(row, text="Auto-switch by trigger app", variable=self.auto_var, bg=XP_WINDOW_BG,
                       font=FONT_UI, command=self._toggle_auto).pack(side="left", padx=12)

        self.profile_status_lbl = tk.Label(row, text="[Mode: Manual]", font=FONT_UI,
                                           fg=XP_OK_GREEN, bg=XP_WINDOW_BG)
        self.profile_status_lbl.pack(side="right", padx=8)

    def save_profiles(self):
        try:
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2)
        except OSError as exc:
            self._set_msg(f"Could not save profiles: {exc}", "alert")

    def store_profile(self, old_name, new_name, prof):
        if old_name and old_name != new_name:
            self.profiles.pop(old_name, None)
            if self.active_profile_name == old_name:
                self.active_profile_name = new_name
        self.profiles[new_name] = prof
        self.save_profiles()
        self.profile_combo.config(values=list(self.profiles))
        self.profile_var.set(self.active_profile_name if self.active_profile_name in self.profiles else new_name)
        self._set_msg(f"Profile '{new_name}' saved.")

    def delete_profile(self):
        name = self.profile_var.get()
        if len(self.profiles) <= 1:
            messagebox.showinfo("Cannot delete", "At least one profile must remain.", parent=self)
            return
        if not messagebox.askyesno("Delete profile", f"Delete profile '{name}'?", parent=self):
            return
        self.profiles.pop(name, None)
        self.save_profiles()
        self.active_profile_name = next(iter(self.profiles))
        self.profile_combo.config(values=list(self.profiles))
        self.profile_var.set(self.active_profile_name)
        self.profile_status_lbl.config(text="[Mode: Manual]", fg=XP_OK_GREEN)

    def _open_editor(self, name):
        if name is not None and name not in self.profiles:
            return
        self._set_msg("Detecting audio apps...")
        self._run_async(lambda: self.backend.list_apps(False),
                        lambda apps, err: (self._set_msg(""), ProfileEditor(self, name, apps or [])))

    def _set_default_device_level(self, kind, pct):
        for d in self.backend.list_devices(kind):
            if d["is_default"] and d["can_set_volume"]:
                self.backend.set_device_volume(kind, d["id"], pct)
                return

    def apply_profile(self, name, auto=False):
        if name not in self.profiles:
            return
        prof = self.profiles[name]
        self.active_profile_name = name
        self.profile_var.set(name)
        self.profile_status_lbl.config(
            text=f"[Active: {name}{' - auto' if auto else ''}]", fg=XP_OK_GREEN)

        def work():
            if prof.get("out_vol") is not None:
                self._set_default_device_level("output", prof["out_vol"])
            if prof.get("in_vol") is not None:
                self._set_default_device_level("input", prof["in_vol"])
            if self.backend.per_app:
                for key, cfg in prof["apps"].items():
                    self.backend.set_app_volume(key, cfg["volume"])
                    self.backend.set_app_mute(key, cfg["muted"])

        def done(_r, err):
            if err:
                self._set_msg(f"Profile applied with errors: {err}", "warn")
            elif prof["apps"] and not self.backend.per_app:
                self._set_msg("Device levels applied. Per-app volume is not supported on this OS.", "warn")
            else:
                self._set_msg(f"Profile '{name}' applied (apps that aren't running are skipped).")
            self.refresh_all()

        self._run_async(work, done)

    def _toggle_auto(self):
        self._last_match = None
        if self.auto_var.get():
            self.profile_status_lbl.config(text=f"[Active: {self.active_profile_name} - auto-watch on]")
        else:
            self.profile_status_lbl.config(text=f"[Active: {self.active_profile_name}]")

    @staticmethod
    def _scan_procs():
        names = set()
        for p in psutil.process_iter(["name"]):
            if p.info.get("name"):
                names.add(norm_app(p.info["name"]))
        return names

    def _trigger_running(self, trigger, procs):
        t = norm_app(trigger)
        if not t:
            return False
        return any(p == t or (len(p) >= 15 and t.startswith(p)) for p in procs)

    def _handle_triggers(self, procs):
        match = None
        for name, prof in self.profiles.items():
            if self._trigger_running(prof.get("trigger_app", ""), procs):
                match = name
                break
        if match == self._last_match:
            return
        self._last_match = match
        if match:
            if self._pre_auto_profile is None:
                self._pre_auto_profile = self.active_profile_name
            if match != self.active_profile_name:
                self.apply_profile(match, auto=True)
        elif self._pre_auto_profile is not None:
            prev, self._pre_auto_profile = self._pre_auto_profile, None
            if prev in self.profiles:
                self.apply_profile(prev, auto=True)

    def _cycle(self):
        if not self._cycle_busy:
            self._cycle_busy = True
            want_procs = self.auto_var.get()
            playing_only = self.filter_var.get() == FILTER_PLAYING

            def work():
                procs = self._scan_procs() if want_procs else None
                return procs, self.backend.list_apps(playing_only)

            self._run_async(work, self._on_cycle)
        self.after(3000, self._cycle)

    def _on_cycle(self, result, err):
        self._cycle_busy = False
        if err or not result:
            return
        procs, apps = result
        self._on_apps(apps, None, force=False)
        if procs is not None:
            self._handle_triggers(procs)

    def _build_mixer_tab(self):
        top = tk.Frame(self.tab_mixer, bg=XP_WINDOW_BG)
        top.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(top, text="Show:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left")
        self.filter_var = tk.StringVar(value=FILTER_ALL)
        combo = ttk.Combobox(top, textvariable=self.filter_var, values=[FILTER_ALL, FILTER_PLAYING],
                             state="readonly", width=24, font=FONT_UI)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_app_mixer())
        if self.backend.per_app_note:
            tk.Label(top, text=self.backend.per_app_note, font=FONT_UI, fg=XP_WARN_ORANGE,
                     bg=XP_WINDOW_BG, wraplength=700, justify="left").pack(side="left", padx=10)

        outer, panel = etched_panel(self.tab_mixer, "Application Volume Mixer")
        outer.pack(fill="both", expand=True, padx=4, pady=4)
        self.mixer_frame = make_scrollable(panel)
        self.app_controls = {}

    def refresh_app_mixer(self):
        if isinstance(self.backend, UnavailableBackend):
            return
        playing_only = self.filter_var.get() == FILTER_PLAYING
        self._run_async(lambda: self.backend.list_apps(playing_only),
                        lambda apps, err: self._on_apps(apps, err, force=True))

    def _on_apps(self, apps, err, force=True):
        if err:
            self._set_msg(f"Could not list audio apps: {err}", "alert")
            return
        apps = sorted(apps, key=lambda a: (not a["playing"], a["name"].lower()))
        sig = tuple((a["key"], a["playing"]) for a in apps)
        if not force and sig == self._mixer_sig:
            return
        self._mixer_sig = sig
        self._render_mixer(apps)

    def _render_mixer(self, apps):
        for w in self.mixer_frame.winfo_children():
            w.destroy()
        self.app_controls.clear()

        if not apps:
            msg = "No audio applications found."
            if platform.system() == "Linux":
                msg += " (Linux lists apps that currently have an audio stream open.)"
            tk.Label(self.mixer_frame, text=msg, font=FONT_UI, bg=XP_WINDOW_BG).pack(padx=10, pady=10)
            return

        for app in apps:
            key = app["key"]
            row = tk.Frame(self.mixer_frame, bg=XP_WINDOW_BG)
            row.pack(fill="x", padx=5, pady=3)
            tk.Label(row, text="\u266A" if app["playing"] else " ", font=FONT_UI_BOLD, fg=XP_OK_GREEN,
                     bg=XP_WINDOW_BG, width=2).pack(side="left")
            tk.Label(row, text=app["name"][:24], font=FONT_UI_BOLD, bg=XP_WINDOW_BG,
                     width=22, anchor="w").pack(side="left", padx=4)

            scale = tk.Scale(row, from_=0, to=100, orient="horizontal", bg=XP_WINDOW_BG,
                             highlightthickness=0, length=260)
            scale.set(app["volume"] if app["volume"] is not None else 0)
            mute_var = tk.BooleanVar(value=app["muted"])
            if self.backend.per_app:
                scale.config(command=lambda v, k=key: self._on_app_scale(k, v))
            else:
                scale.config(state="disabled")
            scale.pack(side="left", padx=6)

            chk = tk.Checkbutton(row, text="Mute", variable=mute_var, bg=XP_WINDOW_BG, font=FONT_UI,
                                 command=lambda k=key, v=mute_var: self._on_app_mute(k, v.get()))
            if not self.backend.per_app:
                chk.config(state="disabled")
            chk.pack(side="left", padx=6)
            self.app_controls[key] = {"scale": scale, "mute_var": mute_var}

    def _on_app_scale(self, key, val):
        pct = int(float(val))
        self._debounce(f"app-{key}", lambda: self._run_async(
            lambda: self.backend.set_app_volume(key, pct), self._report))

    def _on_app_mute(self, key, muted):
        self._run_async(lambda: self.backend.set_app_mute(key, muted), self._report)

    def _build_devices_tab(self, tab):
        for kind, title, lvl in (("output", "Output Devices (speakers / headphones)", "Volume"),
                                 ("input", "Input Devices (microphones)", "Input level / gain")):
            outer, panel = etched_panel(tab, title)
            outer.pack(side="left", fill="both", expand=True, padx=3, pady=3)

            tree = ttk.Treeview(panel, columns=("name", "vol", "state"), show="headings",
                                height=8, selectmode="browse")
            tree.heading("name", text="Device")
            tree.heading("vol", text="Level")
            tree.heading("state", text="Status")
            tree.column("name", width=230)
            tree.column("vol", width=55, anchor="center")
            tree.column("state", width=90, anchor="center")
            tree.pack(fill="both", expand=True, padx=6, pady=(6, 4))
            tree.bind("<<TreeviewSelect>>", lambda e, k=kind: self._load_device_controls(k))

            ctl = tk.Frame(panel, bg=XP_WINDOW_BG)
            ctl.pack(fill="x", padx=6, pady=(0, 8))
            tk.Label(ctl, text=lvl + ":", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(anchor="w")
            scale = tk.Scale(ctl, from_=0, to=100, orient="horizontal", bg=XP_WINDOW_BG,
                             highlightthickness=0, command=lambda v, k=kind: self._on_device_scale(k, v))
            scale.pack(fill="x")
            btn_row = tk.Frame(ctl, bg=XP_WINDOW_BG)
            btn_row.pack(fill="x", pady=(4, 0))
            mute_var = tk.BooleanVar(value=False)
            mute_chk = tk.Checkbutton(btn_row, text="Mute", variable=mute_var, bg=XP_WINDOW_BG,
                                      font=FONT_UI, command=lambda k=kind: self._on_device_mute(k))
            mute_chk.pack(side="left")
            default_btn = xp_button(btn_row, "Set as Default", command=lambda k=kind: self._set_default(k))
            default_btn.pack(side="right")

            self.dev_widgets[kind] = {"tree": tree, "scale": scale, "mute_var": mute_var,
                                      "mute_chk": mute_chk, "default_btn": default_btn}

    def refresh_devices(self):
        if isinstance(self.backend, UnavailableBackend):
            return
        for kind in ("output", "input"):
            self._run_async(lambda k=kind: self.backend.list_devices(k),
                            lambda devs, err, k=kind: self._on_devices(k, devs, err))

    def _selected_device(self, kind):
        tree = self.dev_widgets[kind]["tree"]
        sel = tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        return self.devices[kind][idx] if idx < len(self.devices[kind]) else None

    def _on_devices(self, kind, devs, err):
        if err:
            self._set_msg(f"Could not list {kind} devices: {err}", "alert")
            return
        tree = self.dev_widgets[kind]["tree"]
        prev = self._selected_device(kind)
        prev_id = prev["id"] if prev else None
        self.devices[kind] = devs
        tree.delete(*tree.get_children())
        pick = None
        for i, d in enumerate(devs):
            state = ("Default" if d["is_default"] else "") + (" / Muted" if d["muted"] else "")
            tree.insert("", "end", iid=str(i), values=(
                d["name"], f"{d['volume']}%" if d["volume"] is not None else "-", state.strip(" /")))
            if d["id"] == prev_id:
                pick = str(i)
            elif pick is None and prev_id is None and d["is_default"]:
                pick = str(i)
        if pick is None and devs:
            pick = "0"
        if pick is not None:
            tree.selection_set(pick)
        self._load_device_controls(kind)

    def _load_device_controls(self, kind):
        w = self.dev_widgets[kind]
        d = self._selected_device(kind)
        self._loading = True
        try:
            if not d:
                w["scale"].set(0)
                w["scale"].config(state="disabled")
                w["mute_chk"].config(state="disabled")
                w["default_btn"].config(state="disabled")
                return
            w["scale"].config(state="normal" if d["can_set_volume"] else "disabled")
            w["scale"].set(d["volume"] or 0)
            w["mute_var"].set(d["muted"])
            w["mute_chk"].config(state="normal" if d["can_mute"] else "disabled")
            can_default = self.backend.can_set_default and not d["is_default"]
            w["default_btn"].config(state="normal" if can_default else "disabled")
        finally:
            self._loading = False

    def _on_device_scale(self, kind, val):
        if self._loading:
            return
        d = self._selected_device(kind)
        if not d or not d["can_set_volume"]:
            return
        pct = int(float(val))
        d["volume"] = pct
        tree = self.dev_widgets[kind]["tree"]
        sel = tree.selection()
        if sel:
            tree.set(sel[0], "vol", f"{pct}%")
        self._debounce(f"dev-{kind}-{d['id']}", lambda: self._run_async(
            lambda: self.backend.set_device_volume(kind, d["id"], pct), self._report))

    def _on_device_mute(self, kind):
        d = self._selected_device(kind)
        if not d:
            return
        muted = self.dev_widgets[kind]["mute_var"].get()
        self._run_async(lambda: self.backend.set_device_mute(kind, d["id"], muted),
                        lambda r, e: (self._report(r, e), self.refresh_devices()))

    def _set_default(self, kind):
        d = self._selected_device(kind)
        if not d:
            return
        self._run_async(lambda: self.backend.set_default_device(kind, d["id"]),
                        lambda r, e: (self._report(r, e), self.refresh_devices()))
