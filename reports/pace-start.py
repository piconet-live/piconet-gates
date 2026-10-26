#!/usr/bin/env python3
"""pace-start.py PACE.csv...: a pacing log's start of race (the runner's FZGX_PACE_LOG, as pace-report.py): the long fields (over 50 ms) from the game's first race-mode field to race frame 400,
what the log holds inside each, and how long the catch-up after them lasts (fields in which the race frame
advances by more than one)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the pacing log)
for path in sys.argv[1:]:
    log = logs.pacing(path); rec = log.records   # whole records only (one cut short at the file's end is dropped)
    F = rec["F"]
    hz = log.rate()
    t0 = int(F[0][1]); at = lambda r, c=1: (int(r[c]) - t0) / 1e6
    first2 = next((i for i, f in enumerate(F) if f[4] in ("2", "12")), None)
    if first2 is None: print(path, "no race"); continue
    end = next((i for i, f in enumerate(F) if i > first2 and int(f[6]) >= 400), len(F) - 1)
    go = next((i for i, f in enumerate(F) if i > first2 and int(f[6]) > 0), None)
    print(f"\n=== {path.split('/')[-2]}/{path.split('/')[-1]}: mode 2 from field {F[first2][2]} ({at(F[first2]):.2f} s), race frame 1 at field {F[go][2]} ({at(F[go]):.2f} s)")
    P = sorted(rec["P"], key=lambda p: int(p[2]))
    for i in range(max(first2 - 60, 1), end):
        f, prev = F[i], F[i - 1]
        dt = (int(f[1]) - int(prev[1])) / 1000
        if dt < 50: continue
        a, z = at(prev), at(f)
        inside = lambda rows, c=1: [r for r in rows if a <= at(r, c) < z]
        pres = inside(P, 2); S = inside(rec["S"]); T = inside(rec["T"])
        X = inside(rec["X"]); N = inside(rec["N"])
        print(f"  field {f[2]} ({a:.3f}-{z:.3f} s): {dt:7.1f} ms; CPU thread {int(f[3]) / hz / 1000:7.1f} ms; mode {f[4]}/{f[5]} race frame {prev[6]}->{f[6]}; "
              f"fallback steps {f[17]}, interpreted {f[18]}, chunk checks {f[19]}, failing {f[20]}, trips {f[21]}, idles {f[22]}, fallback JIT {int(f[23]) / hz / 1000:.1f} ms")
        print(f"      fallback PCs [{f[24]}] interpreted PCs [{f[25]}] checked [{f[26] if len(f) > 26 else ''}]")
        print(f"      pictures presented inside: {len(pres)}" + (f", longest call {max(int(p[3]) - int(p[2]) for p in pres) / 1000:.1f} ms, video thread {sum(int(p[4]) for p in pres) / hz / 1000:.1f} ms" if pres else "")
              + f"; builds {len(S)} ({sum(int(s[2]) for s in S) / 1000:.1f} ms); graphics spans {[(t[3], round(int(t[2]) / 1000, 1)) for t in T][:4]}; textures made {sum(x[3] == 'made' for x in X)}, given up {sum(x[3] == 'given up' for x in X)}; invalidated {sum(int(n[4]) for n in N)}")
    # catch-up: fields where race frame advances by 2 or more, from go to race frame 400
    double = [i for i in range(go + 1, end) if int(F[i][6]) - int(F[i - 1][6]) >= 2]
    zero = [i for i in range(go + 1, end) if int(F[i][6]) == int(F[i - 1][6])]
    if double:
        print(f"  catch-up: {len(double)} fields with two or more race frames, from field {F[double[0]][2]} to {F[double[-1]][2]} ({at(F[double[0]]):.2f}-{at(F[double[-1]]):.2f} s); {len(zero)} fields with no race frame")
    else:
        print(f"  catch-up: none; {len(zero)} fields with no race frame")
