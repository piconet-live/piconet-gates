"""map_lib.py: reading a measuring run of the whole-frame map (runs/map-run.sh): the sampler's records, the pacing
log, the rollback log, the link maps of the runner and of the module, the system DLLs' export tables. Used by
map-report.py and map-pace.py. It reads no setting: the programs that use it name the files."""
import bisect
import collections
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the pacing log and the rollback log)

REL = 0x801BA660                 # main.rel as pinned
TEXT = REL + 0xDC                # its text section: fn_1_XXXX = TEXT + XXXX
TASK_RETURN = TEXT + 0x4120      # where a task returns to in the task runner fn_1_407C
FIELD_MS = 1000 / 59.94


def wsl(path):
    """C:\\x\\y -> /mnt/c/x/y"""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/") if m else path


class LinkMap:
    """A Microsoft-format link map (MSVC's /MAP): the function a relative address lies in, and the object it came from.
    The one reader of a link map here (freeze-report.py and runs/map-offsets.py take it too). Addresses are relative
    to the map's "Preferred load address" (default_base when the map states none); functions[i]: the symbol is a
    function (the map's "f"); stamp: the map's "Timestamp is", the program header's when the map is that program's."""

    LINE = re.compile(r"\s*[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s+(.*)$")

    def __init__(self, path=None, text=None, default_base=0):
        if text is None:
            text = open(path, errors="replace").read() if path and os.path.exists(path) else ""
        syms = []
        self.preferred, self.stamp = default_base, None
        for line in text.splitlines():
            m = self.LINE.match(line)
            if m:
                rest = m.group(3).split()
                syms.append((int(m.group(2), 16), m.group(1), rest[-1] if rest else "", "f" in rest[:-1]))
                continue
            m = re.search(r"Preferred load address is ([0-9a-fA-F]+)", line)
            if m:
                self.preferred = int(m.group(1), 16)
            m = re.search(r"Timestamp is ([0-9a-fA-F]{8})", line)
            if m:
                self.stamp = int(m.group(1), 16)
        syms.sort()
        self.addresses = [a - self.preferred for a, _, _, _ in syms]
        self.names = [n for _, n, _, _ in syms]
        self.objects = [o for _, _, o, _ in syms]
        self.functions = [f for _, _, _, f in syms]

    def find(self, rva):
        i = bisect.bisect_right(self.addresses, rva) - 1
        return (self.names[i], self.objects[i]) if i >= 0 else ("?", "")

    def named(self, start, function=False):
        """The relative address of the first symbol whose name begins with START (a function's, with function=True),
        or None."""
        return next((a for a, n, f in zip(self.addresses, self.names, self.functions)
                     if n.startswith(start) and (f or not function)), None)


class Exports:
    """A DLL's export table: the exported function a relative address lies in (system DLLs have no map here)."""

    def __init__(self, path):
        self.addresses, self.names = [], []
        try:
            image = Image(path)
        except OSError:
            return
        d, off = image.data, image.offset
        erva = struct.unpack_from("<I", d, image.pe + 24 + 112)[0]
        if not erva or off(erva) is None:
            return
        e = off(erva)
        nfun, nname = struct.unpack_from("<II", d, e + 20)
        afun, aname, aord = struct.unpack_from("<III", d, e + 28)
        out = []
        for i in range(nname):
            n = off(struct.unpack_from("<I", d, off(aname) + 4 * i)[0])
            name = d[n:d.index(b"\0", n)].decode(errors="replace")
            ordinal = struct.unpack_from("<H", d, off(aord) + 2 * i)[0]
            out.append((struct.unpack_from("<I", d, off(afun) + 4 * ordinal)[0], name))
        out.sort()
        self.addresses = [a for a, _ in out]
        self.names = [n for _, n in out]

    def find(self, rva):
        i = bisect.bisect_right(self.addresses, rva) - 1
        return self.names[i] if i >= 0 else "?"


