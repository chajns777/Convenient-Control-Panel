import json
import os
import sys
import tkinter as tk

from theme import (XP_WINDOW_BG, XP_BLUE_DARK, XP_ALERT_RED, XP_FIELD_BG, XP_OK_GREEN, XP_TEXT,
                   FONT_UI, FONT_UI_BOLD, FONT_MONO, make_titlebar, xp_button)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permissions.json")

_OS_PROMPT = ("Windows will also show its own UAC prompt." if sys.platform == "win32" else
              "macOS will ask for your password." if sys.platform == "darwin" else
              "Your desktop will ask for your password (polkit).")

CAPABILITIES = {
    "elevated_scan": {
        "title": "Administrator disk scan",
        "why": ("A much faster scan needs elevated rights: on Windows it reads the NTFS Master File Table "
                "directly, on Linux it can also read folders your user can't. Only a small helper "
                "process is elevated - this app keeps running normally. " + _OS_PROMPT),
        "danger": False,
    },
    "delete_trash": {
        "title": "Move items to the " + ("Recycle Bin" if sys.platform == "win32" else "Trash"),
        "why": "The selected item will be moved to the " +
               ("Recycle Bin" if sys.platform == "win32" else "Trash") + ". You can restore it from there.",
        "danger": False,
    },
    "delete_permanent": {
        "title": "Delete permanently",
        "why": "The selected item will be erased immediately and cannot be recovered.",
        "danger": True,
    },
    "elevated_delete": {
        "title": "Delete with administrator rights",
        "why": ("The normal delete was refused by the operating system. Retrying with administrator "
                "rights will PERMANENTLY erase the item (no Recycle Bin / Trash). " + _OS_PROMPT),
        "danger": True,
    },
}


class _PermissionDialog(tk.Toplevel):
    def __init__(self, parent, cap, detail):
        super().__init__(parent)
        info = CAPABILITIES[cap]
        self.result = "deny"
        self.title("Permission required")
        self.configure(bg=XP_WINDOW_BG)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        make_titlebar(self, info["title"], "\U0001F512")

        body = tk.Frame(self, bg=XP_WINDOW_BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(body, text=info["title"], font=FONT_UI_BOLD, bg=XP_WINDOW_BG,
                 fg=XP_ALERT_RED if info["danger"] else XP_BLUE_DARK, anchor="w").pack(fill="x")
        tk.Label(body, text=info["why"], font=FONT_UI, bg=XP_WINDOW_BG, fg=XP_TEXT, justify="left",
                 anchor="w", wraplength=440).pack(fill="x", pady=(6, 8))
        if detail:
            tk.Label(body, text=detail, font=FONT_MONO, bg=XP_FIELD_BG, fg=XP_TEXT, justify="left",
                     anchor="w", wraplength=430, relief="sunken", bd=2, padx=6, pady=6).pack(fill="x")
        tk.Label(body, text="'Always allow' is remembered; you can revoke it under Permissions.",
                 font=FONT_UI, bg=XP_WINDOW_BG, fg="#555555", anchor="w", wraplength=440,
                 justify="left").pack(fill="x", pady=(8, 0))

        row = tk.Frame(self, bg=XP_WINDOW_BG)
        row.pack(fill="x", padx=16, pady=(0, 14))
        xp_button(row, "Don't allow", lambda: self._done("deny"), width=13).pack(side="right", padx=(6, 0))
        xp_button(row, "Always allow", lambda: self._done("always"), width=13).pack(side="right", padx=6)
        xp_button(row, "Allow once", lambda: self._done("once"), width=13).pack(side="right", padx=6)

        self.protocol("WM_DELETE_WINDOW", lambda: self._done("deny"))
        self.bind("<Escape>", lambda e: self._done("deny"))
        self.update_idletasks()
        top = parent.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_width()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()
        self.wait_window()

    def _done(self, result):
        self.result = result
        self.destroy()


class PermissionManager:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._data = self._load()

    def _load(self):
        try:
            with open(self.path) as fh:
                data = json.load(fh)
            return {k: True for k, v in data.items() if v is True and k in CAPABILITIES}
        except (OSError, ValueError, AttributeError):
            return {}

    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def is_always(self, cap):
        return self._data.get(cap) is True

    def request(self, parent, cap, detail=""):
        if self.is_always(cap):
            return True
        dlg = _PermissionDialog(parent, cap, detail)
        if dlg.result == "always":
            self._data[cap] = True
            self._save()
            return True
        return dlg.result == "once"

    def revoke(self, cap=None):
        if cap is None:
            self._data.clear()
        else:
            self._data.pop(cap, None)
        self._save()

    def manage(self, parent):
        win = tk.Toplevel(parent)
        win.title("Permissions")
        win.configure(bg=XP_WINDOW_BG)
        win.resizable(False, False)
        win.transient(parent.winfo_toplevel())
        make_titlebar(win, "Saved permissions", "\U0001F512")
        body = tk.Frame(win, bg=XP_WINDOW_BG)
        body.pack(fill="both", expand=True, padx=14, pady=10)

        def render():
            for w in body.winfo_children():
                w.destroy()
            for cap, info in CAPABILITIES.items():
                row = tk.Frame(body, bg=XP_WINDOW_BG)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=info["title"], font=FONT_UI, bg=XP_WINDOW_BG, width=34,
                         anchor="w").pack(side="left")
                allowed = self.is_always(cap)
                tk.Label(row, text="Always allowed" if allowed else "Ask every time", font=FONT_UI_BOLD,
                         bg=XP_WINDOW_BG, fg=XP_OK_GREEN if allowed else "#555555", width=16,
                         anchor="w").pack(side="left")
                btn = xp_button(row, "Revoke", lambda c=cap: (self.revoke(c), render()), width=8)
                btn.pack(side="left")
                if not allowed:
                    btn.config(state="disabled")
            xp_button(body, "Close", win.destroy, width=10).pack(anchor="e", pady=(10, 0))

        render()
