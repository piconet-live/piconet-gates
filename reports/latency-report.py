#!/usr/bin/env python3
"""latency-report.py RUN [RUN...] [--from STEP]: pad to picture, the pictures' pacing and what rollback cost, per game.

Reads <work>/port/runs/RUN: pace.csv (the runner's pacing log, debug.paceLog), and for a race rb.csv (the core's
rollback log, debug.rollbackLog) and race.fzrp (the game's recording). All three use one clock or count steps, so a
press can be followed from the pad to the present call with nothing but what every test game already writes
(the latency-presentation-and-delay notes has the reasoning and what the figures leave out).

  The pad      An F record (a field ended) holds port 1's pad as the game is about to read it. The emulator samples
               the pad at the serial poll 18 half-lines (0.57 ms of emulated time) before the field's end, after its
               last wait of the field, so the sample's time is the F record's less the few microseconds that stretch
               takes: the F record's time is used. An edge is an F record whose pad differs from the one before.
  The step     A race: the recording holds every step's official input of every player seat. The game's own seat's
               record changes at the step the press was stamped for. No race (offline play): NOT FOLLOWED. The
               pacing log holds nothing of the machine that answers a press (tried on 12 October, run lat-v020-off:
               racer 0's flags word at a field's end never showed one of 24 presses of Z), so for offline play
               this script gives the pictures' timing only, and says so.
  The picture  A race: the first displayed frame of the rollback log that ran that step; its pass's picture is the
               one the game copies out after the next field's end (the game's own loop: copy, pad, simulate, draw,
               wait). The picture's time is the first present call (P, after its wait) after that copy (E, the copy
               to the display buffer). That the pass draws what it has just simulated is the game's code, not a
               measurement of this script; no pixel is looked at.

Per game: the input delay its recording names and how it showed its pictures (its log: field, console or copy), pad to picture in
fields and in milliseconds (median, least, most), the present calls' intervals (their spread, and how many are off
16.68 ms by more than 1, 2 and 4 ms), where in the field a picture is shown, rollbacks (how many, median and
deepest), the game thread's time a field and the fields that took longer than 16.68 ms, and the time sync's figure.
With more than one RUN: whether the recordings are one race (replay-compare.py's comparison).
--from STEP: only presses and frames from that step on (default 600: the race under way).
Reads files only."""
import bisect
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py
import work_folder   # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs   # noqa: E402  (the one reader of the pacing log and the rollback log)
import parts  # noqa: E402
sys.path.insert(0, parts.path_in("REPO_PROTOCOL", "protocol/generated"))   # the replay file's reader (protocol/replay.toml)
import replay_file  # noqa: E402

W = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT) + "/port/runs"
FIELD_US = 1e6 / 59.94


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p / 100))] if values else float("nan")


def spread(values, unit=1000.0):
    if not values:
        return "none"
    return (f"median {statistics.median(values) / unit:.2f}, least {min(values) / unit:.2f}, 1% {pct(values, 1) / unit:.2f}, "
            f"99% {pct(values, 99) / unit:.2f}, most {max(values) / unit:.2f}, sd {statistics.pstdev(values) / unit:.2f} (n={len(values)})")


def pacing(path):
    """The pacing log (logs.py): F (end_us, field, cycles, mode, race_frame, flags, pad), E copies to the display buffer, P presents, the cycle rate."""
    log = logs.pacing(path)
    fields = [(int(c[1]), int(c[2]), int(c[3]), int(c[4]), int(c[6]), c[7], tuple(c[9:16])) for c in log["F"]]
    copies = [int(c[1]) for c in log["E"] if c[logs.column("E", "xfb")] == "1"]
    presents = sorted(((int(c[1]), int(c[2]), int(c[3])) for c in log["P"]), key=lambda p: p[1])
    return fields, copies, presents, log.rate()   # (the rate: cycles a microsecond)


def recording(path):
    """The recording: its header, the recorder's seat, and for every step the recorder's own 6-byte control record."""
    r = replay_file.read(path)
    if not r.marked:
        raise ValueError(f"{path}: not a replay")
    header = json.loads(r.header)
    mine = r.seats.index(r.seat) * replay_file.RECORD_SIZE if r.seat in r.seats else None
    own = [row[mine:mine + replay_file.RECORD_SIZE] for row, _ in r.steps] if mine is not None else []
    return header, r.seat, own


def shown_after(log, field_index):
    """The present call that shows the picture of the pass in the field at `field_index`: the first after the copy
    that follows the field's end (its time after the wait; None when the log ends before it)."""
    ends, copies, present_at = log["ends"], log["copies"], log["present_at"]
    end = ends[field_index]
    nxt = ends[field_index + 1] if field_index + 1 < len(ends) else end + 2 * FIELD_US
    ci = bisect.bisect_left(copies, end - 300)   # (a copy the picture thread ran a moment before the F record was written)
    copy = copies[ci] if ci < len(copies) and copies[ci] < nxt - 300 else None
    pi = bisect.bisect_left(present_at, (copy if copy is not None else end) - 50)
    return present_at[pi] if pi < len(present_at) else None


