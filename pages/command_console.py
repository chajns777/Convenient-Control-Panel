import os
import platform
import queue
import re
import signal
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from theme import (XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_UI_BOLD, FONT_MONO,
                    XP_OK_GREEN, XP_WARN_ORANGE, XP_ALERT_RED,
                    make_titlebar, etched_panel, xp_button)
                    
windows_user = os.getlogin()

COMMAND_LIBRARY = [
    # --- System Info ---
    {"name": "systeminfo", "command": "systeminfo", "category": "System Info", "os": "windows",
     "description": "Full OS, hardware and hotfix summary for the machine."},
    {"name": "ver", "command": "ver", "category": "System Info", "os": "windows",
     "description": "Prints the exact Windows version string."},
    {"name": "hostname", "command": "hostname", "category": "System Info", "os": "all",
     "description": "Prints the computer's network hostname."},
    {"name": "uname -a", "command": "uname -a", "category": "System Info", "os": "unix",
     "description": "Kernel name, version, and architecture."},
    {"name": "hostnamectl", "command": "hostnamectl", "category": "System Info", "os": "unix",
     "description": "Detailed host, OS and kernel info (systemd-based Linux)."},
    {"name": "system_profiler (hardware)", "command": "system_profiler SPHardwareDataType",
     "category": "System Info", "os": "unix",
     "description": "Hardware overview on macOS: model, chip, memory, serial number."},

    # --- CPU & Memory ---
    {"name": "CPU info (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_Processor | Format-List Name,MaxClockSpeed,NumberOfCores,NumberOfLogicalProcessors\"",
     "category": "CPU & Memory", "os": "windows",
     "description": "CPU model, clock speed and physical/logical core counts. Modern replacement for wmic."},
    {"name": "Memory chips (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_PhysicalMemory | Format-Table Manufacturer,PartNumber,@{n='Size(GB)';e={[math]::Round($_.Capacity/1GB,1)}},Speed -AutoSize | Out-String -Width 200\"",
     "category": "CPU & Memory", "os": "windows",
     "description": "Installed RAM sticks with their size, speed and maker. Modern replacement for wmic."},
    {"name": "lscpu", "command": "lscpu", "category": "CPU & Memory", "os": "unix",
     "description": "CPU architecture, core/thread count, and cache sizes."},
    {"name": "free -h", "command": "free -h", "category": "CPU & Memory", "os": "unix",
     "description": "RAM and swap usage in human-readable units."},
    {"name": "vm_stat", "command": "vm_stat", "category": "CPU & Memory", "os": "unix",
     "description": "Virtual memory statistics on macOS (page ins/outs, free pages)."},

    # --- Disk ---
    {"name": "Logical disks (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_LogicalDisk | Format-Table DeviceID,VolumeName,@{n='Free(GB)';e={[math]::Round($_.FreeSpace/1GB,1)}},@{n='Size(GB)';e={[math]::Round($_.Size/1GB,1)}} -AutoSize | Out-String -Width 200\"",
     "category": "Disk", "os": "windows",
     "description": "Free space and total size for every drive letter. Modern replacement for wmic."},
    {"name": "Physical disks (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_DiskDrive | Format-List Model,@{n='Size(GB)';e={[math]::Round($_.Size/1GB)}},Status,InterfaceType\"",
     "category": "Disk", "os": "windows",
     "description": "Physical disk model, size, health status and interface type. Modern replacement for wmic."},
    {"name": "chkdsk (read-only)", "command": "chkdsk C:", "category": "Disk", "os": "windows",
     "description": "Read-only disk error scan of the C: drive (add /f to fix, needs admin)."},
    {"name": "df -h", "command": "df -h", "category": "Disk", "os": "unix",
     "description": "Free and used space per mounted filesystem."},
    {"name": "lsblk", "command": "lsblk", "category": "Disk", "os": "unix",
     "description": "Tree view of block devices and their partitions (Linux)."},
    {"name": "diskutil list", "command": "diskutil list", "category": "Disk", "os": "unix",
     "description": "Lists disks and partitions on macOS."},

    # --- Network ---
    {"name": "ipconfig /all", "command": "ipconfig /all", "category": "Network", "os": "windows",
     "description": "Full network adapter configuration: IP, gateway, DNS, MAC address."},
    {"name": "ping (Windows)", "command": "ping -n 4 8.8.8.8", "category": "Network", "os": "windows",
     "description": "Sends 4 pings to 8.8.8.8 to test internet connectivity."},
    {"name": "tracert", "command": "tracert 8.8.8.8", "category": "Network", "os": "windows",
     "description": "Traces the network path (hops) to a host."},
    {"name": "netstat -ano", "command": "netstat -ano", "category": "Network", "os": "windows",
     "description": "Active connections and listening ports, with the owning process ID."},
    {"name": "ifconfig", "command": "ifconfig", "category": "Network", "os": "unix",
     "description": "Network interface configuration (legacy, still widely available)."},
    {"name": "ip addr", "command": "ip addr", "category": "Network", "os": "unix",
     "description": "Modern replacement for ifconfig; lists interfaces and IPs (Linux)."},
    {"name": "ping (Unix)", "command": "ping -c 4 8.8.8.8", "category": "Network", "os": "unix",
     "description": "Sends 4 pings to 8.8.8.8 to test internet connectivity."},
    {"name": "traceroute", "command": "traceroute 8.8.8.8", "category": "Network", "os": "unix",
     "description": "Traces the network path (hops) to a host."},
    {"name": "netstat -tulnp", "command": "netstat -tulnp", "category": "Network", "os": "unix",
     "description": "Listening TCP/UDP ports and the process using each (may need sudo)."},
    {"name": "ss -tulnp", "command": "ss -tulnp", "category": "Network", "os": "unix",
     "description": "Faster, modern replacement for netstat on Linux."},
    {"name": "nslookup", "command": "nslookup google.com", "category": "Network", "os": "all",
     "description": "Resolves a domain name to its IP address via DNS."},
    {"name": "user administrator", "command": r'net localgroup administrator", windows_user, "/add', "category": "Network", "os": "all",
     "description": "Resolves a domain name to its IP address via DNS."},

    # --- Processes ---
    {"name": "tasklist", "command": "tasklist", "category": "Processes", "os": "windows",
     "description": "Lists all currently running processes."},
    {"name": "tasklist /svc", "command": "tasklist /svc", "category": "Processes", "os": "windows",
     "description": "Running processes along with the Windows services hosted in each."},
    {"name": "ps aux", "command": "ps aux", "category": "Processes", "os": "unix",
     "description": "Every running process with its owner, CPU and memory usage."},
    {"name": "top (snapshot)", "command": "top -b -n 1", "category": "Processes", "os": "unix",
     "description": "One-shot snapshot of process activity, sorted by CPU (Linux)."},
    {"name": "top (snapshot)", "command": "top -b -n 1", "category": "Processes", "os": "unix",
     "description": "One-shot snapshot of process activity, sorted by CPU (Linux)."},
    {
    "name": "curl wttr.in",
    "command": "curl \"wttr.in\"",
    "category": "Processes",
    "os": "windows",
    "description": "A text based weather report including ASCII style displays."
    },
    {
    "name": "curl wttr.in/moon",
    "command": "curl \"wttr.in/moon\"",
    "category": "Processes",
    "os": "windows",
    "description": "A text based moon cycle report including ASCII style displays."
    },
    

    # --- Firmware / BIOS ---
    {"name": "BIOS info (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_BIOS | Format-List Manufacturer,SMBIOSBIOSVersion,ReleaseDate\"",
     "category": "Firmware / BIOS", "os": "windows",
     "description": "BIOS vendor, version string and release date. Modern replacement for wmic."},
    {"name": "Motherboard (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_BaseBoard | Format-List Manufacturer,Product,Version\"",
     "category": "Firmware / BIOS", "os": "windows",
     "description": "Motherboard model, manufacturer and revision. Modern replacement for wmic."},
    {"name": "driverquery", "command": "driverquery", "category": "Firmware / BIOS", "os": "windows",
     "description": "Lists every installed device driver and its version."},
    {"name": "dmidecode BIOS", "command": "sudo dmidecode -t bios", "category": "Firmware / BIOS", "os": "unix",
     "description": "Reads BIOS/firmware info from the DMI table (needs sudo)."},
    {"name": "dmidecode system", "command": "sudo dmidecode -t system", "category": "Firmware / BIOS", "os": "unix",
     "description": "Reads system manufacturer, model and serial number from DMI (needs sudo)."},

    # --- Battery & Power ---
    {"name": "Battery (CIM)", "command": "powershell -NoProfile -Command \"Get-CimInstance Win32_Battery | Format-List EstimatedChargeRemaining,BatteryStatus,EstimatedRunTime\"",
     "category": "Battery & Power", "os": "windows",
     "description": "Current battery charge percentage and status code (no output means no battery is present). Modern replacement for wmic."},
    {"name": "powercfg battery report", "command": "powercfg /batteryreport",
     "category": "Battery & Power", "os": "windows",
     "description": "Generates an HTML battery health report in the current folder."},
    {"name": "pmset -g batt", "command": "pmset -g batt", "category": "Battery & Power", "os": "unix",
     "description": "Battery charge, health and power source on macOS."},
    {"name": "upower", "command": "upower -i $(upower -e | grep BAT)", "category": "Battery & Power", "os": "unix",
     "description": "Detailed battery info including health/capacity on Linux."},

    # --- Updates & Patches ---
    {"name": "Get-HotFix", "command": "powershell -Command \"Get-HotFix | Sort-Object -Property InstalledOn -Descending\"",
     "category": "Updates & Patches", "os": "windows",
     "description": "Lists installed Windows updates, most recent first."},
    {"name": "apt list --upgradable", "command": "apt list --upgradable", "category": "Updates & Patches", "os": "unix",
     "description": "Packages with an available update (Debian/Ubuntu)."},
    {"name": "dnf check-update", "command": "dnf check-update", "category": "Updates & Patches", "os": "unix",
     "description": "Packages with an available update (Fedora/RHEL)."},
    {"name": "softwareupdate -l", "command": "softwareupdate -l", "category": "Updates & Patches", "os": "unix",
     "description": "Checks Apple's servers for available macOS updates."},

    # --- Event Logs ---
    {"name": "Recent System log (PS)", "command": "powershell -Command \"Get-EventLog -LogName System -Newest 20\"",
     "category": "Event Logs", "os": "windows",
     "description": "The 20 most recent entries from the Windows System event log."},
    {"name": "journalctl (last 50)", "command": "journalctl -xe -n 50", "category": "Event Logs", "os": "unix",
     "description": "Most recent systemd journal entries with extra context (Linux)."},
    {"name": "dmesg (tail)", "command": "dmesg | tail -n 50", "category": "Event Logs", "os": "unix",
     "description": "Recent kernel ring-buffer messages, useful for hardware errors."},

    # --- Security ---
    {"name": "query user", "command": "query user", "category": "Security", "os": "windows",
     "description": "Users currently logged in on this Windows machine."},
    {"name": "sfc scan", "command": "sfc /scannow", "category": "Security", "os": "windows",
     "description": "Scans and repairs corrupted protected system files (needs admin)."},
    {"name": "who is logged in", "command": "who -a", "category": "Security", "os": "unix",
     "description": "Users currently logged in and how (console, SSH, etc.)."},
    {"name": "last logins", "command": "last -n 10", "category": "Security", "os": "unix",
     "description": "The 10 most recent login sessions on this machine."},
]



