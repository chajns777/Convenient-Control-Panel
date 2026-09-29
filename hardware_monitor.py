"""
hardware_monitor.py - Collects live hardware, firmware and maintenance data.

Honesty note about scope (read this before extending the app):
  * CPU, RAM, disk, network, battery and (where the OS exposes it)
    temperature figures are REAL, live readings taken via `psutil`.
  * BIOS/firmware version reporting is REAL where the OS exposes it
    (Windows via WMI, Linux via /sys/class/dmi). There is no universal,
    vendor-neutral way to ask "is there a newer BIOS available" without
    talking to each manufacturer's own update service, so that specific
    check is intentionally NOT faked here.
  * "Windows Update available" IS a real, live check on Windows machines
    that have `pywin32` installed (it talks to the real Windows Update
    Agent via COM). On other platforms, or without pywin32, it is
    reported as unavailable rather than faked.
  * "Maintenance recommended" flags are rule-of-thumb heuristics
    (e.g. disk > 85% full, RAM > 90% used, temp > 80C) clearly labelled
    as such in the UI - not a vendor diagnostic tool.
"""

import platform
import socket
import time
import psutil

try:
    import wmi  # Windows only, optional
    _HAS_WMI = True
except ImportError:
    _HAS_WMI = False

try:
    import win32com.client  # pywin32, Windows only, optional
    _HAS_WIN32COM = True
except ImportError:
    _HAS_WIN32COM = False

IS_WINDOWS = platform.system() == "Windows"

DISK_WARN_PCT = 85
RAM_WARN_PCT = 90
CPU_SUSTAINED_WARN_PCT = 90
TEMP_WARN_C = 80
BATTERY_WARN_PCT = 15


def _format_duration(seconds):
    d, rem = divmod(int(seconds), 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def get_system_summary():
    uname = platform.uname()
    boot_ts = psutil.boot_time()
    uptime_s = time.time() - boot_ts
    return {
        "hostname": socket.gethostname(),
        "os": f"{uname.system} {uname.release}",
        "os_version": uname.version,
        "architecture": uname.machine,
        "processor": uname.processor or platform.processor() or "Unknown",
        "python_version": platform.python_version(),
        "boot_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_ts)),
        "uptime": _format_duration(uptime_s),
    }


def get_cpu_info():
    freq = None
    try:
        freq = psutil.cpu_freq()
    except Exception:
        pass
    return {
        "physical_cores": psutil.cpu_count(logical=False) or "Unknown",
        "logical_cores": psutil.cpu_count(logical=True) or "Unknown",
        "current_freq_mhz": round(freq.current, 1) if freq and freq.current else None,
        "max_freq_mhz": round(freq.max, 1) if freq and freq.max else None,
        "usage_percent": psutil.cpu_percent(interval=0.3),
        "per_core_percent": psutil.cpu_percent(interval=0.1, percpu=True),
    }


def get_memory_info():
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "total_gb": round(vm.total / (1024 ** 3), 2),
        "used_gb": round(vm.used / (1024 ** 3), 2),
        "available_gb": round(vm.available / (1024 ** 3), 2),
        "percent": vm.percent,
        "swap_total_gb": round(sw.total / (1024 ** 3), 2),
        "swap_used_gb": round(sw.used / (1024 ** 3), 2),
        "swap_percent": sw.percent,
    }


def get_disk_info():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append({
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent": usage.percent,
        })
    return disks


def get_network_info():
    nets = []
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    for name, snic in addrs.items():
        st = stats.get(name)
        ip = next((a.address for a in snic if a.family == socket.AF_INET), "-")
        nets.append({
            "name": name,
            "ip": ip,
            "is_up": st.isup if st else False,
            "speed_mbps": st.speed if st else 0,
        })
    return nets


def get_temperatures():

    temps = {}
    try:
        raw = psutil.sensors_temperatures()
        for name, entries in raw.items():
            for e in entries:
                label = e.label or name
                if e.current is not None:
                    temps[label] = e.current
    except (AttributeError, NotImplementedError):
        pass
    return temps


