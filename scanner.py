"""
Engines
  portable : multithreaded os.scandir walk. Works on every OS, needs no permissions.
  mft      : Windows + NTFS. Reads the Master File Table straight off the volume.
             Needs administrator rights (raw volume access).
  find     : Linux + GNU find. The directory walk runs in C; Python only parses the output.
             Works without root, but root can read protected folders too.

This file doubles as the elevated helper:  python scanner.py --helper <mode> ...
Run `python scanner.py <folder>` for a quick console test.
"""

import heapq
import json
import os
import pickle
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time

import osutils

IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
SCRIPT = os.path.abspath(__file__)

class Node:
    __slots__ = ("name", "parent", "is_dir", "size", "file_count", "children")

    def __init__(self, name, parent, is_dir, size=0):
        self.name = name
        self.parent = parent
        self.is_dir = is_dir
        self.size = size
        self.file_count = 0 if is_dir else 1
        self.children = [] if is_dir else None

    def full_path(self):
        parts, n = [], self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        if not parts:
            return n.name
        parts.reverse()
        return os.path.join(n.name, *parts)


class Progress:
    def __init__(self):
        self.files = 0
        self.dirs = 0
        self.skipped = 0
        self.denied = 0
        self.current = ""
        self.phase = "Scanning"


class ScanResult:
    def __init__(self, path, root, engine, seconds, top_files, ext_stats, files, dirs,
                 skipped, denied, notes):
        self.path, self.root, self.engine, self.seconds = path, root, engine, seconds
        self.top_files, self.ext_stats = top_files, ext_stats
        self.files, self.dirs, self.skipped, self.denied = files, dirs, skipped, denied
        self.notes = notes


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _norm_root(p):
    if IS_WIN and len(p) == 2 and p[1] == ":":
        p += "\\"
    return os.path.abspath(p)


def finalize(root):
    stack = [(root, False)]
    while stack:
        n, done = stack.pop()
        if done:
            s = c = 0
            for ch in n.children:
                s += ch.size
                c += ch.file_count
            n.size, n.file_count = s, c
            n.children.sort(key=lambda x: x.size, reverse=True)
        else:
            stack.append((n, True))
            for ch in n.children:
                if ch.is_dir:
                    stack.append((ch, False))


def iter_files(node):
    stack = [node]
    while stack:
        n = stack.pop()
        if n.is_dir:
            stack.extend(n.children)
        else:
            yield n


def ext_of(name):
    return os.path.splitext(name)[1].lower() or "(none)"


def analyze(root, top_n=1000):
    heap, ext, files, dirs, ctr = [], {}, 0, 0, 0
    stack = [root]
    while stack:
        n = stack.pop()
        if n.is_dir:
            dirs += 1
            stack.extend(n.children)
            continue
        files += 1
        e = ext_of(n.name)
        ent = ext.get(e)
        if ent is None:
            ext[e] = [n.size, 1]
        else:
            ent[0] += n.size
            ent[1] += 1
        item = (n.size, ctr, n)
        ctr += 1
        if len(heap) < top_n:
            heapq.heappush(heap, item)
        elif n.size > heap[0][0]:
            heapq.heapreplace(heap, item)
    return [it[2] for it in sorted(heap, reverse=True)], ext, files, dirs


def remove_node(node):
    p, size, cnt = node.parent, node.size, node.file_count
    if p is not None:
        try:
            p.children.remove(node)
        except ValueError:
            pass
    while p is not None:
        p.size -= size
        p.file_count -= cnt
        p = p.parent


def is_within(n, ancestor):
    while n is not None:
        if n is ancestor:
            return True
        n = n.parent
    return False


