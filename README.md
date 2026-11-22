# Convenient Control Panel

A local-first system diagnostics desktop app written in Python and Tkinter. It brings the checks you normally scatter across Task Manager, a terminal, the Sound settings and a disk-usage tool into one Windows XP-styled window: live hardware readings, a built-in command console, a saved report archive, a per-app audio mixer and a WizTree-style disk space analyzer. No cloud account, no telemetry, no data leaving your computer.

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [The interface](#the-interface)
  - [Hardware Check](#hardware-check)
  - [Report Archive](#report-archive)
  - [Command Console](#command-console)
  - [Sound Control](#sound-control)
  - [Disk Space Analyzer](#disk-space-analyzer)
  - [Configuration](#configuration)
  - [Examples](#examples)
  - [Status and error messages](#status-and-error-messages)
- [Data and accuracy](#data-and-accuracy)
- [Security model](#security-model)
- [Architecture](#architecture)
  - [Project structure](#project-structure)
  - [Execution pipeline](#execution-pipeline)
- [Development and testing](#development-and-testing)
- [Licence](#licence)

---

## Features

- **Fully local:** Every reading comes from your own machine. Reports are stored in a local SQLite file and audio profiles in plain JSON next to the app.
- **Live hardware check:** CPU, RAM, disk, network, temperature and battery readings via `psutil`, split across Overview, Performance Graphs and Details tabs, with an optional 5-second auto-refresh and a **Refresh Now** button that updates everything in place.
- **Firmware and update info:** BIOS vendor, version and date where the OS exposes it (WMI on Windows, `/sys/class/dmi` on Linux), plus a real Windows Update check on Windows.
- **Maintenance recommendations:** Clearly labelled threshold heuristics (disk nearly full, high memory, high temperature, low battery) that you can tune in one file.
- **Report archive:** Snapshot everything on screen into a database, add your own notes to each report, and delete reports you no longer need.
- **Command console:** Run any shell command and watch its output stream live, colour-coded by stdout, stderr and exit status. **Stop** kills the command and everything it launched.
- **Command library:** 60 ready-made diagnostic commands (system info, CPU and RAM, disks, network, processes, firmware, battery, updates, event logs, security), searchable and filtered to your OS. Selecting one loads it into the command box without running it.
- **Per-app audio control:** A volume mixer for every app on your desktop, input and output device controls, and switchable audio profiles (Focus Mode, Gaming / Stream, or your own) that can activate automatically when a chosen app starts.
- **Disk space analyzer:** A fast scan of any drive or folder, shown as a folder tree, a largest-files list, a treemap and a file-type breakdown. Deleting is permission-gated and goes to the Recycle Bin or Trash by default.
- **Cross-platform:** Windows, Linux and macOS, with each page adapting to what the OS can actually do. Unsupported features are disabled or labelled rather than faked.
- **App-style window:** A single Tkinter window with a desktop-style home screen and taskbar. Closing it also stops any running command or scan.

---

## Installation

### Prerequisites

- [Python](https://www.python.org/downloads/) 3.9 or newer
- Tkinter (ships with most Python installers; see the Linux note below)
- Windows 10/11, Linux or macOS

### Run from source

```bash
git clone <your-repo-url>
cd Convenient-Control-Panel
python -m pip install -r requirements.txt
python main.py
```

The core dependencies are `psutil` (live readings), `matplotlib` (performance graphs) and `Send2Trash` (safe deletion in the Disk Space Analyzer).

If you are on Linux and see `ModuleNotFoundError: No module named 'tkinter'`, install it with your package manager first:

```bash
sudo apt-get install python3-tk
```

### Optional extras

| Package or tool | Platform | Unlocks |
| --- | --- | --- |
| `pywin32` | Windows | The live **Windows Update** check on the Hardware Check page. Installed automatically by `requirements.txt` on Windows. |
| `wmi` | Windows | Live BIOS and firmware details. Installed automatically by `requirements.txt` on Windows. |
| `pycaw` + `comtypes` | Windows | The Sound Control page (per-app volume and mute, device volume, mute and gain). Install with `pip install pycaw comtypes`. |
| `pulseaudio-utils` or `pipewire-pulse` | Linux | The `pactl` command that Sound Control uses. No Python packages needed. |
| `switchaudio-osx` | macOS | Changing the default audio device from the Sound Control page (`brew install switchaudio-osx`). |
| `pkexec` (polkit) | Linux | The administrator helper for faster, deeper disk scans. |

### Running with administrator rights

Most of the app works as a normal user. Commands you run in the console use **your account's permissions**, so anything that needs admin (`sfc /scannow`, `chkdsk /f`, `dmidecode`) needs the app started from an elevated terminal or with `sudo`. The console prints a hint when it sees a permission error. The Disk Space Analyzer is different: it asks for elevation only for its own small helper process and never needs the whole app to run as admin.

---

## Usage

```bash
python main.py
```

The app creates `diagnostics_reports.db` on first run, opens a 1060 x 740 window (minimum 920 x 640) and shows the home screen. Closing the window stops any running command or disk scan first.

### The interface

The home screen is a desktop with five icons and a taskbar. Click an icon to open its page; every page has a **Home** button to return.

| Page | Purpose |
| --- | --- |
| **Hardware Check** | Live system readings, firmware info, graphs, maintenance recommendations and the Windows Update check. |
| **Command Console** | Run shell commands with live output and browse the Command Library. |
| **Report Archive** | Browse, annotate and delete saved hardware reports. |
| **Sound Control** | Per-app volume mixer, device controls and audio profiles. |
| **Disk Space Analyzer** | Scan a drive or folder and clean up what is taking the space. |

The **start** button on the taskbar jumps straight to Hardware Check.

### Hardware Check

Readings are split across three tabs:

| Tab | Shows |
| --- | --- |
| **Overview** | System summary, firmware/BIOS panel, Windows Update panel and the maintenance recommendations. |
| **Performance Graphs** | Rolling CPU %, RAM % and temperature graphs built with `matplotlib` and embedded in the window. |
| **Details** | A full metric and value table for CPU, memory, disks, network, temperature and battery. |

- **Refresh Now** re-collects everything in place. Tick **Auto-refresh every 5s** for continuous updates.
- **Check for Updates** queries the Windows Update Agent (Windows only, needs `pywin32`).
- **Save Report** snapshots everything currently on screen into the database for the Report Archive.

### Report Archive

- Lists every report saved from the Hardware Check page, newest first.
- Selecting one shows a formatted, read-only summary of that snapshot.
- Each report has its own editable **Notes** panel, saved back to the database on demand.
- Reports can be deleted.

### Command Console

Type any shell command, press **Enter** (or **Run**), and the output streams into the terminal-style pane. Output is colour-coded for stdout, stderr and exit status.

| Control | What it does |
| --- | --- |
| **Enter** / **Run** | Runs the command in the box. |
| **Stop** | Ends the running command *and* anything it launched (for example a long `ping`). |
| **Up / Down** | Steps through your command history. |
| **Command Library** | Search and filter diagnostic commands. Select one for a description; double-click or press Enter to load it into the command box. It is **not** run automatically, so you can review it first. |

Library categories: Battery & Power, CPU & Memory, Disk, Event Logs, Firmware / BIOS, Misc, Network, Processes, Security and Updates & Patches. The list is filtered to your OS by default.

Windows hardware queries use PowerShell `Get-CimInstance` rather than the old `wmic`, which is disabled or removed on recent Windows 11 builds.

### Sound Control

Two tabs: **App Volume Mixer** and **Input / Output Devices**.

- **Mixer:** Every app on your desktop gets its own volume slider and mute box. A filter switches between **All Audio Apps** and **Currently Playing Only**, and a note marks apps that are outputting sound right now.
- **Devices:** Volume, mute and gain for each input and output device, plus default-device switching where the OS allows it.
- **Profiles:** A profile is a saved set of output volume, input volume and per-app levels. Three ship by default and you can add, edit or delete your own.

| Default profile | Behaviour |
| --- | --- |
| **Default** | Balanced levels for everyday use. |
| **Focus Mode** | Lowers output, mutes Discord and the browser, keeps music quiet. Triggers when `code.exe` runs. |
| **Gaming / Stream** | Full volume for chat, browser turned down. Triggers when `obs64.exe` runs. |

Tick **Auto-switch by trigger app** and each profile activates when its trigger app starts, then returns to your previous profile when it closes. Profiles are stored in `sound_profiles.json`.

Backends are chosen automatically:

| OS | Backend | What works |
| --- | --- | --- |
| Windows | `pycaw` + `comtypes` | Per-app volume and mute, device volume, mute and gain. Windows keeps an entry for every app that has opened audio. |
| Linux | `pactl` (PulseAudio / PipeWire) | Per-app volume and mute, device volume, mute and gain, default device. Only apps that currently own an audio stream appear. |
| macOS | `osascript` + `system_profiler` | Default-device volume and mic gain only. Per-app volume is not possible without a virtual audio driver, so the mixer is read-only. |

Limits: Windows cannot change the default device through public APIs, so that button is disabled there (use Windows Sound settings).

### Disk Space Analyzer

Heavily inspired by [WizTree](https://diskanalyzer.com/); go support their team. Choose a folder or drive (or press **Browse...**), then press **Scan**. **Cancel** stops a scan in progress.

| Tab | Shows |
| --- | --- |
| **Folder Tree** | Expandable folders with size, share of the parent folder and file count. |
| **Largest Files** | The biggest files found, with their folder. |
| **Treemap** | A block map sized by disk usage. Double-click a folder to zoom in, **Up** to zoom out. |
| **File Types** | Space used per file extension. |

Right-click any item for **Open**, **Show in File Explorer / Finder**, **Copy path**, **Show in treemap**, **Move to Recycle Bin / Trash** and **Delete permanently...**

The scan engine is picked from a drop-down:

| Engine | How it works |
| --- | --- |
| **Auto (fastest available)** | Uses the NTFS Master File Table on Windows or GNU `find` on Linux when available, optionally elevated for speed and full coverage, and falls back to the portable engine if that fails. |
| **Portable (Python only)** | A multithreaded `scandir` scan that works everywhere with no elevation. |

**Actions are genuine.** Deleting changes real files on your device, so every risky action asks for your permission first (see [Security model](#security-model)). Your decisions are saved and can be changed under **Permissions...**

### Configuration

There is no settings file to edit for normal use. The tunable values live as constants in the code:

| Setting | Location | Default | Description |
| --- | --- | --- | --- |
| `DISK_WARN_PCT` | `hardware_monitor.py` | `85` | Disk usage % that triggers a maintenance recommendation. |
| `RAM_WARN_PCT` | `hardware_monitor.py` | `90` | RAM usage % that triggers a recommendation. |
| `CPU_SUSTAINED_WARN_PCT` | `hardware_monitor.py` | `90` | Sustained CPU % that triggers a recommendation. |
| `TEMP_WARN_C` | `hardware_monitor.py` | `80` | Temperature in °C that triggers a recommendation. |
| `BATTERY_WARN_PCT` | `hardware_monitor.py` | `15` | Battery % below which a recommendation is shown. |
| `MAX_OUTPUT_LINES` | `pages/command_console.py` | `5000` | Console lines kept; older lines are trimmed. |
| Auto-refresh interval | `pages/hardware_check.py` | `5000` ms | The value in `HardwareCheckPage._auto_refresh_loop`. |
| `COMMAND_LIBRARY` | `pages/command_console.py` | 60 entries | Add your own with `name`, `command`, `category`, `os` (`windows` / `unix` / `all`) and `description`. |
| `DEFAULT_PROFILES` | `pages/sound_control.py` | 3 profiles | Starting audio profiles, used until `sound_profiles.json` exists. |

### Examples

```text
# Hardware Check
Open Hardware Check ▶ tick "Auto-refresh every 5s"     # watch CPU, RAM and temperature live
Press "Save Report"                                    # snapshot it for the archive

# Report Archive
Select a report ▶ write "Fan was loud after update" ▶ save notes

# Command Console
ping 8.8.8.8                                           # streams live; press Stop to end it
Search the library for "disk" ▶ double-click an entry  # loads it into the box; press Enter to run

# Sound Control
Pick "Gaming / Stream"                                 # game and chat loud, everything else low
Tick "Auto-switch by trigger app"                      # profile follows the app you launch

# Disk Space Analyzer
Scan your home folder ▶ Largest Files ▶ right-click ▶ Move to Recycle Bin
```

### Status and error messages

| Message | Meaning |
| --- | --- |
| *Windows Update check unavailable* | You are not on Windows, or `pywin32` is not installed. It is reported rather than faked. |
| *Fast scan unavailable (…); used the portable scanner instead.* | The MFT or `find` engine could not run, so the Disk Space Analyzer fell back to the Python scanner. Results are still correct, just slower. |
| *Permission required* | An action will change your files or needs elevation. Choose **Allow once**, **Always allow** or **Don't allow**. |
| *Delete cancelled / failed.* | The OS refused the delete or you declined the elevation prompt. Nothing was removed. |
| *Mixer shown read-only* | You are on macOS, where per-app volume is not possible without a virtual audio driver. |
| *Console permission hint* | A command needed administrator rights. Restart the app from an elevated terminal or with `sudo`. |

---

## Data and accuracy

- CPU, RAM, disk, network, battery and temperature figures are **real live readings** from your machine via `psutil`.
- BIOS vendor, version and date are **real**, read from Windows WMI or Linux DMI tables where your OS exposes them.
- The **Windows Update check** is a real, live call to the Windows Update Agent (via `pywin32`). On other platforms, or without `pywin32`, it is reported as unavailable rather than faked.
- There is **no universal way** to ask "is there a newer BIOS or driver available" without querying each vendor's own closed update service (Dell, HP, Lenovo and others), so that check is not attempted. The firmware panel shows your *current* firmware only.
- The **maintenance recommended** flags are simple, clearly labelled threshold heuristics you can tune in `hardware_monitor.py`. They are not a vendor diagnostic tool.

---

## Security model

- **Local only:** The app has no server, no network calls of its own and no accounts. Reports, notes and audio profiles never leave your machine.
- **Permission-gated changes:** Any action that alters your files or needs elevation opens a permission dialog first. Four capabilities are managed: administrator disk scan, move to Recycle Bin / Trash, delete permanently, and delete with administrator rights.
- **Remembered, revocable choices:** **Always allow** is saved to `permissions.json`. Open **Permissions...** on the Disk Space Analyzer to see each capability and **Revoke** any of them.
- **Reversible by default:** Delete goes to the Recycle Bin or Trash. Permanent deletion and the admin retry are marked dangerous and warn that they cannot be undone.
- **Protected locations:** System paths and drive roots (for example `C:\Windows`, `Program Files`, `/etc`, `/usr`, `/System`, your home folder itself) cannot be deleted from the analyzer.
- **Small elevation footprint:** Only a short-lived helper process is elevated (UAC, polkit or the macOS password prompt). The app itself keeps running with your normal rights.
- **Console runs as you:** Commands use your account's permissions and nothing more. Review library commands before running them, since loading one never runs it for you.
- **Guardrail, not a sandbox:** The console executes whatever you type. Treat it as you would any terminal.

---

## Architecture

The codebase separates the window shell, one module per page, the data collectors and the storage layer, so each can be reasoned about on its own.

### Project structure

```text
Convenient-Control-Panel/
├── main.py                      # Launcher: builds the window, registers pages, handles shutdown
├── theme.py                     # Windows XP colours, fonts, ttk theme and shared widgets
├── database.py                  # SQLite storage for saved reports and notes
├── hardware_monitor.py          # Live readings, firmware info, update check, maintenance rules
├── scanner.py                   # Disk scan engines (MFT, find, portable) and treemap layout
├── osutils.py                   # Elevation, open/reveal, trash, delete and protected-path checks
├── permissions.py               # Permission dialogs and the saved allow/deny choices
├── requirements.txt             # Dependencies
├── pages/
│   ├── home.py                  # Desktop-style home screen with icons and taskbar clock
│   ├── hardware_check.py        # Overview, graphs and details tabs
│   ├── reports.py               # Report Archive page
│   ├── command_console.py       # Console, history and the Command Library
│   ├── sound_control.py         # Audio backends, mixer, devices and profiles
│   └── disk_analyzer.py         # Folder tree, largest files, treemap and file types
└── diagnostics_reports.db       # Created on first run
```

Created at runtime: `diagnostics_reports.db`, `permissions.json` (once you choose **Always allow**) and `sound_profiles.json` (once you save a profile).

### Execution pipeline

```text
  main.py
     │
     ├──▶ db.init_db()              Create the reports table if it does not exist
     ├──▶ DiagnosticsApp()          Apply the XP theme, build every page into one stacked container
     └──▶ show_frame("HomePage")    Desktop home screen
                │
                ▼
  Click an icon ▶ show_frame(page)
    ├──▶ Hardware Check
    │      ├── hardware_monitor.full_snapshot()    psutil + WMI / DMI, evaluate_maintenance()
    │      ├── Auto-refresh loop (5 s)             Redraw tabs and rolling graphs
    │      └── Save Report ──▶ database.save_report() ──▶ Report Archive reloads
    ├──▶ Command Console
    │      └── Run ──▶ background process ──▶ live stdout / stderr / exit status in the pane
    ├──▶ Sound Control
    │      ├── create_backend()                    pycaw ▶ pactl ▶ osascript, chosen by OS
    │      └── Profile apply / auto-switch         Poll for the trigger app and apply its levels
    └──▶ Disk Space Analyzer
           ├── scanner.run_scan()                  MFT ▶ find ▶ portable, with automatic fallback
           ├── finalize() / analyze()              Sizes, largest files, file-type totals
           └── Delete ──▶ permissions.request() ──▶ Trash, permanent, or elevated delete

  Window close ▶ _on_close() ▶ stop the console and cancel any scan ▶ destroy
```

---

## Development and testing

```bash
# Run from a terminal to see any errors
python main.py

# Syntax check every module
python -m compileall main.py theme.py database.py hardware_monitor.py scanner.py osutils.py permissions.py pages
```

The project has no automated test suite yet. A quick manual smoke test:

1. Launch the app and confirm the home screen shows five icons and a ticking clock.
2. Open **Hardware Check**, press **Refresh Now**, then **Save Report**.
3. Open **Report Archive**, select the new report, add a note and save it.
4. In **Command Console**, run `ping` from the library, then press **Stop**.
5. In **Sound Control**, confirm your apps appear (on Windows this needs `pycaw` and `comtypes`).
6. In **Disk Space Analyzer**, scan a small folder and check all four tabs fill in. Do not delete anything you cannot restore.

---

## Licence

This project is licensed under the MIT Licence. See the [LICENSE](LICENSE) file for details.