def follow_presses(log, own, delay, rb, first_step):
    """Each change of the seat's own record from `first_step` on, back to the pad edge that made it and forward to
    its picture: (fields from the pad to the pass that stamped it, fields to the one its picture is shown in, ms
    from the pad's sample to the present call) for every press followed, and how many changes there were."""
    ends, edges = log["ends"], log["edges"]
    frame_at = [int(r["at_us"]) for r in rb]
    frame_step = [int(r["step"]) + int(r["catch_up"]) for r in rb]   # the newest step the frame's picture shows
    changes = [t for t in range(max(1, first_step), len(own)) if own[t] != own[t - 1]]
    followed = []
    for t in changes:
        # the frame that stamped step t ran step t - delay, in the pass after the field whose F record shows the new pad
        stamped = bisect.bisect_left(frame_step, t - delay)
        ran = bisect.bisect_left(frame_step, t)                   # the first frame whose picture holds step t
        if ran >= len(rb) or stamped >= len(rb):
            continue
        pass_field = bisect.bisect_left(ends, frame_at[ran])      # the field the frame's pass is in (ends when it ends)
        stamp_field = bisect.bisect_left(ends, frame_at[stamped])
        if pass_field >= len(ends) or stamp_field < 1:
            continue
        ei = bisect.bisect_right(edges, stamp_field - 1) - 1      # the last pad edge before the stamping frame's hook
        if ei < 0 or stamp_field - 1 - edges[ei] > 3:
            continue   # no pad edge near: a change the relay made (a late input replaced), or the AI's
        when = shown_after(log, pass_field)
        if when is not None:
            followed.append((stamp_field - edges[ei], pass_field + 1 - edges[ei], when - ends[edges[ei]]))
    return followed, len(changes)


def say_pacing(log, first_step):
    """The pictures' pacing over the race, and the fields' and the game thread's times."""
    fields, ends, presents, rate = log["fields"], log["ends"], log["presents"], log["rate"]
    racing = [i for i, f in enumerate(fields) if f[3] in (2, 12) and f[4] >= first_step]
    if len(racing) <= 10:
        return
    shown = [p for p in presents if ends[racing[0]] <= p[1] <= ends[racing[-1]]]
    gaps = [b[1] - a[1] for a, b in zip(shown, shown[1:])]
    off = [abs(g - FIELD_US) for g in gaps]
    print(f"   present to present, ms: {spread(gaps)}")
    print(f"   intervals off 16.68 ms by more than 1 / 2 / 4 ms: {sum(o > 1000 for o in off)} / {sum(o > 2000 for o in off)} / "
          f"{sum(o > 4000 for o in off)} of {len(gaps)}; over 25 ms (a stall): {sum(g > 25000 for g in gaps)}")
    phase = [p[1] - ends[i] for p in shown for i in [bisect.bisect_right(ends, p[1]) - 1] if i >= 0]
    print(f"   a picture is shown this long after its field began, ms: {spread(phase)}")
    waits = [p[1] - p[0] for p in shown]
    print(f"   the presenter's own wait before the call, ms: median {statistics.median(waits) / 1000:.2f}, most {max(waits) / 1000:.2f}; "
          f"the call: median {statistics.median([p[2] - p[1] for p in shown]) / 1000:.2f}, most {max(p[2] - p[1] for p in shown) / 1000:.2f}")
    between = [ends[b] - ends[a] for a, b in zip(racing, racing[1:]) if b == a + 1]
    work = [fields[i][2] / rate for i in racing]
    print(f"   field to field, ms: {spread(between)}")
    print(f"   fields longer than 16.68 ms by more than 1 / 4 ms: {sum(b > FIELD_US + 1000 for b in between)} / "
          f"{sum(b > FIELD_US + 4000 for b in between)} of {len(between)}")
    print(f"   the game thread's own time a field (its cycle counter; the frame limiter's busy wait is in it), ms: {spread(work)}; "
          f"over 16.68 ms: {sum(w > FIELD_US for w in work)}")