def scan_portable(root_path, progress, cancel, workers=None):
    root_path = _norm_root(root_path)
    root = Node(root_path, None, True)
    try:
        root_dev = os.stat(root_path).st_dev
    except OSError:
        root_dev = None
    skip_paths = {"/proc", "/sys", "/dev"} if IS_LINUX else set()
    seen, seen_lock = set(), threading.Lock()
    q = queue.Queue()
    q.put((root, root_path))

    def scan_dir(node, path):
        if cancel.is_set():
            return
        progress.current = path
        try:
            with os.scandir(path) as it:
                for e in it:
                    if cancel.is_set():
                        return
                    try:
                        if e.is_dir(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            if IS_WIN:
                                if st.st_file_attributes & 0x400:    
                                    continue
                            elif st.st_dev != root_dev or e.path in skip_paths:
                                continue                              
                            child = Node(e.name, node, True)
                            node.children.append(child)
                            progress.dirs += 1
                            q.put((child, e.path))
                        elif e.is_symlink():
                            continue
                        else:
                            st = e.stat(follow_symlinks=False)
                            if IS_WIN:
                                size = st.st_size
                            else:
                                if st.st_nlink > 1:              
                                    key = (st.st_dev, st.st_ino)
                                    with seen_lock:
                                        if key in seen:
                                            continue
                                        seen.add(key)
                                size = st.st_blocks * 512             
                            node.children.append(Node(e.name, node, False, size))
                            progress.files += 1
                    except OSError:
                        progress.skipped += 1
        except PermissionError:
            progress.skipped += 1
            progress.denied += 1
        except OSError:
            progress.skipped += 1

    def worker():
        while True:
            item = q.get()
            if item is None:
                q.task_done()
                return
            try:
                scan_dir(*item)
            except Exception:
                progress.skipped += 1
            finally:
                q.task_done()

    n = workers or min(32, (os.cpu_count() or 4) * 4)
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(n)]
    for t in threads:
        t.start()
    q.join()
    for _ in threads:
        q.put(None)
    for t in threads:
        t.join()
    return root


def _read_status(out):
    try:
        with open(out + ".status") as fh:
            return json.load(fh)
    except Exception:
        return None


def _run_helper(mode_args, cancel, out, progress=None, label=""):
    def poll():
        if cancel.is_set():
            try:
                open(out + ".cancel", "w").close()
            except OSError:
                pass
        if progress is not None:
            try:
                with open(out + ".progress") as fh:
                    progress.phase = f"{label}... {fh.read().strip()}%"
            except OSError:
                pass

    if progress is not None:
        progress.phase = "Waiting for administrator approval..."
    osutils.run_elevated([SCRIPT, "--helper"] + mode_args, poll)
    st = _read_status(out)
    if not st or not st.get("ok"):
        raise RuntimeError((st or {}).get("error") or "the administrator helper did not finish")