class Image:
    """A PE file's header and its bytes by relative address: the one PE reader here (Exports, runs/map-offsets.py).
    pe: the file offset of the PE header; stamp: its time stamp (a link map's "Timestamp is" when the map is this
    program's); secs: (virtual size, virtual address, raw size, raw offset) of each section."""

    def __init__(self, path):
        d = self.data = open(path, "rb").read()
        pe = self.pe = struct.unpack_from("<I", d, 0x3C)[0]
        self.stamp = struct.unpack_from("<I", d, pe + 8)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opt = struct.unpack_from("<H", d, pe + 20)[0]
        self.secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * i + 8) for i in range(nsec)]

    def offset(self, rva):
        """The file offset of a relative address inside a section (its virtual or its raw size), or None."""
        for vs, va, rs, ro in self.secs:
            if va <= rva < va + max(vs, rs):
                return ro + rva - va
        return None

    def at(self, rva, n):
        for vs, va, rs, ro in self.secs:
            if va <= rva < va + rs:
                return self.data[ro + rva - va: ro + rva - va + n]
        return b""

    def follows_call(self, rva):
        b = self.at(rva - 7, 7)
        if len(b) < 7:
            return False
        if b[2] == 0xE8:
            return True
        return any(b[7 - k] == 0xFF and (b[8 - k] >> 3) & 7 == 2 for k in (2, 3, 4, 6, 7) if 8 - k < 7)


class Run:
    """One run's records. Times are the performance counter in microseconds (one clock for every file)."""

    def __init__(self, folder):
        self.folder = folder
        self.modules, self.thread_names, self.cycles = [], {}, collections.defaultdict(list)
        self.cpu, self.video, self.others, self.info = [], [], collections.defaultdict(list), {}
        path = os.path.join(folder, "samples.txt")
        if os.path.exists(path):
            for line in open(path, errors="replace"):
                k = line[0]
                if k == "C":
                    head, chain, stack = line.split("|")
                    f = head.split()
                    self.cpu.append((int(f[1]), int(f[2], 16), int(f[3], 16), int(f[4], 16), int(f[5], 16), int(f[6], 16), int(f[7]),
                                     tuple(int(x) for x in f[8:14]), tuple(int(x, 16) for x in chain.split()),
                                     tuple(int(x, 16) for x in stack.split())))
                elif k == "V":
                    head, stack = line.split("|")
                    f = head.split()
                    self.video.append((int(f[1]), int(f[2], 16), tuple(int(x, 16) for x in stack.split())))
                elif k == "O":
                    head, stack = line.split("|")
                    f = head.split()
                    self.others[int(f[1])].append((int(f[2]), int(f[3], 16), tuple(int(x, 16) for x in stack.split())))
                elif k == "T":
                    f = line.split()
                    self.cycles[int(f[2])].append((int(f[1]), int(f[3])))
                elif k == "M":
                    f = line.rstrip("\n").split(" ", 3)
                    self.modules.append((int(f[1], 16), int(f[2], 16), f[3]))
                elif k == "N":
                    f = line.rstrip("\n").split(" ", 2)
                    self.thread_names[int(f[1])] = f[2]
                elif k == "G":
                    f = line.split()
                    self.info[f[1]] = line.strip()
        self.modules.sort()
        self.fields, self.presents, self.tsc, self.other_records = [], [], [], collections.defaultdict(list)
        pace = logs.pacing(os.path.join(folder, "pace.csv"))
        self.backend = next((n.strip() for n in pace.notes if n.startswith("graphics backend")), "")
        for f in pace["F"]:
            # end_us, field, cycles, mode, submode, race_frame, trips, idles, fallback steps, interpreted
            self.fields.append((int(f[1]), int(f[2]), int(f[3]), int(f[4]), int(f[5]), int(f[6]), int(f[21]), int(f[22]),
                                int(f[17]), int(f[18])))
        self.presents = [tuple(int(x) for x in f[1:13]) for f in pace["P"]]
        self.tsc = [(int(f[1]), int(f[2])) for f in pace["C"]]
        for kind in "TXNESR":
            self.other_records[kind] = [f[1:] for f in pace[kind]]
        self.tsc_per_us = pace.rate(default=0)
        self.rollback = logs.rollback_log(os.path.join(folder, "rb.csv"))

    def module_of(self, address):
        i = bisect.bisect_right(self.modules, (address, 1 << 62, "")) - 1
        if i >= 0 and address < self.modules[i][0] + self.modules[i][1]:
            return self.modules[i]
        return None

    def thread_ms(self, tid, t0, t1):
        """A thread's CPU time between two instants, from the once-a-second cycle readings around them."""
        c = self.cycles.get(tid, [])
        inside = [(t, v) for t, v in c if t0 <= t <= t1]
        if len(inside) < 2 or not self.tsc_per_us:
            return 0.0, 0.0
        return (inside[-1][1] - inside[0][1]) / self.tsc_per_us / 1000, (inside[-1][0] - inside[0][0]) / 1000


