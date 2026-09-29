import threading
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import hardware_monitor as hw
import database as db
from theme import (XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_MONO,
                    XP_OK_GREEN, XP_WARN_ORANGE, XP_ALERT_RED,
                    make_titlebar, etched_panel, xp_button, status_dot)

HISTORY_LEN = 60


class HardwareCheckPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller

        self.cpu_history = deque(maxlen=HISTORY_LEN)
        self.ram_history = deque(maxlen=HISTORY_LEN)
        self.temp_history = deque(maxlen=HISTORY_LEN)
        self.sample_index = deque(maxlen=HISTORY_LEN)
        self._tick = 0
        self._auto_job = None
        self.last_snapshot = None

        make_titlebar(self, "Hardware & Firmware Check", "\U0001F5A5")
        self._build_toolbar()
        self._build_tabs()

        self.refresh(initial=True)

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        bar.pack(fill="x", padx=4, pady=(4, 0))

        xp_button(bar, "\u2190 Home",
                  command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)
        xp_button(bar, "\U0001F504 Refresh Now", command=self.refresh).pack(side="left", padx=3, pady=3)
        xp_button(bar, "\U0001F4BE Save Report", command=self.save_report).pack(side="left", padx=3, pady=3)

        self.auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Auto-refresh every 5s", variable=self.auto_var, bg=XP_WINDOW_BG,
                        font=FONT_UI, command=self._toggle_auto).pack(side="left", padx=10)

        self.status_lbl = tk.Label(bar, text="", bg=XP_WINDOW_BG, font=FONT_UI)
        self.status_lbl.pack(side="right", padx=8)

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        self.tab_overview = tk.Frame(nb, bg=XP_WINDOW_BG)
        self.tab_graphs = tk.Frame(nb, bg=XP_WINDOW_BG)
        self.tab_details = tk.Frame(nb, bg=XP_WINDOW_BG)
        nb.add(self.tab_overview, text="Overview")
        nb.add(self.tab_graphs, text="Performance Graphs")
        nb.add(self.tab_details, text="Details")

        self._build_overview_tab()
        self._build_graphs_tab()
        self._build_details_tab()

    def _build_overview_tab(self):
        top = tk.Frame(self.tab_overview, bg=XP_WINDOW_BG)
        top.pack(fill="x", padx=6, pady=6)

        sys_outer, sys_panel = etched_panel(top, "System")
        sys_outer.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.sys_text = tk.Label(sys_panel, text="", justify="left", anchor="w",
                                  font=FONT_MONO, bg=XP_WINDOW_BG)
        self.sys_text.pack(fill="both", expand=True, padx=6, pady=6)

        fw_outer, fw_panel = etched_panel(top, "Firmware / BIOS")
        fw_outer.pack(side="left", fill="both", expand=True, padx=4)
        self.fw_text = tk.Label(fw_panel, text="", justify="left", anchor="w",
                                 font=FONT_MONO, bg=XP_WINDOW_BG)
        self.fw_text.pack(fill="both", expand=True, padx=6, pady=6)

        upd_outer, upd_panel = etched_panel(top, "Updates")
        upd_outer.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.update_lbl = tk.Label(upd_panel, text="Click 'Check for Updates'", justify="left",
                                    anchor="w", wraplength=190, font=FONT_UI, bg=XP_WINDOW_BG)
        self.update_lbl.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        xp_button(upd_panel, "Check for Updates", command=self.check_updates).pack(padx=6, pady=6, anchor="w")

        maint_outer, maint_panel = etched_panel(self.tab_overview, "Maintenance Recommendations")
        maint_outer.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.maint_list = tk.Frame(maint_panel, bg=XP_WINDOW_BG)
        self.maint_list.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_graphs_tab(self):
        self.fig = Figure(figsize=(9, 5.2), dpi=90)
        self.ax_cpu = self.fig.add_subplot(311)
        self.ax_ram = self.fig.add_subplot(312)
        self.ax_temp = self.fig.add_subplot(313)
        self.fig.subplots_adjust(hspace=0.65)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_graphs)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=6)
        self._style_axes()

    def _style_axes(self):
        for ax, title in (
            (self.ax_cpu, "CPU Usage (%)"),
            (self.ax_ram, "RAM Usage (%)"),
            (self.ax_temp, "Temperature (\u00b0C)"),
        ):
            ax.clear()
            ax.set_title(title, fontsize=9, loc="left")
            ax.set_ylim(0, 100 if ax is not self.ax_temp else 110)
            ax.tick_params(labelsize=7)
            ax.grid(True, linestyle=":", alpha=0.5)

    def _build_details_tab(self):
        cols = ("metric", "value")
        self.details_tree = ttk.Treeview(self.tab_details, columns=cols, show="headings", height=20)
        self.details_tree.heading("metric", text="Metric")
        self.details_tree.heading("value", text="Value")
        self.details_tree.column("metric", width=260)
        self.details_tree.column("value", width=440)
        self.details_tree.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh(self, initial=False):
        snap = hw.full_snapshot()
        self.last_snapshot = snap
        self._tick += 1

        self.cpu_history.append(snap["cpu"]["usage_percent"])
        self.ram_history.append(snap["memory"]["percent"])
        temp_val = max(snap["temperatures"].values()) if snap["temperatures"] else None
        self.temp_history.append(temp_val)
        self.sample_index.append(self._tick)

        self._render_overview(snap)
        self._render_graphs()
        self._render_details(snap)

        prefix = "Loaded" if initial else "Last updated"
        self.status_lbl.config(text=f"{prefix}: {snap['captured_at']}", fg=XP_OK_GREEN)

    def _render_overview(self, snap):
        s = snap["system"]
        self.sys_text.config(text=(
            f"Host:       {s['hostname']}\n"
            f"OS:         {s['os']}\n"
            f"Arch:       {s['architecture']}\n"
            f"Processor:  {s['processor'][:34]}\n"
            f"Uptime:     {s['uptime']}\n"
            f"Boot time:  {s['boot_time']}"
        ))
        f = snap["firmware"]
        self.fw_text.config(text=(
            f"BIOS vendor: {f['bios_vendor']}\n"
            f"BIOS ver:    {f['bios_version']}\n"
            f"BIOS date:   {f['bios_date']}\n"
            f"Source:      {f['source']}"
        ))

        for w in self.maint_list.winfo_children():
            w.destroy()
        color_map = {"ok": XP_OK_GREEN, "warn": XP_WARN_ORANGE, "alert": XP_ALERT_RED}
        for severity, msg in snap["maintenance"]:
            row = tk.Frame(self.maint_list, bg=XP_WINDOW_BG)
            row.pack(fill="x", anchor="w", pady=1)
            status_dot(row, severity).pack(side="left", padx=(0, 6))
            tk.Label(row, text=msg, bg=XP_WINDOW_BG, fg=color_map[severity],
                     font=FONT_UI, anchor="w").pack(side="left")

    def _render_graphs(self):
        self._style_axes()
        x = list(self.sample_index)
        self.ax_cpu.plot(x, list(self.cpu_history), color="#245EDC", linewidth=1.5)
        self.ax_ram.plot(x, list(self.ram_history), color="#B36A00", linewidth=1.5)
        temps = [t for t in self.temp_history if t is not None]
        if temps:
            tx = [xi for xi, t in zip(x, self.temp_history) if t is not None]
            self.ax_temp.plot(tx, temps, color="#B00000", linewidth=1.5)
        else:
            self.ax_temp.text(0.5, 0.5, "No temperature sensors reported by this system",
                               ha="center", va="center", fontsize=8, transform=self.ax_temp.transAxes)
        self.canvas.draw_idle()

    def _render_details(self, snap):
        for row in self.details_tree.get_children():
            self.details_tree.delete(row)

        cpu = snap["cpu"]
        self.details_tree.insert("", "end", values=("Physical cores", cpu["physical_cores"]))
        self.details_tree.insert("", "end", values=("Logical cores", cpu["logical_cores"]))
        self.details_tree.insert("", "end", values=("Current frequency",
                                                      f"{cpu['current_freq_mhz']} MHz" if cpu["current_freq_mhz"] else "Unavailable"))
        self.details_tree.insert("", "end", values=("Max frequency",
                                                      f"{cpu['max_freq_mhz']} MHz" if cpu["max_freq_mhz"] else "Unavailable"))
        self.details_tree.insert("", "end", values=("Per-core usage",
                                                      ", ".join(f"{c}%" for c in cpu["per_core_percent"])))

        mem = snap["memory"]
        self.details_tree.insert("", "end", values=("RAM total", f"{mem['total_gb']} GB"))
        self.details_tree.insert("", "end", values=("RAM used", f"{mem['used_gb']} GB ({mem['percent']}%)"))
        self.details_tree.insert("", "end", values=("RAM available", f"{mem['available_gb']} GB"))
        self.details_tree.insert("", "end", values=("Swap used", f"{mem['swap_used_gb']} / {mem['swap_total_gb']} GB"))

        for d in snap["disks"]:
            self.details_tree.insert("", "end", values=(
                f"Disk {d['device']}", f"{d['used_gb']}/{d['total_gb']} GB used ({d['percent']}%)"))

        for n in snap["network"]:
            self.details_tree.insert("", "end", values=(
                f"Network: {n['name']}", f"{n['ip']}   {'UP' if n['is_up'] else 'DOWN'}   {n['speed_mbps']} Mbps"))

        if snap["temperatures"]:
            for label, c in snap["temperatures"].items():
                self.details_tree.insert("", "end", values=(f"Temp: {label}", f"{c:.1f}\u00b0C"))
        else:
            self.details_tree.insert("", "end", values=("Temperature sensors", "Not reported by this OS/hardware"))

        b = snap["battery"]
        if b:
            self.details_tree.insert("", "end", values=(
                "Battery", f"{b['percent']}% ({'plugged in' if b['plugged_in'] else 'on battery'})"))
        else:
            self.details_tree.insert("", "end", values=("Battery", "No battery detected"))

    def _toggle_auto(self):
        if self.auto_var.get():
            self._auto_refresh_loop()
        elif self._auto_job:
            self.after_cancel(self._auto_job)
            self._auto_job = None

    def _auto_refresh_loop(self):
        self.refresh()
        if self.auto_var.get():
            self._auto_job = self.after(5000, self._auto_refresh_loop)

    def check_updates(self):
        self.update_lbl.config(text="Checking (this can take a few seconds)...")

        def worker():
            result = hw.check_os_updates()
            self.after(0, lambda: self.update_lbl.config(text=result["message"]))

        threading.Thread(target=worker, daemon=True).start()

    def save_report(self):
        if not self.last_snapshot:
            return
        title = f"Diagnostic Report - {self.last_snapshot['captured_at']}"
        db.save_report(title, self.last_snapshot)
        messagebox.showinfo("Report Saved", f"Saved as:\n{title}", parent=self)
        if hasattr(self.controller, "notify_new_report"):
            self.controller.notify_new_report()