def say_rollbacks(rb, first_step, text):
    """What rollback cost: how many and how deep, the steps a frame ran, the time sync's figure, the frames' pace."""
    rows = [r for r in rb if int(r["step"]) >= first_step]
    if not rows:
        return
    depths = [int(r["depth"]) for r in rows if int(r["depth"]) > 0 and r.get("forced", "0") == "0"]
    forced = [int(r["depth"]) for r in rows if int(r["depth"]) > 0 and r.get("forced", "0") != "0"]
    sched = [float(r["sched"]) for r in rows]
    steps = [1 + int(r["resim_n"]) for r in rows]
    at = [int(r["at_us"]) for r in rows]
    frames = [b - a for a, b in zip(at, at[1:])]
    print(f"   rollbacks (not forced): {len(depths)} in {len(rows)} displayed frames"
          + (f", depth median {statistics.median(depths):g}, 90% {pct(depths, 90)}, deepest {max(depths)}" if depths else "")
          + (f"; forced: {len(forced)}, depths {sorted(set(forced))}" if forced else "; none forced"))
    print(f"   steps run a displayed frame: mean {statistics.mean(steps):.2f}, most {max(steps)}; held frames {sum(r['held'] != '0' for r in rows)}, "
          f"catch-up steps {sum(int(r['catch_up']) for r in rows)}")
    print(f"   ahead of the schedule (the time sync's figure, steps): median {statistics.median(sched):.2f}, least {min(sched):.2f}, most {max(sched):.2f}")
    print(f"   displayed frame to displayed frame (the hook's clock), ms: {spread(frames)}; over 16.68 ms by more than 1 / 4 ms: "
          f"{sum(f > FIELD_US + 1000 for f in frames)} / {sum(f > FIELD_US + 4000 for f in frames)}")
    summary = [line for line in text.splitlines() if "race summary:" in line]
    if summary:
        print("   " + summary[-1][summary[-1].index("race summary:"):].strip()[:520])


def report(run, first_step):
    folder = run if os.path.isdir(run) else f"{W}/{run}"
    name = os.path.basename(folder.rstrip("/"))
    fields, copies, presents, rate = pacing(f"{folder}/pace.csv")
    race = os.path.isfile(f"{folder}/race.fzrp") and os.path.isfile(f"{folder}/rb.csv")
    text = ""
    for part in ("fzgx.log", "stderr.txt"):
        if os.path.isfile(f"{folder}/{part}"):
            text += open(f"{folder}/{part}", encoding="utf-8", errors="replace").read()
    shown = re.search(r'TEST SETTING: presentation is "(\w+)"', text)
    # (runner 84471de3, the first build of the setting, said "early presentation is on" for what is "copy" now)
    early = shown.group(1) if shown else "copy" if "early presentation is on" in text else "field"
    log = dict(fields=fields, copies=copies, presents=presents, rate=rate, ends=[f[0] for f in fields],
               present_at=[p[1] for p in presents],
               edges=[k for k in range(1, len(fields)) if fields[k][6] != fields[k - 1][6]])
    print(f"== {name}: {'a race' if race else 'no race (offline play)'}; presentation {early}; {len(fields)} fields, "
          f"{len(presents)} pictures, {len(log['edges'])} pad edges in the log")
    rb = logs.rollback_log(f"{folder}/rb.csv") if race else []
    if race:
        header, seat, own = recording(f"{folder}/race.fzrp")
        print(f"   recording: seat {seat}, input delay {header.get('delay')} (its header), {len(own)} steps; engine {header.get('engine', '-')}, "
              f"module {str(header.get('module_sha1', '-'))[:8]}, image {str(header.get('mod_sha1', '-'))[:8]}")
        followed, changes = follow_presses(log, own, int(header.get("delay", 2)), rb, first_step)
        print(f"   presses followed: {len(followed)} of {changes} changes of the seat's own record from step {first_step} on")
        if followed:
            stamp, show, ms = zip(*followed)
            print(f"   pad to the pass that stamped it, in fields: { {n: stamp.count(n) for n in sorted(set(stamp))} }")
            print(f"   pad to the field its picture is shown in, in fields: { {n: show.count(n) for n in sorted(set(show))} }")
            print(f"   PAD TO PICTURE (the pad's sample to the present call), ms: {spread(list(ms))}")
    else:
        print("   presses followed: none. Offline play has no recording to find a press's step in, and the pacing log holds "
              "nothing of the machine that answers one: pad to simulation is not measured here")
    say_pacing(log, first_step)
    if race:
        say_rollbacks(rb, first_step, text)
    return f"{folder}/race.fzrp" if race else None


def main(argv):
    first_step, runs = 600, []
    it = iter(argv)
    for a in it:
        if a == "--from":
            first_step = int(next(it))
        else:
            runs.append(a)
    if not runs:
        sys.exit(__doc__)
    recordings = [r for r in (report(run, first_step) for run in runs) if r]
    if len(recordings) > 1:
        import subprocess
        compare = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "replay-compare.py")
        out = subprocess.run([sys.executable, compare, *recordings], capture_output=True, text=True)
        print("== one race?")
        print("   " + out.stdout.strip().replace("\n", "\n   "))
        print("   " + ("EQUAL: inputs and checksums at every step both recorded" if out.returncode == 0 else "NOT EQUAL"))
        return out.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