class Symbols:
    """Names for host addresses (the runner by its map, the module by its map, system DLLs by their exports) and for
    guest addresses (the function starts the module's map lists; fn_1_XXXX for main.rel, the image's own names)."""

    def __init__(self, run, exe_map, module_map, image_symbols=None, functions=None):
        """module_map may be absent (a module is linked without one): generated code is then one place, and the
        guest functions' starts come from `functions`, the module's generated.h."""
        self.run = run
        self.exe = LinkMap(exe_map)
        self.mod = LinkMap(module_map)
        self.has_module_map = bool(self.mod.names)
        self.exe_range = self.mod_range = (0, 0)
        self.exe_image = None
        for base, size, path in run.modules:
            if path.lower().endswith("moderngekko-run.exe"):
                self.exe_range = (base, base + size)
                self.exe_image = Image(wsl(path))
            elif path.lower().endswith("_recomp.dll"):
                self.mod_range = (base, base + size)
        self.exports = {}
        starts = set()
        for n in self.mod.names:
            m = re.match(r"func_([0-9A-F]{8})", n)
            if m:
                starts.add(int(m.group(1), 16))
        if not starts and functions and os.path.exists(functions):
            starts = {int(x, 16) for x in re.findall(r"\bfunc_([0-9A-F]{8})\(", open(functions, errors="replace").read())}
        self.guest_starts = sorted(starts)
        self.image_names = []
        if image_symbols and os.path.exists(image_symbols):
            for name, value in json.load(open(image_symbols)).items():
                try:
                    self.image_names.append((int(value, 16), name))
                except (TypeError, ValueError):
                    pass
            self.image_names.sort()

    def host(self, address):
        """(module, function, object) of a host address."""
        if self.exe_range[0] <= address < self.exe_range[1]:
            n, o = self.exe.find(address - self.exe_range[0])
            return "exe", n, o
        if self.mod_range[0] <= address < self.mod_range[1]:
            n, o = self.mod.find(address - self.mod_range[0])
            return "module", n, o
        m = self.run.module_of(address)
        if not m:
            return "(no module)", "", ""
        name = m[2].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name not in self.exports:
            self.exports[name] = Exports(wsl(m[2]))
        return name, self.exports[name].find(address - m[0]), ""

    def callers(self, stack):
        """The runner's functions whose return addresses lie on a sampled host stack, innermost first."""
        out = []
        for v in stack:
            if self.exe_range[0] <= v < self.exe_range[1] and self.exe_image.follows_call(v - self.exe_range[0]):
                out.append(self.exe.find(v - self.exe_range[0]))
        return out

    def guest_function(self, address):
        i = bisect.bisect_right(self.guest_starts, address) - 1
        return self.guest_starts[i] if i >= 0 else 0

    def guest_name(self, start):
        if start >= 0x81800000:
            i = bisect.bisect_right(self.image_names, (start, "~")) - 1
            return f"image:{self.image_names[i][1]}" if i >= 0 else f"image:{start:08X}"
        if start >= TEXT:
            return f"fn_1_{start - TEXT:X}"
        return f"dol_{start:08X}"
