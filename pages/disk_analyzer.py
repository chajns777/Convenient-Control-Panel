import os
import threading
import zlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import psutil

import osutils
import scanner
from scanner import fmt_size
from permissions import PermissionManager
from theme import (XP_WINDOW_BG, XP_FIELD_BG, FONT_UI, FONT_UI_BOLD, FONT_MONO,
                   XP_OK_GREEN, XP_WARN_ORANGE, XP_ALERT_RED, XP_BLUE_DARK,
                   make_titlebar, xp_button)

ENGINE_AUTO = "Auto (fastest available)"
ENGINE_PORTABLE = "Portable (Python only)"
MAX_CHILDREN = 1500          # rows inserted per expanded folder
TM_MAX_CHILDREN = 250        # treemap blocks per folder
TM_MAX_ITEMS = 6000          # hard cap on canvas rectangles
PALETTE = ["#E57373", "#F2A65A", "#E8D26B", "#8CC17B", "#5FB8A8",
           "#6AA9E0", "#8C8FE0", "#B586D9", "#D98BB4", "#A0A7AE"]


class DiskAnalyzerPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=XP_WINDOW_BG)
        self.controller = controller
        self.perms = PermissionManager()
        self.result = None
        self.scanning = False
        self.cancel = None
        self.progress = scanner.Progress()
        self.iid_node, self.node_iid, self._n = {}, {}, 0
        self.tm_root, self.tm_hits, self.tm_sel = None, [], None
        self._tm_items, self._tm_after = 0, None

        make_titlebar(self, "Disk Space Analyzer", "\U0001F4BD")
        self._build_toolbar()
        self._build_status()
        self._build_tabs()
        self._build_notice()

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self):
        bar = tk.Frame(self, bg=XP_WINDOW_BG, bd=1, relief="ridge")
        bar.pack(fill="x", padx=4, pady=(4, 0))
        xp_button(bar, "\u2190 Home",
                  command=lambda: self.controller.show_frame("HomePage")).pack(side="left", padx=3, pady=3)
        tk.Label(bar, text="Scan:", font=FONT_UI, bg=XP_WINDOW_BG).pack(side="left", padx=(8, 2))
        self.path_var = tk.StringVar(value=os.path.expanduser("~"))
        ttk.Combobox(bar, textvariable=self.path_var, values=self._targets(), width=30).pack(side="left", padx=2)
        xp_button(bar, "Browse...", self._browse).pack(side="left", padx=3)
        self.scan_btn = xp_button(bar, "\u25B6 Scan", self.start_scan)
        self.scan_btn.pack(side="left", padx=3)
        self.cancel_btn = xp_button(bar, "\u25A0 Cancel", self._cancel)
        self.cancel_btn.pack(side="left", padx=3)
        self.cancel_btn.config(state="disabled")
        self.engine_var = tk.StringVar(value=ENGINE_AUTO)
        ttk.Combobox(bar, textvariable=self.engine_var, state="readonly", width=22,
                     values=(ENGINE_AUTO, ENGINE_PORTABLE)).pack(side="left", padx=6)
        xp_button(bar, "\U0001F512 Permissions...", lambda: self.perms.manage(self)).pack(side="right", padx=3)

    def _build_status(self):
        row = tk.Frame(self, bg=XP_WINDOW_BG)
        row.pack(fill="x", padx=6, pady=(4, 0))
        self.status = tk.Label(row, text="Choose a folder or drive and press Scan.", font=FONT_UI,
                               bg=XP_WINDOW_BG, anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        self.pbar = ttk.Progressbar(row, mode="indeterminate", length=140)
        self.pbar.pack(side="right")

    def _build_notice(self):
        self.notice = tk.Frame(self, bg="#F5E6B8", bd=1, relief="solid")
        self.notice_lbl = tk.Label(self.notice, bg="#F5E6B8", font=FONT_UI, anchor="w", justify="left")
        self.notice_lbl.pack(side="left", padx=8, pady=4)
        self.notice_btn = xp_button(self.notice, "", None)

    def _set_notice(self, text, btn_text=None, cmd=None):
        self.notice_lbl.config(text=text, wraplength=700)
        if btn_text:
            self.notice_btn.config(text=btn_text, command=cmd)
            self.notice_btn.pack(side="right", padx=8, pady=3)
        else:
            self.notice_btn.pack_forget()
        self.notice.pack(fill="x", padx=6, pady=(4, 0), before=self.nb)

    def _clear_notice(self):
        self.notice.pack_forget()

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=4, pady=4)
        tab_tree, tab_top, tab_tm, tab_types = (tk.Frame(self.nb, bg=XP_WINDOW_BG) for _ in range(4))
        self.nb.add(tab_tree, text="Folder Tree")
        self.nb.add(tab_top, text="Largest Files")
        self.nb.add(tab_tm, text="Treemap")
        self.nb.add(tab_types, text="File Types")
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._schedule_treemap())

        # --- folder tree
        self.tree = ttk.Treeview(tab_tree, columns=("size", "pct", "files"), show="tree headings")
        for col, text, w, anc in (("#0", "Name", 380, "w"), ("size", "Size", 90, "e"),
                                  ("pct", "% of parent", 150, "w"), ("files", "Files", 90, "e")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor=anc, stretch=(col == "#0"))
        self._with_scroll(tab_tree, self.tree)
        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self._bind_context(self.tree)

        # --- largest files
        self.top_tree = ttk.Treeview(tab_top, columns=("name", "folder", "size"), show="headings")
        for col, text, w in (("name", "File", 260), ("folder", "Folder", 460), ("size", "Size", 100)):
            self.top_tree.heading(col, text=text)
            self.top_tree.column(col, width=w, anchor="e" if col == "size" else "w")
        self._with_scroll(tab_top, self.top_tree)
        self._bind_context(self.top_tree)

        # --- treemap
        head = tk.Frame(tab_tm, bg=XP_WINDOW_BG)
        head.pack(fill="x", padx=4, pady=3)
        xp_button(head, "\u2B06 Up", self._tm_up).pack(side="left")
        self.tm_path = tk.Label(head, text="", font=FONT_UI_BOLD, bg=XP_WINDOW_BG, anchor="w")
        self.tm_path.pack(side="left", padx=8)
        self.tm_canvas = tk.Canvas(tab_tm, bg="#222831", highlightthickness=0, cursor="hand2")
        self.tm_canvas.pack(fill="both", expand=True, padx=4)
        self.tm_info = tk.Label(tab_tm, text="Double-click a folder to zoom in. Right-click for actions.",
                                font=FONT_UI, bg=XP_WINDOW_BG, anchor="w")
        self.tm_info.pack(fill="x", padx=6, pady=3)
        self.tm_canvas.bind("<Configure>", lambda e: self._schedule_treemap())
        self.tm_canvas.bind("<Motion>", self._tm_hover)
        self.tm_canvas.bind("<Button-1>", self._tm_click)
        self.tm_canvas.bind("<Double-Button-1>", self._tm_double)
        self._bind_context(self.tm_canvas, treemap=True)

        # --- file types
        self.types_tree = ttk.Treeview(tab_types, columns=("ext", "files", "size", "pct"), show="headings")
        for col, text, w in (("ext", "Extension", 160), ("files", "Files", 110),
                             ("size", "Total size", 120), ("pct", "% of scanned files", 160)):
            self.types_tree.heading(col, text=text)
            self.types_tree.column(col, width=w, anchor="w" if col == "ext" else "e")
        self._with_scroll(tab_types, self.types_tree)

    @staticmethod
    def _with_scroll(parent, tree):
        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 4), pady=4)
        tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)

    def _bind_context(self, widget, treemap=False):
        def handler(event):
            if treemap:
                node = self._tm_node_at(event.x, event.y)
                if node:
                    self._tm_select(node)
            else:
                iid = widget.identify_row(event.y)
                node = self.iid_node.get(iid)
                if node:
                    widget.selection_set(iid)
            if node:
                self._show_menu(event, node)
        widget.bind("<Button-3>", handler)
        if osutils.IS_MAC:
            widget.bind("<Button-2>", handler)
            widget.bind("<Control-Button-1>", handler)

    @staticmethod
    def _targets():
        out = []
        try:
            out = [p.mountpoint for p in psutil.disk_partitions(all=False)]
        except Exception:
            pass
        home = os.path.expanduser("~")
        return out + ([home] if home not in out else [])

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.path_var.get() or None)
        if d:
            self.path_var.set(d)

    # ------------------------------------------------------------ scanning
    def _plan_engine(self, path, force):
        """Decide engine, and ask permission before anything needs elevation."""
        if self.engine_var.get() == ENGINE_PORTABLE and not force:
            return "portable", False, []
        if osutils.IS_WIN and scanner.is_ntfs_volume(path):
            if osutils.is_admin():
                return "mft", False, []
            detail = f"Drive {os.path.splitdrive(path)[0]}\nFast NTFS scan via an elevated helper process."
            if self.perms.request(self, "elevated_scan", detail):
                return "mft", True, []
            return "portable", False, ["Administrator scan declined - used the slower portable scanner."]
        if osutils.IS_LINUX and scanner.find_supported():
            if osutils.is_admin():
                return "find", False, []
            if force:
                if self.perms.request(self, "elevated_scan", f"Folder: {path}\nScan as root via pkexec."):
                    return "find", True, []
                return None
            return "find", False, []
        if force:
            messagebox.showinfo("Not available", "Administrator scanning isn't available for this "
                                "drive or operating system.", parent=self)
            return None
        return "portable", False, []

    def start_scan(self, force_elevated=False):
        if self.scanning:
            return
        path = self.path_var.get().strip()
        if not path or not os.path.isdir(path):
            messagebox.showerror("Scan", "That folder doesn't exist.", parent=self)
            return
        plan = self._plan_engine(path, force_elevated)
        if plan is None:
            return
        engine, elevated, pre_notes = plan
        self.scanning = True
        self.cancel = threading.Event()
        self.progress = scanner.Progress()
        self._clear_notice()
        self.scan_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.pbar.start(12)
        threading.Thread(target=self._worker, args=(path, engine, elevated, pre_notes), daemon=True).start()
        self._poll()

    def _worker(self, path, engine, elevated, pre_notes):
        result = err = None
        try:
            result = scanner.run_scan(path, engine, elevated, self.progress, self.cancel)
            if result:
                result.notes = pre_notes + result.notes
        except Exception as exc:       # noqa: BLE001
            err = exc
        try:
            self.after(0, lambda: self._scan_done(result, err, path))
        except (tk.TclError, RuntimeError):
            pass

    def _poll(self):
        if not self.scanning:
            return
        p = self.progress
        self.status.config(text=f"{p.phase}   {p.files:,} files, {p.dirs:,} folders"
                                f"{'   |   ' + p.current[-70:] if p.current else ''}", fg="black")
        self.after(150, self._poll)

    def _cancel(self):
        if self.cancel:
            self.cancel.set()
            self.status.config(text="Cancelling...")

    def shutdown(self):
        if self.cancel:
            self.cancel.set()

    def _scan_done(self, result, err, path):
        self.scanning = False
        self.pbar.stop()
        self.scan_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        if err is not None:
            self.status.config(text=f"Scan failed: {err}", fg=XP_ALERT_RED)
            return
        if result is None:
            self.status.config(text="Scan cancelled.", fg=XP_WARN_ORANGE)
            return
        self.result = result
        self._populate_all()
        text = (f"{result.files:,} files, {result.dirs:,} folders, {fmt_size(result.root.size)} "
                f"in {result.seconds:.1f}s  -  {result.engine}")
        self.status.config(text=text, fg=XP_OK_GREEN)
        notes = list(result.notes)
        if result.skipped and not osutils.is_admin():
            if osutils.IS_MAC:
                notes.append(f"{result.skipped:,} folders were blocked by macOS privacy protection. "
                             "Grant this terminal/Python 'Full Disk Access' and rescan.")
                self._set_notice(" ".join(notes), "Open Privacy Settings", osutils.open_full_disk_access_settings)
                return
            helps = ((osutils.IS_WIN and scanner.is_ntfs_volume(path) and "MFT" not in result.engine)
                     or (osutils.IS_LINUX and scanner.find_supported()))
            notes.append(f"{result.skipped:,} folders couldn't be read, so sizes may be understated.")
            if helps:
                self._set_notice(" ".join(notes), "Rescan as administrator...",
                                 lambda: self.start_scan(force_elevated=True))
                return
        if notes:
            self._set_notice(" ".join(notes))

    # ---------------------------------------------------------- populate UI
    def _populate_all(self):
        r = self.result
        self.tm_root = r.root
        self._fill_tree()
        self._fill_top()
        self._fill_types()
        self._schedule_treemap()

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.iid_node.clear()
        self.node_iid.clear()
        iid = self._insert(self.tree, "", self.result.root)
        self.tree.item(iid, open=True)
        self._expand(iid)

    def _insert(self, tree, parent_iid, node):
        iid = f"n{self._n}"
        self._n += 1
        self.iid_node[iid] = node
        self.node_iid[id(node)] = iid
        icon = "\U0001F4C1 " if node.is_dir else "\U0001F4C4 "
        tree.insert(parent_iid, "end", iid=iid, text=icon + node.name, values=self._row(node))
        if node.is_dir and node.children:
            tree.insert(iid, "end", iid=iid + "_dummy", text="")
        return iid

    @staticmethod
    def _row(node):
        base = node.parent.size if node.parent is not None else node.size
        pct = 100.0 * node.size / base if base else 0.0
        bar = "\u2588" * int(round(pct / 10)) + "\u2591" * (10 - int(round(pct / 10)))
        return (fmt_size(node.size), f"{bar} {pct:4.1f}%", f"{node.file_count:,}" if node.is_dir else "")

    def _on_open(self, event=None):
        self._expand(self.tree.focus())

    def _expand(self, iid):
        node = self.iid_node.get(iid)
        kids = self.tree.get_children(iid)
        if not node or len(kids) != 1 or not kids[0].endswith("_dummy"):
            return
        self.tree.delete(kids[0])
        for ch in node.children[:MAX_CHILDREN]:
            self._insert(self.tree, iid, ch)
        extra = len(node.children) - MAX_CHILDREN
        if extra > 0:
            self.tree.insert(iid, "end", text=f"... {extra:,} smaller items not shown", values=("", "", ""))

    def _fill_top(self):
        self.top_tree.delete(*self.top_tree.get_children())
        for node in self.result.top_files:
            iid = f"f{self._n}"
            self._n += 1
            self.iid_node[iid] = node
            path = node.full_path()
            self.top_tree.insert("", "end", iid=iid,
                                 values=(node.name, os.path.dirname(path), fmt_size(node.size)))

    def _fill_types(self):
        self.types_tree.delete(*self.types_tree.get_children())
        total = sum(v[0] for v in self.result.ext_stats.values()) or 1
        for ext, (size, cnt) in sorted(self.result.ext_stats.items(), key=lambda kv: -kv[1][0])[:500]:
            self.types_tree.insert("", "end", values=(ext, f"{cnt:,}", fmt_size(size), f"{100 * size / total:.1f}%"))

    def _refresh_rows(self):
        for iid, node in list(self.iid_node.items()):
            if iid.startswith("n") and self.tree.exists(iid):
                self.tree.item(iid, values=self._row(node))

    # ---------------------------------------------------------- context menu
    def _show_menu(self, event, node):
        path = node.full_path()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="Open", command=lambda: self._try(osutils.open_path, path))
        m.add_command(label=f"Show in {osutils.FILE_MANAGER}",
                      command=lambda: self._try(osutils.reveal_in_file_manager, path))
        m.add_command(label="Copy path", command=lambda: self._copy(path))
        if node.is_dir or node.parent is not None:
            m.add_command(label="Show in treemap", command=lambda: self._show_in_treemap(node))
        m.add_separator()
        m.add_command(label=f"Move to {osutils.TRASH}", command=lambda: self._delete(node, False))
        m.add_command(label="Delete permanently...", command=lambda: self._delete(node, True))
        m.tk_popup(event.x_root, event.y_root)

    def _try(self, fn, *args):
        try:
            fn(*args)
        except Exception as exc:       # noqa: BLE001
            messagebox.showerror("Error", str(exc), parent=self)

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _show_in_treemap(self, node):
        self.tm_root = node if node.is_dir and node.children else (node.parent or node)
        self.nb.select(2)
        self._schedule_treemap()

    # ----------------------------------------------------------------- delete
    def _delete(self, node, permanent):
        if self.scanning:
            messagebox.showinfo("Busy", "Wait for the scan to finish first.", parent=self)
            return
        if node.parent is None:
            messagebox.showinfo("Not allowed", "The scan root itself can't be deleted from here.", parent=self)
            return
        path = node.full_path()
        if osutils.is_protected(path):
            messagebox.showerror("Protected location", f"Deleting this is blocked for safety:\n{path}", parent=self)
            return
        detail = f"{path}\n{fmt_size(node.size)}" + (f" in {node.file_count:,} file(s)" if node.is_dir else "")
        if not self.perms.request(self, "delete_permanent" if permanent else "delete_trash", detail):
            return
        self.status.config(text=f"Deleting {node.name}...", fg="black")

        def job():
            (osutils.delete_permanently if permanent else osutils.move_to_trash)(path)

        self._bg(job, lambda exc: self._delete_done(node, path, detail, exc))

    def _delete_done(self, node, path, detail, exc):
        if exc is None:
            self._after_delete(node)
            return
        if isinstance(exc, ImportError):
            messagebox.showerror("Missing package", "Moving to the trash needs:\n\n    pip install Send2Trash",
                                 parent=self)
        elif isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError):
            if self.perms.request(self, "elevated_delete", f"{detail}\n\nRefused with: {exc}"):
                self.status.config(text="Deleting with administrator rights...", fg="black")
                self._bg(lambda: scanner.elevated_delete(path), lambda e2: self._elev_done(node, path, e2))
                return
        else:
            messagebox.showerror("Delete failed", str(exc), parent=self)
        self.status.config(text="Delete cancelled / failed.", fg=XP_WARN_ORANGE)

    def _elev_done(self, node, path, exc):
        if exc is None or not os.path.lexists(path):
            self._after_delete(node)
        else:
            self.status.config(text="Delete failed.", fg=XP_ALERT_RED)
            messagebox.showerror("Delete failed", str(exc), parent=self)

    def _after_delete(self, node):
        r = self.result
        old_parent, size, name = node.parent, node.size, node.name
        files = list(scanner.iter_files(node))
        scanner.remove_node(node)                       # fixes every ancestor's size/count
        for f in files:
            ent = r.ext_stats.get(scanner.ext_of(f.name))
            if ent:
                ent[0] -= f.size
                ent[1] -= 1
                if ent[1] <= 0:
                    r.ext_stats.pop(scanner.ext_of(f.name), None)
        r.top_files = [n for n in r.top_files if not scanner.is_within(n, node)]
        r.files -= len(files)
        if self.tm_root is not None and scanner.is_within(self.tm_root, node):
            self.tm_root = old_parent
        iid = self.node_iid.get(id(node))
        if iid and self.tree.exists(iid):
            self.tree.delete(iid)
        self._refresh_rows()
        self._fill_top()
        self._fill_types()
        self._schedule_treemap()
        self.status.config(text=f"Removed {name} - freed {fmt_size(size)}.", fg=XP_OK_GREEN)

    def _bg(self, fn, done):
        def run():
            exc = None
            try:
                fn()
            except BaseException as e:      # noqa: BLE001
                exc = e
            try:
                self.after(0, lambda: done(exc))
            except (tk.TclError, RuntimeError):
                pass
        threading.Thread(target=run, daemon=True).start()

    # ---------------------------------------------------------------- treemap
    def _schedule_treemap(self):
        if self._tm_after:
            self.after_cancel(self._tm_after)
        self._tm_after = self.after(120, self._draw_treemap)

    def _draw_treemap(self):
        self._tm_after = None
        try:
            if self.nb.index(self.nb.select()) != 2:
                return
        except tk.TclError:
            return
        c = self.tm_canvas
        c.delete("all")
        self.tm_hits = []
        node = self.tm_root
        if node is None:
            return
        w, h = c.winfo_width(), c.winfo_height()
        if w < 30 or h < 30:
            return
        self._tm_items = 0
        self._tm_layout(node, 2, 2, w - 4, h - 4, 2)
        self.tm_path.config(text=f"{node.full_path()}   -   {fmt_size(node.size)}")

    def _tm_layout(self, node, x, y, w, h, depth):
        kids = [k for k in node.children[:TM_MAX_CHILDREN] if k.size > 0]
        if not kids or w < 4 or h < 4:
            return
        c = self.tm_canvas
        for k, (rx, ry, rw, rh) in zip(kids, scanner.squarify([k.size for k in kids], x, y, w, h)):
            if rw < 3 or rh < 3 or self._tm_items > TM_MAX_ITEMS:
                continue
            x1, y1, x2, y2 = rx, ry, rx + rw, ry + rh
            self._tm_items += 1
            nested = k.is_dir and depth > 0 and rw > 48 and rh > 34 and k.children
            if nested:
                c.create_rectangle(x1, y1, x2, y2, fill="#3A4556", outline="#1F3F63")
                self.tm_hits.append((x1, y1, x2, y2, k))
                self._tm_label(k, x1, y1, rw)
                self._tm_layout(k, x1 + 2, y1 + 15, rw - 4, rh - 17, depth - 1)
            else:
                fill = "#6E97C4" if k.is_dir else PALETTE[zlib.crc32(scanner.ext_of(k.name).encode()) % len(PALETTE)]
                c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="#222831")
                self.tm_hits.append((x1, y1, x2, y2, k))
                if rw > 60 and rh > 18:
                    self._tm_label(k, x1, y1, rw, dark=True)

    def _tm_label(self, node, x, y, w, dark=False):
        chars = int((w - 6) / 6)
        if chars >= 3:
            self.tm_canvas.create_text(x + 3, y + 2, anchor="nw", font=("Tahoma", 8),
                                       fill="#111111" if dark else "white",
                                       text=node.name[:chars] + ("..." if len(node.name) > chars else ""))

    def _tm_node_at(self, x, y):
        for x1, y1, x2, y2, node in reversed(self.tm_hits):    # last drawn = deepest
            if x1 <= x <= x2 and y1 <= y <= y2:
                return node
        return None

    def _tm_hover(self, event):
        node = self._tm_node_at(event.x, event.y)
        if node:
            base = self.tm_root.size or 1
            self.tm_info.config(text=f"{node.full_path()}   -   {fmt_size(node.size)} "
                                     f"({100 * node.size / base:.1f}% of view)")

    def _tm_select(self, node):
        c = self.tm_canvas
        c.delete("sel")
        for x1, y1, x2, y2, n in self.tm_hits:
            if n is node:
                c.create_rectangle(x1, y1, x2, y2, outline="#FFE600", width=3, tags="sel")
                break

    def _tm_click(self, event):
        node = self._tm_node_at(event.x, event.y)
        if node:
            self._tm_select(node)

    def _tm_double(self, event):
        node = self._tm_node_at(event.x, event.y)
        if node and node.is_dir and node.children:
            self.tm_root = node
            self._draw_treemap()

    def _tm_up(self):
        if self.tm_root is not None and self.tm_root.parent is not None:
            self.tm_root = self.tm_root.parent
            self._draw_treemap()