def elevated_delete(path):
    tmp = tempfile.mkdtemp(prefix="diag_del_")
    try:
        _run_helper(["delete", path, os.path.join(tmp, "del")], threading.Event(), os.path.join(tmp, "del"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _FileFlag:
    def __init__(self, path):
        self.path = path

    def is_set(self):
        return os.path.exists(self.path)


def is_ntfs_volume(path):
    if not IS_WIN:
        return False
    drive = os.path.splitdrive(path)[0]
    if len(drive) != 2 or drive[1] != ":":
        return False
    try:
        import psutil
        for p in psutil.disk_partitions(all=False):
            if p.mountpoint.upper().startswith(drive.upper()):
                return p.fstype.upper() == "NTFS"
    except Exception:
        pass
    return False


def _parse_record(rec, rsize):
    unpack = struct.unpack_from
    usa_off, usa_cnt = unpack("<HH", rec, 4)
    if usa_cnt < 2 or usa_off + 2 * usa_cnt > rsize:
        return None
    for i in range(1, usa_cnt):                    
        e = i * 512
        if e > rsize:
            break
        rec[e - 2:e] = rec[usa_off + 2 * i: usa_off + 2 * i + 2]
    base = int.from_bytes(rec[0x20:0x26], "little")  
    is_dir = 1 if rec[0x16] & 2 else 0
    off = rec[0x14] | (rec[0x15] << 8)
    name, parent, best_ns, size = None, 0, 9, None
    while off + 16 <= rsize:
        atype, alen = unpack("<II", rec, off)
        if atype == 0xFFFFFFFF or alen < 16 or off + alen > rsize:
            break
        if atype == 0x30:                         
            p = off + unpack("<H", rec, off + 0x14)[0]
            nl, ns = rec[p + 0x40], rec[p + 0x41]

            if name is None or (best_ns == 2 and ns != 2):
                if p + 0x42 + nl * 2 <= rsize:
                    parent = unpack("<Q", rec, p)[0] & 0xFFFFFFFFFFFF
                    name = bytes(rec[p + 0x42:p + 0x42 + nl * 2]).decode("utf-16-le", "replace")
                    best_ns = ns
        elif atype == 0x80 and rec[off + 9] == 0:     
            if rec[off + 8]:                        
                if unpack("<Q", rec, off + 0x10)[0] == 0:
                    size = unpack("<Q", rec, off + 0x28)[0]
            elif size is None:
                size = unpack("<I", rec, off + 0x10)[0]
        off += alen
    if name is None and not base:
        return None
    return base, parent, name, size, is_dir


def _runs(buf, off, end):
    runs, lcn = [], 0
    while off < end and buf[off]:
        h = buf[off]
        ln, lo = h & 0xF, h >> 4
        off += 1
        length = int.from_bytes(buf[off:off + ln], "little")
        off += ln
        if lo:
            lcn += int.from_bytes(buf[off:off + lo], "little", signed=True)
            off += lo
            runs.append((lcn, length))
        else:
            runs.append((None, length))              
    return runs


def read_mft(drive, cancel=None, on_pct=None):
    with open(r"\\.\%s" % drive.rstrip("\\"), "rb", buffering=0) as f:
        boot = f.read(4096)
        if boot[3:11] != b"NTFS    ":
            raise RuntimeError("not an NTFS volume")
        bps, spc = struct.unpack_from("<HB", boot, 0x0B)
        csize = bps * spc
        mft_lcn = struct.unpack_from("<Q", boot, 0x30)[0]
        cpr = struct.unpack_from("<b", boot, 0x40)[0]
        rsize = cpr * csize if cpr > 0 else 1 << -cpr

        f.seek(mft_lcn * csize)
        rec0 = bytearray(f.read(max(rsize, bps)))
        if rec0[:4] != b"FILE":
            raise RuntimeError("could not read the $MFT record")
        usa_off, usa_cnt = struct.unpack_from("<HH", rec0, 4)
        for i in range(1, usa_cnt):
            e = i * 512
            if e <= rsize:
                rec0[e - 2:e] = rec0[usa_off + 2 * i: usa_off + 2 * i + 2]

        runs, real, off = None, 0, rec0[0x14] | (rec0[0x15] << 8)
        while off + 16 <= rsize:
            atype, alen = struct.unpack_from("<II", rec0, off)
            if atype == 0xFFFFFFFF or alen < 16:
                break
            if atype == 0x80 and rec0[off + 8]:
                roff = struct.unpack_from("<H", rec0, off + 0x20)[0]
                real = struct.unpack_from("<Q", rec0, off + 0x30)[0]
                runs = _runs(rec0, off + roff, off + alen)
                break
            off += alen
        if not runs:
            raise RuntimeError("could not locate the $MFT data runs")
        if sum(n for _, n in runs) * csize < real:
            raise RuntimeError("the $MFT is too fragmented for the fast reader")

        total = real // rsize
        names, parents = [None] * total, [0] * total
        isdir, sizes = bytearray(total), [0] * total
        ext_sizes = {}
        buf, idx, remaining = bytearray(), 0, real
        for lcn, nclu in runs:
            if lcn is None:
                continue
            f.seek(lcn * csize)
            left = nclu * csize
            while left > 0 and remaining > 0:
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("cancelled")
                data = f.read(min(16 * 1024 * 1024, left))
                if not data:
                    break
                left -= len(data)
                buf += data
                take = min(len(buf) // rsize * rsize, remaining)
                for pos in range(0, take, rsize):
                    rec = buf[pos:pos + rsize]
                    if rec[:4] == b"FILE" and rec[0x16] & 1:        
                        r = _parse_record(rec, rsize)
                        if r:
                            base, parent, name, size, d = r
                            if base:
                                if size is not None:
                                    ext_sizes[base] = size
                            else:
                                names[idx], parents[idx], isdir[idx], sizes[idx] = name, parent, d, size or 0
                    idx += 1
                del buf[:take]
                remaining -= take
                if on_pct:
                    on_pct(int(100 * idx / max(total, 1)))
        for b, s in ext_sizes.items():  
            if b < total and names[b] is not None and not sizes[b]:
                sizes[b] = s
        return names, parents, bytes(isdir), sizes


def build_mft_tree(names, parents, isdir, sizes, drive_root):
    n = len(names)
    nodes = [None] * n
    for i in range(n):
        if names[i] is not None:
            nodes[i] = Node(names[i], None, bool(isdir[i]), 0 if isdir[i] else sizes[i])
    if n <= 5 or nodes[5] is None:
        raise RuntimeError("root directory record missing")
    root = nodes[5]
    root.name = drive_root
    for i in range(n):
        nd = nodes[i]
        if nd is None or i == 5:
            continue
        pi = parents[i]
        p = nodes[pi] if pi < n else None
        if p is not None and p.is_dir and p is not nd:
            nd.parent = p
            p.children.append(nd)
    return root


def _crop(root, path, drive_root):
    rel = os.path.relpath(path, drive_root)
    if rel in (".", ""):
        return root
    node = root
    for part in rel.split(os.sep):
        low, nxt = part.lower(), None
        for ch in node.children:
            if ch.is_dir and ch.name.lower() == low:
                nxt = ch
                break
        if nxt is None:
            raise FileNotFoundError(path)
        node = nxt
    node.parent = None
    node.name = path
    return node


def scan_mft(path, elevated, progress, cancel):
    path = _norm_root(path)
    drive = os.path.splitdrive(path)[0]
    if len(drive) != 2:
        raise RuntimeError("the MFT scan needs a drive-letter path")

    def on_pct(p):
        progress.phase = f"Reading NTFS Master File Table... {p}%"

    if osutils.is_admin():
        progress.phase = "Reading NTFS Master File Table..."
        data = read_mft(drive, cancel, on_pct)
    elif elevated:
        tmp = tempfile.mkdtemp(prefix="diag_mft_")
        out = os.path.join(tmp, "mft.pkl")
        try:
            _run_helper(["mft", drive, out], cancel, out, progress, "Reading NTFS Master File Table (admin)")
            progress.phase = "Loading results..."
            with open(out, "rb") as fh:
                data = pickle.load(fh)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        raise PermissionError("administrator rights are required for the MFT scan")
    if cancel.is_set():
        return None
    progress.phase = "Building folder tree..."
    root = build_mft_tree(*data, drive + "\\")
    progress.files = sum(1 for i, nm in enumerate(data[0]) if nm is not None and not data[2][i])
    return _crop(root, path, drive + "\\")


_FIND_OK = None


def find_supported():
    global _FIND_OK
    if _FIND_OK is None:
        _FIND_OK = False
        if IS_LINUX and shutil.which("find"):
            try:
                r = subprocess.run(["find", "--version"], capture_output=True, text=True, timeout=5)
                _FIND_OK = r.returncode == 0 and "GNU" in r.stdout
            except (OSError, subprocess.TimeoutExpired):
                pass
    return _FIND_OK


def _find_cmd(path):
    return ["find", path, "-xdev", "-printf", r"%y\t%n\t%D:%i\t%b\t%P\0"]


def _parse_find(stream, root, progress, cancel):
    dirs, seen, buf, count = {"": root}, set(), b"", 0
    while True:
        if cancel.is_set():
            return False
        chunk = stream.read1(1 << 20)
        if not chunk:
            break
        buf += chunk
        parts = buf.split(b"\0")
        buf = parts.pop()
        for rec in parts:
            try:
                t, nlink, devino, blocks, rel = os.fsdecode(rec).split("\t", 4)
            except ValueError:
                continue
            if not rel:
                continue
            parent_rel, _, name = rel.rpartition("/")
            parent = dirs.get(parent_rel)
            if parent is None:
                continue
            if t == "d":
                node = Node(name, parent, True)
                parent.children.append(node)
                dirs[rel] = node
                progress.dirs += 1
            elif t == "f":
                if int(nlink) > 1:
                    if devino in seen:
                        continue
                    seen.add(devino)
                parent.children.append(Node(name, parent, False, int(blocks) * 512))
                progress.files += 1
            count += 1
            if count % 4000 == 0:
                progress.current = rel
    return True


def _count_find_errors(errf, progress):
    errf.seek(0)
    for line in errf:
        progress.skipped += 1
        if b"Permission denied" in line:
            progress.denied += 1


def scan_find(path, elevated, progress, cancel):
    path = _norm_root(path)
    root = Node(path, None, True)
    if osutils.is_admin() or not elevated:
        progress.phase = "Scanning (GNU find)"
        with tempfile.TemporaryFile() as errf:
            proc = subprocess.Popen(_find_cmd(path), stdout=subprocess.PIPE, stderr=errf)
            ok = _parse_find(proc.stdout, root, progress, cancel)
            if not ok:
                proc.kill()
            proc.wait()
            _count_find_errors(errf, progress)
    else:
        tmp = tempfile.mkdtemp(prefix="diag_find_")
        out = os.path.join(tmp, "find.out")
        try:
            _run_helper(["find", path, out], cancel, out, progress, "Scanning as administrator")
            progress.phase = "Reading results..."
            with open(out, "rb") as fh:
                _parse_find(fh, root, progress, cancel)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return None if cancel.is_set() else root


def run_scan(path, engine, elevated, progress, cancel):
    t0, notes, root = time.time(), [], None
    label = "Portable (multithreaded scandir)"
    path = _norm_root(path)
    try:
        if engine == "mft":
            root = scan_mft(path, elevated, progress, cancel)
            label = "NTFS Master File Table"
        elif engine == "find":
            root = scan_find(path, elevated, progress, cancel)
            label = "GNU find" + (" (admin)" if elevated or osutils.is_admin() else "")
    except Exception as exc:
        if not cancel.is_set():
            notes.append(f"Fast scan unavailable ({exc}); used the portable scanner instead.")
        root = None
    if cancel.is_set():
        return None
    if root is None:
        progress.files = progress.dirs = progress.skipped = progress.denied = 0
        progress.phase = "Scanning"
        root = scan_portable(path, progress, cancel)
        label = "Portable (multithreaded scandir)"
        if cancel.is_set():
            return None
    progress.phase = "Calculating sizes..."
    finalize(root)
    top, ext, nfiles, ndirs = analyze(root)
    return ScanResult(path, root, label, time.time() - t0, top, ext, nfiles, ndirs,
                      progress.skipped, progress.denied, notes)


def squarify(sizes, x, y, w, h):
    total = float(sum(sizes))
    if total <= 0 or w <= 0 or h <= 0:
        return []
    areas = [s * w * h / total for s in sizes]

    def worst(row, side):
        s = sum(row)
        return max(side * side * max(row) / (s * s), (s * s) / (side * side * min(row)))

    rects, i = [], 0
    while i < len(areas):
        short = min(w, h)
        row, j = [areas[i]], i + 1
        while j < len(areas) and worst(row + [areas[j]], short) <= worst(row, short):
            row.append(areas[j])
            j += 1
        rs = sum(row)
        if w >= h:                     
            cw, cy = rs / h, y
            for a in row:
                rects.append((x, cy, cw, a / cw))
                cy += a / cw
            x += cw
            w -= cw
        else:                      
            rh, cx = rs / w, x
            for a in row:
                rects.append((cx, y, a / rh, rh))
                cx += a / rh
            y += rh
            h -= rh
        i = j
    return rects


def _write_private(path, text):
    with open(path, "w") as fh:
        fh.write(text)
    _chmod_open(path)


def _chmod_open(path):
    try:
        os.chmod(path, 0o666)          
    except OSError:
        pass


def _status(out, ok, error=""):
    _write_private(out + ".status", json.dumps({"ok": ok, "error": error}))


def _helper_main(argv):
    mode, out = argv[0], argv[-1]
    flag = _FileFlag(out + ".cancel")
    try:
        if mode == "mft":
            def pct(p):
                _write_private(out + ".progress", str(p))
            data = read_mft(argv[1], flag, pct)
            with open(out, "wb") as fh:
                pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            _chmod_open(out)
        elif mode == "find":
            with open(out, "wb") as fh, open(out + ".err", "wb") as ef:
                proc = subprocess.Popen(_find_cmd(argv[1]), stdout=fh, stderr=ef)
                while proc.poll() is None:
                    if flag.is_set():
                        proc.kill()
                        raise InterruptedError("cancelled")
                    time.sleep(0.25)
            _chmod_open(out)
        elif mode == "delete":
            if osutils.is_protected(argv[1]):
                raise PermissionError("protected location")
            osutils.delete_permanently(argv[1])
        else:
            raise ValueError("unknown helper mode " + mode)
        _status(out, True)
        return 0
    except BaseException as exc:
        _status(out, False, f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--helper":
        sys.exit(_helper_main(sys.argv[2:]))
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
    prog, ev = Progress(), threading.Event()
    eng = "find" if find_supported() else "portable"
    res = run_scan(target, eng, False, prog, ev)
    print(f"{res.engine}: {res.files:,} files, {res.dirs:,} folders, "
          f"{fmt_size(res.root.size)} in {res.seconds:.1f}s (skipped {res.skipped})")
    for c in res.root.children[:20]:
        print(f"{fmt_size(c.size):>10}  {c.name}{'/' if c.is_dir else ''}")
