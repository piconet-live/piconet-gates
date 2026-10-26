#!/usr/bin/env python3
"""rollback-report.py RUN [RUN...]: what rollback costs in a run, per depth (the port-recomp notes 5.14).

Reads <work>/port/runs/RUN/rb.csv, the core's rollback log (the launch file's debug.rollbackLog: one line for every displayed frame
of the race phase), and RUN/pace.csv, the runner's pacing log (FZGX_PACE_LOG), whose F records give the CPU thread's
own time in every field. Both use one clock, so a frame's fields are the F records that end between its first hook
call and the next frame's.

Per depth of rollback (0: frames with none), all times in milliseconds:
  frames     how many                      undo      the undo log's comparisons in the frame (wall)
  restore    putting memory back (wall)    hook      everything inside the hook: undo, restore, checksums, relay
  first      the frame's first step, the game's code between the first hook call and the second
  re-sim     one re-simulated step: the game's code between two later hook calls, mean and 99%
  CPU thread the CPU thread's own time for the frame: median, 99%, longest. Fields and game frames are not locked
             to each other in dual core, so a frame's time is taken over three frames (the one before, itself, the
             one after) less twice a plain frame's median: right when its neighbours are plain frames (rollbacks
             forced every few frames), meaningless when every frame rolls back (the summary line then says what a
             frame costs on average)
  frame to frame   from this frame's first hook call to the next frame's: 16.7 ms when the work fitted
Reads files only."""
import bisect
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs   # noqa: E402  (the one reader of the pacing log and the rollback log)

W = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT) + "/port/runs"
RUNS = sys.argv[1:]
FIELD_MS = 1000 / 59.94


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))] if values else float("nan")


