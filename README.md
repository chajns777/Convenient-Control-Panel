# System Diagnostics Console

## Functions

**1. Hardware & Firmware Check**
- Live system, CPU, RAM, disk, network, temperature, and battery readings
  (via `psutil`), refreshed live and split across three tabs.
- BIOS/firmware version info where the OS exposes it (WMI on
  Windows, `/sys/class/dmi` on Linux).
- A **Refresh Now** button that re-collects everything in place — no need
  to restart the app or leave the page — plus an optional auto-refresh
  every 5 seconds.
- Rolling performance graphs (CPU %, RAM %, temperature) built with
  `matplotlib`, embedded directly in the window.
- A **maintenance recommendations** panel (e.g. "disk 90%
  full", "high memory usage", "high temperature").
- A live **Windows Update** check button (Windows-only, needs `pywin32`).
- A **Save Report** button that snapshots everything currently on screen
  into the database, for the Report Archive page.

**2. Report Archive**
- A list of every report saved from the Hardware Check page.
- Selecting one shows a formatted read-only summary of that snapshot.
- Each report has its own editable **Notes** panel, saved back to the
  database on demand.
- Reports can be deleted.

**3. Command Console**
- A built-in command runner: type any shell command, press **Enter** (or
  **Run**), and watch its output stream live into the terminal-style pane.
  Output is colour-coded (stdout, stderr, exit status).
- **Stop** ends the running command *and* anything it launched (e.g. a long
  `ping`), and closing the app window does the same.
- **Up / Down** arrows step through your command history.
- A searchable, filterable **Command Library** of diagnostic commands
  (system info, CPU/RAM, disks, network, processes, firmware/BIOS, battery,
  updates, event logs, security), filtered to your OS by default. Select one
  for a description; double-click or press Enter to load it into the command
  box (it is *not* run automatically, so you can review it first).
- Commands run with **your account's permissions**. Anything needing admin
  (`sfc /scannow`, `chkdsk /f`, `dmidecode`...) needs the app started from an
  elevated terminal / with sudo; the console prints a hint when it sees that.
- Windows hardware queries use PowerShell `Get-CimInstance` rather than the
  old `wmic`, which is disabled or removed on recent Windows 11 builds.

## DATA

- CPU / RAM / disk / network / battery / temperature figures are **real
  live readings** from your machine via `psutil`.
- BIOS vendor/version/date is **real**, read from Windows WMI or Linux
  DMI tables, where your OS exposes it.
- The **Windows Update check** is a real, live call to the Windows
  Update Agent (via `pywin32`) — Windows only. On other platforms (or if
  `pywin32` isn't installed) it's reported as unavailable
  rather than faked.
- There is **no universal way** to ask "is there a newer BIOS/driver
  available" without querying each hardware vendor's own update service
  (Dell, HP, Lenovo, etc. all have separate, closed systems for this) —
  so that specific check isn't attempted. The BIOS panel shows your
  *current* firmware info only.
- The **"maintenance recommended"** flags (low disk space, high RAM/CPU
  load, high temperature, low battery) are simple, clearly-labeled
  threshold heuristics you can tune in `hardware_monitor.py` — not a
  vendor diagnostic tool.

## Project structure

```
system_diagnostics/
├── main.py                
├── theme.py                 
├── database.py              
├── hardware_monitor.py       
├── requirements.txt
├── pages/
│   ├── home.py              
│   ├── hardware_check.py     
│   ├── command_console.py    
│   └── reports.py             
└── diagnostics_reports.db   
```

## Setup & running

```bash
pip install -r requirements.txt
python main.py
```

Tkinter ships with most Python installers, but if you're on Linux and get
`ModuleNotFoundError: No module named 'tkinter'`, install it via your
package manager first, e.g.:

```bash
sudo apt-get install python3-tk
```

On Windows, install the optional extras to unlock the live BIOS/Windows
Update checks:

```bash
pip install pywin32 wmi
```

## Extending it

- **Tune maintenance thresholds:** edit the constants near the top of
  `hardware_monitor.py` (`DISK_WARN_PCT`, `RAM_WARN_PCT`, etc.).
- **Add your own commands** to the Command Library: append an entry to
  `COMMAND_LIBRARY` in `pages/command_console.py` (`name`, `command`,
  `category`, `os` = `windows` / `unix` / `all`, `description`).
- **Change how much output is kept:** `MAX_OUTPUT_LINES` in
  `pages/command_console.py` (older lines are trimmed beyond it).
- **Change the auto-refresh interval:** it's the `5000` (ms) value in
  `HardwareCheckPage._auto_refresh_loop`.
