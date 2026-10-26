#!/usr/bin/env python3
"""map-pace.py RUNDIR [--from N] [--to N] [--mode N]: a scene's frame pacing and the video thread's totals from the
runner's pacing log alone (pace.csv; rb.csv beside it when the core's rollback log was on). No sampler needed, so
it reads any run that has a pacing log (match-run.sh, pair-run.sh, map-run.sh).

  fields        wall time and the CPU thread's own time per field (the F records' cycle counter)
  pictures      the gap between two presented pictures; every gap over 20 ms with what the log holds around it: the
                CPU thread's longest field, a rollback and its depth, a shader or pipeline built, a stretch of
                graphics work of 2 ms or more, a copy out of the frame buffer, textures made
  video thread  its own time per picture (the P records' cycle counter, the thread that presents), the present call,
                the wait before it; draw calls, primitives, vertex and uniform bytes per picture; textures
Reads files only."""
import argparse
import bisect
import collections
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))
import work_folder  # noqa: E402
from map_lib import Run  # noqa: E402


def q(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, int(len(v) * p))] if v else float("nan")


def line(name, values, unit="ms"):
    if not values:
        print(f"  {name}: none"); return
    print(f"  {name}: mean {statistics.mean(values):.3f}, median {statistics.median(values):.3f}, 90% {q(values, .9):.3f}, "
          f"99% {q(values, .99):.3f}, most {max(values):.3f} {unit}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--from", dest="first", type=int, default=600)
    ap.add_argument("--to", dest="last", type=int, default=10 ** 9)
    ap.add_argument("--mode", type=int, default=2)
    ap.add_argument("--gaps", type=int, default=12)
    a = ap.parse_args()
    run = Run(a.run if os.path.isdir(a.run) else f"{os.environ.get('PORT_WORK', work_folder.WORK_DEFAULT)}/port/runs/{a.run}")
    scene = [(run.fields[i - 1][0],) + run.fields[i] for i in range(1, len(run.fields))
             if run.fields[i][3] == a.mode and a.first <= run.fields[i][5] <= a.last]
    if not scene:
        print("no field of the scene"); return
    t0, t1 = scene[0][0], scene[-1][1]
    us = run.tsc_per_us
    print(f"{os.path.basename(run.folder.rstrip('/'))}: {run.backend}; scene race frames {scene[0][6]}-{scene[-1][6]}, {len(scene)} fields, {(t1 - t0) / 1e6:.1f} s")
    line("field, wall", [(s[1] - s[0]) / 1000 for s in scene])
    line("CPU thread per field", [s[3] / us / 1000 for s in scene])
    print(f"  fields over 20 ms: {sum(1 for s in scene if s[1] - s[0] > 20000)}; race frames per field {(scene[-1][6] - scene[0][6]) / len(scene):.3f}; "
          f"run-loop trips a field {statistics.mean(s[7] for s in scene):.0f} (idle {statistics.mean(s[8] for s in scene):.0f})")
    pres = [p for p in run.presents if t0 <= p[2] <= t1]
    if len(pres) < 3:
        print("no pictures in the scene"); return
    by_thread = collections.Counter(p[4] for p in pres)
    tid = by_thread.most_common(1)[0][0]
    pres = [p for p in pres if p[4] == tid]
    gaps = [(pres[i][2] - pres[i - 1][2]) / 1000 for i in range(1, len(pres))]
    print(f"pictures: {len(pres)} in {(pres[-1][2] - pres[0][2]) / 1e6:.1f} s = {(len(pres) - 1) / ((pres[-1][2] - pres[0][2]) / 1e6):.2f} a second (thread {tid})")
    line("picture to picture", gaps)
    line("video thread's own time per picture", [p[3] / us / 1000 for p in pres[1:]])
    line("the present call", [(p[2] - p[1]) / 1000 for p in pres])
    line("the wait before it", [(p[1] - p[0]) / 1000 for p in pres])
    line("draw calls", [p[5] for p in pres], "")
    line("primitives", [p[6] for p in pres], "")
    line("vertex bytes", [p[7] for p in pres], "")
    line("uniform bytes", [p[8] for p in pres], "")
    print(f"  textures made {sum(p[9] for p in pres)}, uploaded {sum(p[10] for p in pres)} over the scene; alive at its end {pres[-1][11]}")
    video_s = sum(p[3] for p in pres[1:]) / us / 1e6
    print(f"  video thread: {video_s / ((pres[-1][2] - pres[0][2]) / 1e6) * 100:.1f}% of one core; per field {video_s * 1000 / len(scene):.3f} ms")
    # causes of late pictures
    late = [(gaps[i - 1], pres[i - 1][2], pres[i][2]) for i in range(1, len(pres)) if gaps[i - 1] > 20]
    print(f"picture gaps over 20 ms: {len(late)} of {len(gaps)} ({100 * len(late) / len(gaps):.2f}%); over 25 ms: {sum(1 for g in gaps if g > 25)}; over 33 ms: {sum(1 for g in gaps if g > 33.4)}")
    f_end = [s[1] for s in scene]
    rb = [(int(r["at_us"]), int(r["depth"]), float(r["hook_us"]), float(r["track_us"])) for r in run.rollback] if run.rollback else []
    rb_at = [r[0] for r in rb]
    spans = {k: [(int(r[0]), int(r[1]), r[2] if len(r) > 2 else "") for r in run.other_records.get(k, [])] for k in "TSE"}
    causes = collections.Counter()
    shown = 0
    for gap, a0, a1 in sorted(late, reverse=True):
        lo = bisect.bisect_left(f_end, a0 - 20000); hi = bisect.bisect_right(f_end, a1 + 1000)
        cpu = max((scene[i][3] / us / 1000 for i in range(lo, min(hi, len(scene)))), default=0)
        depth = max((rb[i][1] for i in range(bisect.bisect_left(rb_at, a0 - 40000), bisect.bisect_right(rb_at, a1))), default=0) if rb else 0
        notes = []
        for k, what in (("S", "built"), ("T", "graphics stretch"), ("E", "copy")):
            hits = [s for s in spans[k] if a0 - 20000 <= s[0] <= a1 and (k != "E" or s[1] >= 2000)]
            if hits:
                notes.append(f"{what} {max(h[1] for h in hits) / 1000:.1f} ms" + (f" ({hits[0][2]})" if k != "E" else ""))
        cause = ("rollback" if depth and cpu > 14 else "a long field of the CPU thread" if cpu > 14 else notes[0].split(" ")[0] if notes else "nothing recorded")
        causes[cause] += 1
        if shown < a.gaps:
            shown += 1
            print(f"  {gap:6.1f} ms: CPU thread's longest field around it {cpu:.1f} ms" + (f", rollback of {depth}" if depth else "") + ("; " + "; ".join(notes) if notes else ""))
    if late:
        print("  by cause: " + ", ".join(f"{k} {v}" for k, v in causes.most_common()))
    if rb:
        inside = [r for r in rb if t0 <= r[0] <= t1]
        by_depth = collections.defaultdict(list)
        for r in inside:
            by_depth[r[1]].append(r)
        print("rollback log, per displayed frame: depth, frames, the hook (ms), the undo log (ms)")
        for d in sorted(by_depth):
            v = by_depth[d]
            print(f"  {d:3d} {len(v):6d}  {statistics.mean(x[2] for x in v) / 1000:7.3f}  {statistics.mean(x[3] for x in v) / 1000:7.3f}")


if __name__ == "__main__":
    main()