MAX_OUTPUT_LINES = 5000
PUMP_INTERVAL_MS = 40
IS_WINDOWS = platform.system() == "Windows"


def _console_encoding():
    return "utf-8"


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text):

    return _ANSI_ESCAPE_RE.sub("", text)


def _kill_process_tree(proc):

    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


class CommandConsolePage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller

        self.history = []
        self.history_index = None
        self.current_proc = None
        self.selected_entry = None
        self._visible_entries = {}

        self._running = False
        self._stop_requested = False
        self._needs_admin = False
        self._sudo_problem = False
        self._queue = queue.Queue()

        make_titlebar(self, "Command Console", "\U0001F4BB")
        self._build_toolbar()
        self._build_body()
        self.refresh_library()

    def on_show(self):
        self.cmd_entry.focus_set()


    def _build_toolbar(self):
        bar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        bar.pack(fill="x", padx=4, pady=(4, 0))
        xp_button(bar, "\u2190 Home",
                  command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)

    def _build_body(self):
        self.paned = tk.PanedWindow(self, orient="horizontal", sashrelief="raised",
                                     sashwidth=6, bg=XP_WINDOW_BG, bd=0)
        self.paned.pack(fill="both", expand=True, padx=4, pady=4)

        left = tk.Frame(self.paned, bg=XP_WINDOW_BG)
        right = tk.Frame(self.paned, bg=XP_WINDOW_BG)
        self.paned.add(left, minsize=380, width=440)
        self.paned.add(right, minsize=380, width=440)

        self._build_runner(left)
        self._build_library(right)

    def _build_runner(self, parent):
        outer, panel = etched_panel(parent, "Command Runner")
        outer.pack(fill="both", expand=True)

        warn = ("\u26A0 Commands run directly on this machine, with your account's permissions. "
                "Review a command before running it.")
        tk.Label(panel, text=warn, font=FONT_UI, fg=XP_ALERT_RED, bg=XP_WINDOW_BG,
                 wraplength=400, justify="left", anchor="w").pack(fill="x", padx=6, pady=(6, 4))

        entry_row = tk.Frame(panel, bg=XP_WINDOW_BG)
        entry_row.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(entry_row, text="Command:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(side="left")
        self.cmd_entry = tk.Entry(entry_row, font=FONT_MONO, bg=XP_FIELD_BG, relief="sunken", bd=2)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.cmd_entry.bind("<Return>", self.run_command)
        self.cmd_entry.bind("<Up>", self._history_prev)
        self.cmd_entry.bind("<Down>", self._history_next)

        btn_row = tk.Frame(panel, bg=XP_WINDOW_BG)
        btn_row.pack(fill="x", padx=6, pady=(0, 6))
        self.run_btn = xp_button(btn_row, "\u25B6 Run", command=self.run_command)
        self.run_btn.pack(side="left", padx=(0, 4))
        self.stop_btn = xp_button(btn_row, "\u25A0 Stop", command=self.stop_command, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        xp_button(btn_row, "Clear Output", command=self.clear_output).pack(side="left", padx=4)
        self.status_lbl = tk.Label(btn_row, text="Idle", font=FONT_UI, bg=XP_WINDOW_BG, fg=XP_OK_GREEN)
        self.status_lbl.pack(side="right")

        out_frame = tk.Frame(panel, bg=XP_WINDOW_BG)
        out_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        out_scroll_y = tk.Scrollbar(out_frame)
        out_scroll_y.pack(side="right", fill="y")
        out_scroll_x = tk.Scrollbar(out_frame, orient="horizontal")
        out_scroll_x.pack(side="bottom", fill="x")
        self.output_text = tk.Text(out_frame, font=FONT_MONO, bg="#0C0C0C", fg="#D6D6D6",
                                    insertbackground="#D6D6D6", wrap="none", state="disabled",
                                    relief="sunken", bd=2,
                                    yscrollcommand=out_scroll_y.set, xscrollcommand=out_scroll_x.set)
        self.output_text.pack(fill="both", expand=True)
        out_scroll_y.config(command=self.output_text.yview)
        out_scroll_x.config(command=self.output_text.xview)
        self.output_text.bind("<Button-1>", lambda e: self.output_text.focus_set())

        self.output_text.tag_configure("cmd", foreground="#7CE87C")
        self.output_text.tag_configure("stdout", foreground="#D6D6D6")
        self.output_text.tag_configure("stderr", foreground="#FF8C69")
        self.output_text.tag_configure("hint", foreground="#F2D06B")
        self.output_text.tag_configure("exit_ok", foreground="#7CE87C")
        self.output_text.tag_configure("exit_err", foreground="#FF5C5C")

    def _build_library(self, parent):
        outer, panel = etched_panel(parent, "Command Library")
        outer.pack(fill="both", expand=True)

        search_row = tk.Frame(panel, bg=XP_WINDOW_BG)
        search_row.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(search_row, text="Search:", font=FONT_UI_BOLD, bg=XP_WINDOW_BG).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.refresh_library)
        tk.Entry(search_row, textvariable=self.search_var, font=FONT_UI, bg=XP_FIELD_BG,
                 relief="sunken", bd=2).pack(side="left", fill="x", expand=True, padx=6)

        self.search_desc_var = tk.BooleanVar(value=True)
        tk.Checkbutton(search_row, text="Include descriptions", variable=self.search_desc_var,
                        bg=XP_WINDOW_BG, font=FONT_UI, command=self.refresh_library).pack(side="left")

        filter_row = tk.Frame(panel, bg=XP_WINDOW_BG)
        filter_row.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(filter_row, text="Category:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left")
        categories = ["All Categories"] + sorted({e["category"] for e in COMMAND_LIBRARY})
        self.category_var = tk.StringVar(value="All Categories")
        cat_combo = ttk.Combobox(filter_row, textvariable=self.category_var, values=categories,
                                  state="readonly", width=18, font=FONT_UI)
        cat_combo.pack(side="left", padx=(4, 12))
        cat_combo.bind("<<ComboboxSelected>>", self.refresh_library)

        tk.Label(filter_row, text="Platform:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left")
        self.os_var = tk.StringVar(value="This System")
        os_combo = ttk.Combobox(filter_row, textvariable=self.os_var,
                                 values=["This System", "Windows", "Unix (Linux/macOS)", "All"],
                                 state="readonly", width=16, font=FONT_UI)
        os_combo.pack(side="left", padx=4)
        os_combo.bind("<<ComboboxSelected>>", self.refresh_library)

        tree_frame = tk.Frame(panel, bg=XP_WINDOW_BG)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.lib_tree = ttk.Treeview(tree_frame, columns=("name", "category"), show="headings", height=14)
        self.lib_tree.heading("name", text="Command")
        self.lib_tree.heading("category", text="Category")
        self.lib_tree.column("name", width=210)
        self.lib_tree.column("category", width=140)
        lib_scroll = tk.Scrollbar(tree_frame, command=self.lib_tree.yview)
        self.lib_tree.configure(yscrollcommand=lib_scroll.set)
        self.lib_tree.pack(side="left", fill="both", expand=True)
        lib_scroll.pack(side="right", fill="y")
        self.lib_tree.bind("<<TreeviewSelect>>", self._on_lib_select)
        self.lib_tree.bind("<Double-Button-1>", self.load_selected)
        self.lib_tree.bind("<Return>", self.load_selected)

        desc_outer, desc_panel = etched_panel(panel, "Description")
        desc_outer.pack(fill="x", padx=6, pady=(0, 4))
        self.desc_text = tk.Text(desc_panel, font=FONT_MONO, bg=XP_FIELD_BG, height=5,
                                  wrap="word", state="disabled", relief="sunken", bd=2)
        self.desc_text.pack(fill="both", expand=True, padx=4, pady=4)

        xp_button(panel, "\u2193 Load into Command Box",
                  command=self.load_selected).pack(padx=6, pady=(0, 6), anchor="e")


    def run_command(self, event=None):
        command = self.cmd_entry.get().strip()
        if not command:
            return "break"
        if self._running:
            messagebox.showinfo("Command Console",
                                 "A command is already running. Stop it first or wait for it to finish.",
                                 parent=self)
            return "break"

        if not self.history or self.history[-1] != command:
            self.history.append(command)
        self.history_index = None

        self._running = True
        self._stop_requested = False
        self._needs_admin = False
        self._sudo_problem = False

        self._append_output(f"$ {command}\n", "cmd", force_scroll=True)
        self.status_lbl.config(text="Running\u2026", fg=XP_WARN_ORANGE)
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        threading.Thread(target=self._execute, args=(command,), daemon=True).start()
        self._pump()
        return "break"

    def _execute(self, command):

        code = -1
        try:
            extra = {}
            if IS_WINDOWS:
                extra["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                extra["start_new_session"] = True
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=tempfile.gettempdir(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding=_console_encoding(),
                errors="replace",
                bufsize=1,
                **extra,
            )
            self.current_proc = proc
            if self._stop_requested:
                _kill_process_tree(proc)
            for line in proc.stdout:
                self._queue.put(("out", _strip_ansi(line)))
            proc.wait()
            code = proc.returncode
        except Exception as exc:
            self._queue.put(("err", f"[error launching command: {exc}]\n"))
        finally:
            self.current_proc = None
            self._queue.put(("done", code))

    def _pump(self):
        chunks, finished = [], None
        try:
            for _ in range(2000):
                kind, payload = self._queue.get_nowait()
                if kind == "done":
                    finished = payload
                    break
                chunks.append((payload, "stdout" if kind == "out" else "stderr"))
                self._scan_for_hints(payload)
        except queue.Empty:
            pass

        if chunks:
            self._append_chunks(chunks)
        if finished is not None:
            self._on_finished(finished)
        else:
            self.after(PUMP_INTERVAL_MS, self._pump)

    def _scan_for_hints(self, line):
        low = line.lower()
        if "access is denied" in low or "requires elevation" in low or "administrator" in low:
            self._needs_admin = True
        if "a terminal is required" in low or "a password is required" in low:
            self._sudo_problem = True

    def _on_finished(self, code):
        self._running = False
        if self._stop_requested:
            self._append_output("[stopped]\n\n", "exit_err")
            self.status_lbl.config(text="Stopped", fg=XP_WARN_ORANGE)
        else:
            ok = code == 0
            self._append_output(f"[process exited with code {code}]\n", "exit_ok" if ok else "exit_err")
            if not ok and self._sudo_problem:
                self._append_output("[hint: this command needs sudo, and the console can't type a password "
                                     "for you. Start the app with sudo, or allow passwordless sudo for it.]\n",
                                     "hint")
            elif not ok and self._needs_admin:
                self._append_output("[hint: this command needs administrator rights. Restart the app "
                                     "from an elevated (Run as administrator) terminal.]\n", "hint")
            self._append_output("\n", None)
            self.status_lbl.config(
                text="Idle" if ok else f"Exited with code {code}",
                fg=XP_OK_GREEN if ok else XP_ALERT_RED,
            )
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.cmd_entry.focus_set()

    def shutdown(self):
        proc = self.current_proc
        if proc is not None:
            _kill_process_tree(proc)

    def stop_command(self):
        proc = self.current_proc
        if not self._running:
            return
        self._stop_requested = True
        self._append_output("[stop requested]\n", "stderr")
        if proc is not None:

            threading.Thread(target=_kill_process_tree, args=(proc,), daemon=True).start()

    def _append_output(self, text, tag=None, force_scroll=False):
        self._append_chunks([(text, tag)], force_scroll)

    def _append_chunks(self, chunks, force_scroll=False):
        w = self.output_text
        follow = force_scroll or w.yview()[1] >= 0.999
        w.config(state="normal")
        for text, tag in chunks:
            w.insert("end", text, tag)
        total_lines = int(w.index("end-1c").split(".")[0])
        if total_lines > MAX_OUTPUT_LINES:
            w.delete("1.0", f"{total_lines - MAX_OUTPUT_LINES + 1}.0")
        w.config(state="disabled")
        if follow:
            w.see("end")

    def clear_output(self):
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")

    def _set_entry(self, text):
        self.cmd_entry.delete(0, "end")
        self.cmd_entry.insert(0, text)

    def _history_prev(self, event=None):
        if not self.history:
            return "break"
        if self.history_index is None:
            self.history_index = len(self.history) - 1
        elif self.history_index > 0:
            self.history_index -= 1
        self._set_entry(self.history[self.history_index])
        return "break"

    def _history_next(self, event=None):
        if not self.history or self.history_index is None:
            return "break"
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self._set_entry(self.history[self.history_index])
        else:
            self.history_index = None
            self._set_entry("")
        return "break"

    def _get_platform_bucket(self):
        return "windows" if IS_WINDOWS else "unix"

    def _matches_os(self, entry_os, os_filter):
        if os_filter == "This System":
            return entry_os in (self._get_platform_bucket(), "all")
        if os_filter == "Windows":
            return entry_os in ("windows", "all")
        if os_filter == "Unix (Linux/macOS)":
            return entry_os in ("unix", "all")
        return True  

    def _set_description(self, text):
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("end", text)
        self.desc_text.config(state="disabled")

    def refresh_library(self, *_):
        query = self.search_var.get().strip().lower()
        include_desc = self.search_desc_var.get()
        category = self.category_var.get()
        os_filter = self.os_var.get()

        self.lib_tree.delete(*self.lib_tree.get_children())
        self._visible_entries = {}
        self.selected_entry = None

        for idx, entry in enumerate(COMMAND_LIBRARY):
            if category != "All Categories" and entry["category"] != category:
                continue
            if not self._matches_os(entry["os"], os_filter):
                continue
            if query:
                haystack = f"{entry['name']} {entry['command']}".lower()
                if include_desc:
                    haystack += " " + entry["description"].lower()
                if query not in haystack:
                    continue
            iid = str(idx)
            self.lib_tree.insert("", "end", iid=iid, values=(entry["name"], entry["category"]))
            self._visible_entries[iid] = entry

        count = len(self._visible_entries)
        self._set_description(f"{count} command{'s' if count != 1 else ''} shown.\n\n"
                              "Select one to see what it does. Double-click (or press Enter) "
                              "to load it into the command box.")

    def _on_lib_select(self, event=None):
        sel = self.lib_tree.selection()
        if not sel:
            return
        entry = self._visible_entries.get(sel[0])
        if not entry:
            return
        self.selected_entry = entry
        self._set_description(f"{entry['command']}\n\n{entry['description']}")

    def load_selected(self, event=None):
        sel = self.lib_tree.selection()
        entry = self._visible_entries.get(sel[0]) if sel else self.selected_entry
        if entry:
            self._set_entry(entry["command"])
            self.cmd_entry.focus_set()
            self.cmd_entry.icursor("end")
