#!/usr/bin/env python3
"""map-offsets.py RUNNER.exe RUNNER.map: the five offsets map-sample.exe needs of one runner build, read out of its
code (map-run.sh's OFFSETS; they belong to that build alone). The link map is the runner build's own
(<work>/ModernGekko/build/moderngekko-run.map; its "Timestamp is" line equals the program's header).

  system   the static Core::System instance (the map's ?instance@...GetInstance@System@Core)
  timing   Core::System::Impl -> CoreTimingManager     (System::GetCoreTiming: add rax, N)
  ppc      Core::System::Impl -> PowerPCManager        (System::GetPPCState: add rax, N)
  core     PowerPCManager -> the CPU core's pointer    (PowerPCManager::RunLoop: mov rcx, [rcx + N])
  guest    StaticRecompCore -> its CPUState            (StaticRecompCore::SyncIn: lea r14, [rbp + N])
Prints the line for OFFSETS, or says which function no longer reads as expected. Needs capstone (the checkout's
.venv has it). Reads files only."""
import os
import re
import sys

import capstone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports"))
from map_lib import Image, LinkMap  # noqa: E402  (the one reader of a link map and of a PE header)

WANT = (("timing", "?GetCoreTiming@System@Core@", r"add rax, (0x[0-9a-f]+)"),
        ("ppc", "?GetPPCState@System@Core@", r"add rax, (0x[0-9a-f]+)"),
        ("core", "?RunLoop@PowerPCManager@PowerPC@", r"mov rcx, qword ptr \[rcx \+ (0x[0-9a-f]+)\]"),
        ("guest", "?SyncIn@StaticRecompCore@", r"lea r\d+, \[r\w+ \+ (0x[0-9a-f]+)\]"))


def main(exe_path, map_path):
    exe, linked = Image(exe_path), LinkMap(map_path)
    if linked.stamp != exe.stamp:
        said = f"{linked.stamp:08x}" if linked.stamp is not None else "?"
        sys.exit(f"map-offsets: the map is not this program's (map {said}, program {exe.stamp:08x})")

    def code(rva, n):
        at = exe.offset(rva)
        return exe.data[at:at + n] if at is not None else b""

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    found = {}
    system = linked.named("?instance@?1??GetInstance@System@Core")
    if system is not None:
        found["system"] = hex(system)
    for key, name, pattern in WANT:
        rva = linked.named(name, function=True)
        if rva is None:
            continue
        listing = "\n".join(f"{i.mnemonic} {i.op_str}" for i in md.disasm(code(rva, 120), linked.preferred + rva))
        hit = re.search(pattern, listing)
        if hit:
            found[key] = hit.group(1)
    missing = [k for k in ("system", "ppc", "timing", "core", "guest") if k not in found]
    if missing:
        sys.exit(f"map-offsets: not found: {' '.join(missing)} (read the functions by hand: the head of this file)")
    print(" ".join(f"{k}={found[k]}" for k in ("system", "ppc", "timing", "core", "guest")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
