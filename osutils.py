import importlib
import os
import shlex
import shutil
import stat
import subprocess
import sys
import urllib.parse

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

FILE_MANAGER = "File Explorer" if IS_WIN else ("Finder" if IS_MAC else "file manager")
TRASH = "Recycle Bin" if IS_WIN else "Trash"


class ElevationDenied(Exception):
    pass


class ElevationUnavailable(Exception):
    pass
def is_admin():
    try:
        if IS_WIN:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def _wait(proc, on_poll, poll):
    while True:
        try:
            return proc.wait(timeout=poll)
        except subprocess.TimeoutExpired:
            if on_poll:
                on_poll()


def run_elevated(script_args, on_poll=None, poll=0.25):
    py = sys.executable
    if IS_WIN:
        return _run_elevated_windows(py, script_args, on_poll, poll)
    if IS_LINUX:
        exe = shutil.which("pkexec")
        if not exe:
            raise ElevationUnavailable("pkexec (polkit) is not installed.")
        proc = subprocess.Popen([exe, py] + list(script_args))
        code = _wait(proc, on_poll, poll)
        if code in (126, 127):
            raise ElevationDenied("The administrator prompt was dismissed.")
        return code
    if IS_MAC:
        cmd = " ".join(shlex.quote(a) for a in [py] + list(script_args))
        cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
        proc = subprocess.Popen(
            ["osascript", "-e", 'do shell script "%s" with administrator privileges' % cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        code = _wait(proc, on_poll, poll)
        if code != 0:
            raise ElevationDenied("The administrator prompt was dismissed.")
        return code
    raise ElevationUnavailable("Elevation is not supported on this OS.")


def _run_elevated_windows(py, script_args, on_poll, poll):
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    shell32, k32 = ctypes.windll.shell32, ctypes.windll.kernel32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    sei = SHELLEXECUTEINFO()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = 0x00000040           
    sei.lpVerb = "runas"           
    sei.lpFile = py
    sei.lpParameters = subprocess.list2cmdline(list(script_args))
    sei.nShow = 0                  
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        raise ElevationDenied("The administrator prompt was declined.")
    handle = sei.hProcess
    while k32.WaitForSingleObject(handle, int(poll * 1000)) == 0x102:   
        if on_poll:
            on_poll()
    code = wintypes.DWORD(0)
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    k32.CloseHandle(handle)
    return code.value

def open_path(path):
    if IS_WIN:
        os.startfile(path)  
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def reveal_in_file_manager(path):
    path = os.path.abspath(path)
    if IS_WIN:
        subprocess.Popen('explorer /select,"%s"' % os.path.normpath(path))
    elif IS_MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        try:   
            uri = "file://" + urllib.parse.quote(path)
            r = subprocess.run(
                ["dbus-send", "--session", "--print-reply",
                 "--dest=org.freedesktop.FileManager1", "--type=method_call",
                 "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1.ShowItems",
                 "array:string:" + uri, "string:"],
                capture_output=True, timeout=5)
            if r.returncode == 0:
                return
        except (OSError, subprocess.TimeoutExpired):
            pass
        open_path(path if os.path.isdir(path) else os.path.dirname(path))


def open_full_disk_access_settings():
    if IS_MAC:
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])



def move_to_trash(path):
    try:
        send2trash = importlib.import_module("send2trash").send2trash
    except ModuleNotFoundError as exc:
        raise ImportError("Moving to the trash needs:\n\n    pip install Send2Trash") from exc
    send2trash(os.path.abspath(path))


def _rm_error(func, path, *_):
    os.chmod(path, stat.S_IWRITE)         
    func(path)


def delete_permanently(path):
    if os.path.islink(path):
        if IS_WIN and os.path.isdir(path):
            os.rmdir(path)
        else:
            os.unlink(path)
    elif os.path.isdir(path):
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_rm_error)
        else:
            shutil.rmtree(path, onerror=_rm_error)
    else:
        try:
            os.remove(path)
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)


_PROTECTED_EXACT_WIN = ["SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                        "USERPROFILE", "PUBLIC", "SystemDrive"]
_PROTECTED_TREES_UNIX = ["/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc",
                         "/sbin", "/sys", "/usr", "/System", "/private/etc", "/private/var/db"]
_PROTECTED_EXACT_UNIX = ["/", "/home", "/root", "/opt", "/var", "/run", "/srv", "/mnt", "/media",
                         "/Library", "/Applications", "/Users", "/Volumes", "/private",
                         os.path.expanduser("~")]


def _n(p):
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/") or os.sep


def is_protected(path):
    try:
        p = _n(os.path.realpath(path))
    except OSError:
        p = _n(path)
    if os.path.dirname(p) == p or p.endswith(":"):
        return True
    if IS_WIN:
        exact = {_n(os.environ[k]) for k in _PROTECTED_EXACT_WIN if os.environ.get(k)}
        exact.add(_n(os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "Users")))
        if p in exact:
            return True
        root = os.environ.get("SystemRoot")
        if root:
            for sub in ("System32", "WinSxS", "SysWOW64"):
                t = _n(os.path.join(root, sub))
                if p == t or p.startswith(t + os.sep):
                    return True
        return False
    if p in {_n(x) for x in _PROTECTED_EXACT_UNIX}:
        return True
    for t in _PROTECTED_TREES_UNIX:
        t = _n(t)
        if p == t or p.startswith(t + os.sep):
            return True
    return False