def get_battery_info():
    try:
        batt = psutil.sensors_battery()
    except (AttributeError, NotImplementedError):
        batt = None
    if not batt:
        return None
    secs_left = batt.secsleft
    if secs_left in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        secs_left = None
    return {
        "percent": batt.percent,
        "plugged_in": batt.power_plugged,
        "secs_left": secs_left,
    }


def get_firmware_info():

    info = {
        "bios_vendor": "Unknown", "bios_version": "Unknown",
        "bios_date": "Unknown", "source": "Not available on this OS",
    }
    if IS_WINDOWS and _HAS_WMI:
        try:
            c = wmi.WMI()
            bios = c.Win32_BIOS()[0]
            info.update({
                "bios_vendor": bios.Manufacturer or "Unknown",
                "bios_version": bios.SMBIOSBIOSVersion or bios.Version or "Unknown",
                "bios_date": (bios.ReleaseDate or "Unknown")[:8],
                "source": "WMI (live)",
            })
        except Exception:
            pass
    elif platform.system() == "Linux":
        import os as _os
        dmi = "/sys/class/dmi/id"

        def _read(fname):
            p = _os.path.join(dmi, fname)
            try:
                if _os.path.exists(p):
                    return open(p).read().strip()
            except PermissionError:
                return "Permission denied (try running as root)"
            return "Unknown"

        try:
            info.update({
                "bios_vendor": _read("bios_vendor"),
                "bios_version": _read("bios_version"),
                "bios_date": _read("bios_date"),
                "source": "/sys/class/dmi (live)",
            })
        except Exception:
            pass
    return info


def check_os_updates():

    if not IS_WINDOWS:
        return {"available": None, "count": 0,
                "message": "OS update checking is implemented for Windows only in this build."}
    if not _HAS_WIN32COM:
        return {"available": None, "count": 0,
                "message": "Install 'pywin32' to enable live Windows Update checks."}
    try:
        session = win32com.client.Dispatch("Microsoft.Update.Session")
        searcher = session.CreateUpdateSearcher()
        result = searcher.Search("IsInstalled=0 and IsHidden=0")
        count = result.Updates.Count
        titles = [result.Updates.Item(i).Title for i in range(count)]
        msg = f"{count} update(s) pending." if count else "System is up to date."
        return {"available": count > 0, "count": count, "titles": titles, "message": msg}
    except Exception as exc:
        return {"available": None, "count": 0, "message": f"Update check failed: {exc}"}


def evaluate_maintenance(cpu, mem, disks, temps, battery):

    flags = []
    if cpu["usage_percent"] >= CPU_SUSTAINED_WARN_PCT:
        flags.append(("warn", f"CPU load is high ({cpu['usage_percent']}%). Check for runaway processes."))
    if mem["percent"] >= RAM_WARN_PCT:
        flags.append(("warn", f"Memory usage is high ({mem['percent']}%). Consider closing applications or adding RAM."))
    for d in disks:
        if d["percent"] >= DISK_WARN_PCT:
            sev = "alert" if d["percent"] >= 95 else "warn"
            flags.append((sev, f"Disk {d['device']} is {d['percent']}% full ({d['free_gb']} GB free). Free up space soon."))
    for label, c in temps.items():
        if c >= TEMP_WARN_C:
            flags.append(("alert", f"{label} temperature is {c:.0f}\u00b0C - check cooling / airflow."))
    if battery and not battery["plugged_in"] and battery["percent"] <= BATTERY_WARN_PCT:
        flags.append(("warn", f"Battery is low ({battery['percent']}%) and not charging."))
    if not flags:
        flags.append(("ok", "No maintenance issues detected."))
    return flags


def full_snapshot():

    cpu = get_cpu_info()
    mem = get_memory_info()
    disks = get_disk_info()
    temps = get_temperatures()
    battery = get_battery_info()
    return {
        "system": get_system_summary(),
        "cpu": cpu,
        "memory": mem,
        "disks": disks,
        "network": get_network_info(),
        "temperatures": temps,
        "battery": battery,
        "firmware": get_firmware_info(),
        "maintenance": evaluate_maintenance(cpu, mem, disks, temps, battery),
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
