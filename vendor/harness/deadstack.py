"""Dead stack in a GameCube/Wii memory dump: the part of each guest thread's stack below its saved stack pointer.

Memory below a thread's stack pointer holds what earlier calls left there (frames, saved registers) and nothing the
program reads before writing it again, so two runs that compute the same may leave different words there: when an
interrupt caught the thread, or which calls a thread made before it ended. A memory gate with `dead_stacks` leaves
those words out of its count, and only those, in both dumps.

The threads are the Dolphin SDK's OSThread records (the OS of every GameCube and Wii game):
  - every thread whose stack the OS marked: OSCreateThread writes OS_THREAD_STACK_MAGIC (0xDEADBABE) at the stack's
    lowest word (stackEnd), and the record names that address at +0x308, the stack's top (stackBase) at +0x304; its
    saved context's r1 is at +0x4. So a thread that has ended and left the active queue is found too: its record
    and its stack are still in memory, and all of its stack below its last r1 is dead;
  - not the thread that runs (the OS's current thread, 0x800000E4): the dump catches it running, below the r1 its
    record saved when it last stopped, so none of its stack is left out.
A record is taken only when it is whole: stackEnd < r1 <= stackBase, a stack of 256 bytes to 1 MiB, the magic at
stackEnd and its state one of the OS's (0 to 8). The magic word itself is compared.
"""
from __future__ import annotations

import struct

MEM1 = 0x80000000
MAGIC = b"\xde\xad\xba\xbe"
CURRENT_THREAD = 0x800000E4
CONTEXT_R1 = 0x4
STATE = 0x2C8
STACK_BASE = 0x304
STACK_END = 0x308
STATES = {0, 1, 2, 4, 8}
SMALLEST, LARGEST = 0x100, 0x100000


def _word(dump: bytes, address: int) -> int | None:
    o = address - MEM1
    if o < 0 or o + 4 > len(dump):
        return None
    return struct.unpack_from(">I", dump, o)[0]


def threads(dump: bytes) -> list[dict]:
    """Every whole OSThread record whose stack is marked: {at, state, r1, base, end, current}."""
    out = []
    current = _word(dump, CURRENT_THREAD)
    at = dump.find(MAGIC)
    while at != -1:
        if at % 4 == 0:
            end = MEM1 + at
            needle = struct.pack(">I", end)
            ref = dump.find(needle)
            while ref != -1:
                record = MEM1 + ref - STACK_END
                if ref % 4 == 0 and ref >= STACK_END:
                    base, r1 = _word(dump, record + STACK_BASE), _word(dump, record + CONTEXT_R1)
                    state = struct.unpack_from(">H", dump, record - MEM1 + STATE)[0]
                    if (base is not None and r1 is not None and SMALLEST <= base - end <= LARGEST
                            and end < r1 <= base and state in STATES):
                        out.append(dict(at=record, state=state, r1=r1, base=base, end=end, current=record == current))
                ref = dump.find(needle, ref + 1)
        at = dump.find(MAGIC, at + 1)
    return out


def dead_ranges(dump: bytes) -> list[tuple[int, int]]:
    """[start, end) of each thread's stack below its saved r1, the magic word kept; none for the running thread."""
    return sorted((t["end"] + 4, t["r1"]) for t in threads(dump) if not t["current"] and t["r1"] > t["end"] + 4)


def dead_in_both(addresses: list[int], dump_a: bytes, dump_b: bytes) -> tuple[list[int], list[int]]:
    """(the words below a thread's stack pointer in both dumps, the rest), of `addresses`."""
    ra, rb = dead_ranges(dump_a), dead_ranges(dump_b)
    dead, rest = [], []
    for a in addresses:
        (dead if any(s <= a < e for s, e in ra) and any(s <= a < e for s, e in rb) else rest).append(a)
    return dead, rest
