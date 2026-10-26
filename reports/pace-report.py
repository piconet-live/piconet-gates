#!/usr/bin/env python3
"""pace-report.py PACE.csv: what a pacing log shows, around the boosts and elsewhere.

The log is the runner's (FZGX_PACE_LOG=<file>; the runtime's FzgxProbe, StartPaceLog; its first lines name every
column). Records, all with times in microseconds of one clock:
  F a field ended (CPU thread)            P a picture was presented (video thread: wait, the present call, draws)
  S a shader or pipeline was built        T a stretch of graphics work of 2 ms or more (Vulkan's submit path)
  E a copy out of the frame buffer        X a texture made or given up by the backend (Vulkan), and during what
  N the texture cache's size at a frame's end      R a rumble command      C clock calibration

A stall is a present call longer than 12 ms (CALL) or a gap between two pictures longer than 25 ms (LATE: a field
and a half). A boost is racer 0's flag 0x20 coming on in a race (the machine the game's own
camera follows; in a match race that is seat 0); a press of Y on port 1 is listed beside it. For every boost: the
stalls in the 350 ms (AFTER) that follow. Then every stall of the race with what the graphics thread
recorded inside it, and the texture cache's size over the race (its largest and smallest, the frames with more
than 50 entries invalidated).
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the pacing log)

path = sys.argv[1]
LATE, CALL, AFTER = 25.0, 12.0, 350.0 / 1000   # ms, ms, s

log = logs.pacing(path)   # its whole records (a record cut short at the file's end is dropped)
rec = log.records
started = ""
for note in log.notes:
    if note.startswith("pacing log"):
        started = note
    if note.startswith("graphics backend"):
        started += "\n" + note
F, P, S, T, E, X, N, C = (rec[k] for k in "FPSTEXNC")
if not F:
    sys.exit("no field in the log")
hz = log.rate()   # cycles a microsecond
t0 = int(F[0][1])
at = lambda row, column=1: (int(row[column]) - t0) / 1e6
energy = lambda text: struct.unpack(">f", bytes.fromhex(text))[0]
P.sort(key=lambda p: int(p[2]))

print(started)
print(f"{len(F)} fields over {at(F[-1]):.1f} s, {len(P)} pictures, {len(S)} shader or pipeline builds, "
      f"{len(rec['R'])} rumble commands, {len(X)} texture events; time stamp counter {hz / 1000:.3f} GHz")
race = [f for f in F if f[4] in ("2", "12") and int(f[6]) > 0]
if not race:
    sys.exit("no field of a race in the log")
r0, r1 = at(race[0]), at(race[-1])
print(f"the race: fields {race[0][2]}-{race[-1][2]} ({r0:.2f} s to {r1:.2f} s), race frames {race[0][6]}-{race[-1][6]}")

stalls, previous = [], None
for p in P:
    call = (int(p[3]) - int(p[2])) / 1000
    gap = (int(p[2]) - previous) / 1000 if previous else 0
    previous = int(p[2])
    if call > CALL or gap > LATE:
        stalls.append(dict(t=at(p, 2), call=call, gap=gap, thread=int(p[4]) / hz / 1000, p=p))
race_p = [p for p in P if r0 <= at(p, 2) <= r1]
gaps = sorted((int(b[2]) - int(a[2])) / 1000 for a, b in zip(race_p, race_p[1:]))
times = sorted((int(b[1]) - int(a[1])) / 1000 for a, b in zip(race, race[1:]))
cpu = sorted(int(f[3]) / hz / 1000 for f in race)
q = lambda rows, x: rows[min(len(rows) - 1, int(x * len(rows)))] if rows else float("nan")
print(f"  picture gaps: median {q(gaps, 0.5):.2f} ms, 99% {q(gaps, 0.99):.2f}, 99.9% {q(gaps, 0.999):.2f}, longest {q(gaps, 1):.1f}")
print(f"  field times: median {q(times, 0.5):.2f} ms, 99% {q(times, 0.99):.2f}, longest {q(times, 1):.1f}; "
      f"CPU thread a field: median {q(cpu, 0.5):.2f} ms, 99% {q(cpu, 0.99):.2f}")
print(f"  fallback steps {sum(int(f[17]) for f in race)}, interpreted instructions {sum(int(f[18]) for f in race)}, "
      f"chunk checks {sum(int(f[19]) for f in race)}, pad reads a field {min(int(f[16]) for f in race)}-{max(int(f[16]) for f in race)}")

boosts = []
for prev, f in zip(F, F[1:]):
    if f[4] not in ("2", "12"):
        continue
    on = int(f[7], 16) & 0x20 and not int(prev[7], 16) & 0x20
    y = int(f[9], 16) & 0x800 and not int(prev[9], 16) & 0x800
    if on or y:
        boosts.append(dict(t=at(f), field=f[2], frame=f[6], energy=energy(f[8]), kind="boost" if on else "Y"))
flags = [b for b in boosts if b["kind"] == "boost"]
print(f"\n== boosts: {len(flags)} (racer 0's flag 0x20 coming on); presses of Y: {len(boosts) - len(flags)} ==")
hit = 0
for b in boosts:
    near = [s for s in stalls if 0 <= s["t"] - b["t"] < AFTER]
    hit += bool(near) and b["kind"] == "boost"
    print(f"  {b['t']:8.3f} s field {b['field']} race frame {b['frame']} energy {b['energy']:6.2f} {b['kind']:5s} "
          + "; ".join(f"+{(s['t'] - b['t']) * 1000:.0f} ms: present call {s['call']:.1f} ms, gap {s['gap']:.1f} ms" for s in near))
print(f"boosts followed within {AFTER * 1000:.0f} ms by a stall: {hit} of {len(flags)}")

print(f"\n== stalls in the race (a present call over {CALL:.0f} ms or a picture gap over {LATE:.0f} ms) ==")
for s in stalls:
    if not r0 <= s["t"] <= r1:
        continue
    near = [b for b in flags if 0 <= s["t"] - b["t"] < AFTER]
    a, z = s["t"] - 0.02, s["t"] + s["call"] / 1000 + 0.02
    p = s["p"]
    print(f"  {s['t']:8.3f} s present call {s['call']:6.1f} ms, gap {s['gap']:6.1f} ms, video thread {s['thread']:5.1f} ms; "
          + (f"{(s['t'] - near[-1]['t']) * 1000:.0f} ms after a boost began" if near else "no boost before")
          + (f"; {p[6]} draws, {p[10]} textures created" if len(p) > 11 else ""))
    for x in T:
        if a < at(x) < z:
            print(f"      {(at(x) - s['t']) * 1000:+7.1f} ms: {int(x[2]) / 1000:6.1f} ms {x[3]}")
    for x in S:
        if a - 0.1 < at(x) < z and int(x[2]) > 2000:
            print(f"      {(at(x) - s['t']) * 1000:+7.1f} ms: {int(x[2]) / 1000:6.1f} ms built: {x[3]}")
    given = collections.Counter(f"{x[4]}x{x[5]}" + (f" ({x[10]})" if len(x) > 10 and x[10] else "")
                                for x in X if x[3] == "given up" and s["t"] - 0.12 < at(x) < z)
    if given:
        print("      textures given up in the 120 ms before: " + "; ".join(f"{n} x {k}" for k, n in given.most_common(4)))

if N:
    sizes = [(at(n), int(n[2]), int(n[3]), int(n[4])) for n in N if r0 <= at(n) <= r1]
    if sizes:
        print(f"\n== the texture cache in the race: {min(s[1] for s in sizes)} to {max(s[1] for s in sizes)} entries, "
              f"up to {max(s[2] for s in sizes)} pooled ==")
        for t, entries, pooled, invalidated in sizes:
            if invalidated > 50:
                print(f"  {t:8.3f} s: {invalidated} entries invalidated in one frame ({entries} left, {pooled} pooled)")
made = collections.Counter((f"{x[4]}x{x[5]}", x[10] if len(x) > 10 else "", x[11] if len(x) > 11 else "") for x in X if x[3] == "made" and r0 <= at(x) <= r1)
if made:
    print("\n== textures made in the race, by size and by what the texture cache was doing (the five most frequent) ==")
    for (size, during, address), n in made.most_common(5):
        print(f"  {n} x {size} during: {during or '-'}" + (f" at 0x{address}" if during else ""))
