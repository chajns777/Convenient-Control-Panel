import json
import tkinter as tk
from tkinter import ttk, messagebox

import database as db
from theme import (XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_MONO,
                    make_titlebar, etched_panel, xp_button)


class ReportsPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller
        self.selected_id = None

        make_titlebar(self, "Report Archive", "\U0001F4C1")

        toolbar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        toolbar.pack(fill="x", padx=4, pady=(4, 0))
        xp_button(toolbar, "\u2190 Home",
                  command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)
        xp_button(toolbar, "\U0001F504 Refresh List", command=self.reload_list).pack(side="left", padx=3, pady=3)
        xp_button(toolbar, "\U0001F5D1 Delete Report", command=self.delete_selected).pack(side="left", padx=3, pady=3)

        body = tk.Frame(self, bg=XP_WINDOW_BG)
        body.pack(fill="both", expand=True, padx=4, pady=4)

        list_outer, list_panel = etched_panel(body, "Saved Reports")
        list_outer.pack(side="left", fill="y", padx=(0, 4))
        list_outer.configure(width=260)
        list_outer.pack_propagate(False)
        self.tree = ttk.Treeview(list_panel, columns=("title",), show="headings", height=25)
        self.tree.heading("title", text="Report")
        self.tree.column("title", width=230)
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = tk.Frame(body, bg=XP_WINDOW_BG)
        right.pack(side="left", fill="both", expand=True)

        detail_outer, detail_panel = etched_panel(right, "Report Summary")
        detail_outer.pack(fill="both", expand=True, pady=(0, 4))
        self.detail_text = tk.Text(detail_panel, font=FONT_MONO, bg=XP_FIELD_BG, height=14,
                                    wrap="word", state="disabled", relief="sunken", bd=2)
        self.detail_text.pack(fill="both", expand=True, padx=6, pady=6)

        notes_outer, notes_panel = etched_panel(right, "Notes")
        notes_outer.pack(fill="both", expand=True)
        self.notes_text = tk.Text(notes_panel, font=FONT_UI, bg=XP_FIELD_BG, height=8,
                                   wrap="word", relief="sunken", bd=2)
        self.notes_text.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        xp_button(notes_panel, "\U0001F4BE Save Notes", command=self.save_notes).pack(anchor="e", padx=6, pady=6)

        self.reload_list()

    def reload_list(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in db.list_reports():
            self.tree.insert("", "end", iid=str(r["id"]), values=(r["title"],))
        self.selected_id = None
        self._clear_detail()

    def _clear_detail(self):
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "Select a report on the left to view its details.")
        self.detail_text.config(state="disabled")
        self.notes_text.delete("1.0", "end")

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        report_id = int(sel[0])
        self.selected_id = report_id
        row = db.get_report(report_id)
        if not row:
            return
        summary = json.loads(row["summary_json"])
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", self._format_summary(row["title"], row["created_at"], summary))
        self.detail_text.config(state="disabled")
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", row["notes"] or "")

    def _format_summary(self, title, created_at, s):
        lines = [title, f"Saved: {created_at}", "-" * 52]
        sysinfo = s.get("system", {})
        lines.append(f"Host: {sysinfo.get('hostname')}   OS: {sysinfo.get('os')}")
        lines.append(f"Uptime at capture: {sysinfo.get('uptime')}")
        cpu = s.get("cpu", {})
        lines.append(f"CPU usage: {cpu.get('usage_percent')}%   "
                     f"Cores: {cpu.get('physical_cores')}P / {cpu.get('logical_cores')}L")
        mem = s.get("memory", {})
        lines.append(f"RAM usage: {mem.get('percent')}%  ({mem.get('used_gb')}/{mem.get('total_gb')} GB)")
        for d in s.get("disks", []):
            lines.append(f"Disk {d['device']}: {d['percent']}% used ({d['free_gb']} GB free)")
        temps = s.get("temperatures", {})
        if temps:
            for label, c in temps.items():
                lines.append(f"Temp {label}: {c:.1f}\u00b0C")
        fw = s.get("firmware", {})
        lines.append(f"BIOS: {fw.get('bios_vendor')} {fw.get('bios_version')} ({fw.get('bios_date')})")
        lines.append("-" * 52)
        lines.append("Maintenance flags at time of capture:")
        for severity, msg in s.get("maintenance", []):
            lines.append(f"  [{severity.upper()}] {msg}")
        return "\n".join(lines)

    def save_notes(self):
        if self.selected_id is None:
            messagebox.showwarning("No report selected", "Select a report first.", parent=self)
            return
        notes = self.notes_text.get("1.0", "end").rstrip("\n")
        db.update_notes(self.selected_id, notes)
        messagebox.showinfo("Saved", "Notes saved.", parent=self)

    def delete_selected(self):
        if self.selected_id is None:
            return
        if messagebox.askyesno("Delete report", "Delete this report permanently?", parent=self):
            db.delete_report(self.selected_id)
            self.reload_list()