def report(run):
    rows = logs.rollback_log(f"{W}/{run}/rb.csv")
    if not rows:
        print(f"{run}: the rollback log is empty")
        return
    pace = logs.pacing(f"{W}/{run}/pace.csv")
    fields = [(int(part[1]), int(part[3])) for part in pace["F"]]   # end_us, cpu_thread_cycles
    hz = pace.rate(default=None)   # cycles a microsecond
    ends = [f[0] for f in fields]
    at = [int(r["at_us"]) for r in rows]
    groups = {}
    total = [0] * (len(fields) + 1)
    for k, (_, c) in enumerate(fields):
        total[k + 1] = total[k] + c
    between = lambda a, b: (total[bisect.bisect_right(ends, b)] - total[bisect.bisect_right(ends, a)]) / hz / 1000
    is_plain = lambda i: (int(rows[i]["depth"]) == 0 and int(rows[i]["catch_up"]) == 0 and
                          not any(int(rows[j]["depth"]) > 0 for j in range(max(0, i - 2), i)))
    plain = [between(at[i], at[i + 1]) for i in range(len(rows) - 1) if hz and is_plain(i)
             and bisect.bisect_right(ends, at[i + 1]) - bisect.bisect_right(ends, at[i]) == 1]
    plain_median = statistics.median(plain) if plain else None
    for i, r in enumerate(rows[:-1]):   # the last line's frame was still running when the log closed
        nxt = at[i + 1]
        if nxt - at[i] > 200_000:        # the frames on either side of a gap in the race phase (never seen)
            continue
        cpu = None
        if plain_median is not None and int(r["depth"]) > 0 and 0 < i < len(rows) - 2:
            cpu = between(at[i - 1], at[i + 2]) - 2 * plain_median
        elif hz and bisect.bisect_right(ends, nxt) - bisect.bisect_right(ends, at[i]) == 1:
            cpu = between(at[i], nxt)   # a frame with no rollback: only when exactly one field ended inside it
        key = int(r["depth"])
        # a frame with no rollback is "plain" only when it adds no catch-up step and neither of the two frames before
        # it rolled back (a rollback frame that ran long is made up for in the frames after it)
        if key == 0 and (int(r["catch_up"]) > 0 or any(int(rows[j]["depth"]) > 0 for j in range(max(0, i - 2), i))):
            key = -1
        g = groups.setdefault(key, dict(n=0, forced=0, undo=[], restore=[], hook=[], first=[], resim=[], cpu=[],
                                        blocks=[], period=[], catch=0))
        g["n"] += 1
        g["forced"] += int(r["forced"])
        g["catch"] += int(r["catch_up"]) > 0
        g["undo"].append(float(r["track_us"]) / 1000)
        g["restore"].append(float(r["restore_us"]) / 1000)
        g["hook"].append(float(r["hook_us"]) / 1000)
        g["blocks"].append(int(r["blocks"]))
        g["period"].append((nxt - at[i]) / 1000)
        if float(r["first_us"]) > 0:
            g["first"].append(float(r["first_us"]) / 1000)
        if int(r["resim_n"]) > 0:
            g["resim"].append(float(r["resim_us"]) / 1000 / int(r["resim_n"]))
        if cpu is not None:
            g["cpu"].append(cpu)
    steps = [int(r["step"]) for r in rows]
    print(f"{run}: {len(rows)} displayed frames of the race phase, steps {steps[0]}-{steps[-1]}; "
          f"{sum(int(r['depth']) > 0 for r in rows)} rollbacks ({sum(int(r['forced']) for r in rows)} forced), "
          f"{sum(int(r['catch_up']) for r in rows)} catch-up steps; steps ahead of the official frames: median "
          f"{statistics.median(int(r['ahead']) for r in rows):.0f}")
    if hz and len(rows) > 2:
        seconds = (at[-1] - at[0]) / 1e6
        print(f"  the race phase: {between(at[0], at[-1]) / (len(rows) - 1):.2f} ms of the CPU thread a displayed frame "
              f"on average, {(len(rows) - 1) / seconds:.2f} frames a second, {(steps[-1] - steps[0]) / seconds:.2f} new "
              f"steps a second; a plain frame's median {plain_median if plain_median is not None else float('nan'):.2f} ms")
    print("| Depth | Frames | Undo log | Restore | In the hook | First step | A re-simulated step (99%) | "
          "CPU thread: median, 99%, longest | Frame to frame: median, 99%, longest | Left of 16.68 ms (median) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    mean = lambda v: statistics.fmean(v) if v else float("nan")
    name = {0: "none (plain frames)", -1: "none (a catch-up step, or just after a rollback)"}
    for depth in sorted(groups, key=lambda d: (d != 0, d != -1, d)):
        g = groups[depth]
        resim = f"{mean(g['resim']):.2f} ({pct(g['resim'], 0.99):.2f})" if g["resim"] else "-"
        cpu = (f"{statistics.median(g['cpu']):.2f}, {pct(g['cpu'], 0.99):.2f}, {max(g['cpu']):.2f}" if g["cpu"] else "-")
        left = f"{FIELD_MS - statistics.median(g['cpu']):.1f}" if g["cpu"] else "-"
        print(f"| {name.get(depth, depth)} | {g['n']} | {mean(g['undo']):.2f} | {mean(g['restore']):.3f} | {mean(g['hook']):.2f} | "
              f"{mean(g['first']):.2f} | {resim} | {cpu} | {statistics.median(g['period']):.1f}, {pct(g['period'], 0.99):.1f}, "
              f"{max(g['period']):.1f} | {left} |")
    # the CPU thread's time against the depth, by least squares over the frames that rolled back
    xs = [d for d, g in groups.items() if d > 0 for _ in g["cpu"]]
    ys = [c for d, g in groups.items() if d > 0 for c in g["cpu"]]
    if len(set(xs)) > 1:
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        base = my - slope * mx
        print(f"CPU thread of a rollback frame = {base:.2f} ms + {slope:.2f} ms a step rolled back; "
              f"16.68 ms is reached at {(FIELD_MS - base) / slope:.1f} steps")
    all_blocks = [b for g in groups.values() for b in g["blocks"]]
    print(f"blocks logged a frame: mean {mean(all_blocks):.0f}, most {max(all_blocks)}")


for name in RUNS:
    report(name)
