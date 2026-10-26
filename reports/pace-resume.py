#!/usr/bin/env python3
"""pace-resume.py PACE.csv [COUNTDOWN]: a practice's pacing around each pause and resume (practice-run.sh PACE=1;
the runner's pacing log, as pace-report.py reads it).

A press of Start or D-pad left on port 1 (F records' pad1_buttons, 1000 and 0001) is a pause, a resume or a load;
a resume or a load runs the race on COUNTDOWN fields later (default 60, practice.h COUNTDOWN). For each press: the
presented pictures from 30 fields before the race runs on (or the press) to 90 after, as gaps between pictures:
how many were long (over 25 ms: a picture shown for two fields or more, a skip), how many short (under 8 ms: two
pictures in one field's time, a doubled one), the longest and the shortest, and the fields of the same span as the
CPU thread ended them (the same measures). A seamless resume: no long and no short gap.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the pacing log)

path = sys.argv[1]
COUNTDOWN = int(sys.argv[2]) if len(sys.argv) > 2 else 60
LONG, SHORT = 25.0, 8.0   # ms
BEFORE, AFTER = 30, 90    # fields

log = logs.pacing(path)
end, field, pad = (logs.column("F", c) for c in ("end_us", "field", "pad1_buttons"))
F = [(int(r[end]), int(r[field]), int(r[pad], 16)) for r in log["F"]]
P = [int(r[logs.column("P", "after_present_us")]) for r in log["P"]]
if not F or not P:
    sys.exit("no fields or no pictures in the log")
F.sort(key=lambda f: f[1])
P.sort()
period = 1e6 / 60
at = {field: end for end, field, _ in F}


def gaps(times):
    return [(b - a) / 1000 for a, b in zip(times, times[1:])]


def judge(name, times):
    g = gaps(times)
    if not g:
        return f"{name}: none"
    long_ = sum(1 for x in g if x > LONG)
    short = sum(1 for x in g if x < SHORT)
    return (f"{name}: {len(times)}, {long_} long, {short} short, gaps {min(g):.1f} to {max(g):.1f} ms "
            f"(mean {sum(g) / len(g):.2f})")


before = 0
total_long = total_short = 0
print(f"{len(F)} fields, {len(P)} pictures over {(F[-1][0] - F[0][0]) / 1e6:.1f} s")
for end, field, buttons in F:
    pressed = buttons & ~before
    before = buttons
    if not pressed & 0x1001:
        continue
    kind = "Start" if pressed & 0x1000 else "D-pad left"
    on = field + COUNTDOWN   # where the race would run on, were it a resume or a load
    lo, hi = at.get(on - BEFORE), at.get(on + AFTER)
    if lo is None or hi is None:
        print(f"field {field}, {kind}: the log ends too soon")
        continue
    pictures = [t for t in P if lo <= t <= hi]
    fields = [at[f] for f in range(on - BEFORE, on + AFTER + 1) if f in at]
    g = gaps(pictures)
    total_long += sum(1 for x in g if x > LONG)
    total_short += sum(1 for x in g if x < SHORT)
    print(f"field {field}, {kind} (the race on at field {on}, if this resumed it):")
    print("   " + judge("pictures", pictures))
    print("   " + judge("fields", fields))
    odd = [(round((t - at[on]) / period), round(x, 1)) for t, x in zip(pictures[1:], g) if x > LONG or x < SHORT]
    if odd:
        print("   odd gaps (fields from the race on, ms): " + ", ".join(f"{f:+d}: {x}" for f, x in odd[:12]))
print(f"in all: {total_long} long gaps, {total_short} short")
