#!/usr/bin/env python3
"""quickplay-report.py RUN [RUN...]: what a Quick Play run through the launchers showed (quickplay-run.sh;
the port-recomp notes 5.15). Reads files only.

For each run and each of its races: the match (course, laps, seats), each launcher's times from the start vote to
the green light (the door's lines), the launchers' replays of that match compared step by step (replay-compare.py:
every final step's inputs and the checksum each game computed for it), each game's rollbacks by depth and the
pictures it lost, the round trip its game measured, the final standings each launcher was sent by its own game, and
what a launcher that only waited in the lobby received.

A lost picture: two pictures of the race phase more than 25 ms apart (a field and a half) have at least one picture
missing between them; the gap's length over 16.683 ms, rounded, less one, is how many. A gap is put down to a
rollback when a rollback frame began within 60 ms before the gap's end, and to that rollback's depth."""
import bisect
import collections
import datetime
import glob
import json
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs   # noqa: E402  (the one reader of the pacing log and the rollback log)

W = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT)
RUNS = sys.argv[1:]
here = os.path.dirname(os.path.abspath(__file__))
FIELD_MS = 1000 / 59.94


def clock(text):
    t = datetime.datetime.strptime(text, "%H:%M:%S.%f")
    return t.hour * 3600 + t.minute * 60 + t.second + t.microsecond / 1e6


def door(path):
    """The door's lines, split into the visit's races (a race begins at its start vote or its match)."""
    races, current, other = [], None, []
    if not os.path.exists(path):
        return races, other
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        name, v = e.get("event"), e.get("values") or {}
        at = clock(e["at"]) if "at" in e else None
        if name == "press" and "vote to start" in v.get("button", ""):
            current = dict(vote=at)
            races.append(current)
        elif name == "match":
            if current is None or "match" in current:
                current = {}
                races.append(current)
            current.update(match=v["match"], at_match=at, **{k: v[k] for k in ("relay", "host", "course", "name", "laps", "seats", "cpu", "seat")})
        elif current is not None and name == "press" and "course vote" in v.get("button", ""):
            current["voted"] = v.get("course")
        elif current is not None and name == "course":
            current["drawn"] = v.get("course")
        elif current is not None and name == "press" and "machine" in v.get("button", ""):
            current["machine"] = v.get("name")
        elif current is not None and name == "game" and v.get("state") == "running":
            current["at_game"] = at
        elif current is not None and name == "live" and "first snapshot" in str(v.get("state")):
            current["at_go"] = at
        elif current is not None and name == "live" and "green light" in str(v.get("state")):
            current["at_green"] = at
        elif current is not None and name == "game" and v.get("state") in ("closed", "never ran"):
            current.update(at_closed=at, standings=v.get("standings"), end=v["state"], last_frame=v.get("lastFrame"))
            current = None
        elif name in ("problem", "failed", "watch") or (name == "status" and "Disconnected" in str(v.get("text"))):
            if v.get("text") or name == "watch":
                other.append((e.get("at"), name, v))
    return races, other


def pictures(folder):
    """One game's race phase: its rollbacks by depth and the pictures lost."""
    rb, pace = f"{folder}/rb.csv", f"{folder}/pace.csv"
    rows = logs.rollback_log(rb)
    if not rows:
        return None
    shown = sorted(int(p[2]) for p in logs.pacing(pace)["P"])
    t0, t1 = int(rows[0]["at_us"]), int(rows[-1]["at_us"])
    gaps = [(b, (b - a) / 1000) for a, b in zip(shown, shown[1:]) if t0 < b <= t1]
    long_gaps = [(t, ms) for t, ms in gaps if ms > 25]
    ends = [t for t, _ in long_gaps]
    by_depth = collections.Counter()      # rollback frames at each depth
    lost_by_depth = collections.Counter()  # of them, followed by a gap with a lost picture
    blamed = set()
    for r in rows:
        d = int(r["depth"])
        if d > 0:
            by_depth[d] += 1
            at = int(r["at_us"])
            k = bisect.bisect_right(ends, at)
            if k < len(ends) and ends[k] - at <= 60000:
                lost_by_depth[d] += 1
                blamed.add(k)
    lost = sum(max(1, round(ms / FIELD_MS) - 1) for _, ms in long_gaps)
    lost_rb = sum(max(1, round(long_gaps[k][1] / FIELD_MS) - 1) for k in blamed)
    depths = [int(r["depth"]) for r in rows if int(r["depth"]) > 0]
    seconds = (t1 - t0) / 1e6
    return dict(frames=len(rows), rollbacks=len(depths), median=statistics.median(depths) if depths else 0,
                deepest=max(depths, default=0), by_depth=by_depth, lost_by_depth=lost_by_depth, pictures=len(gaps),
                gaps=len(long_gaps), lost=lost, lost_rb=lost_rb, gap_max=max((ms for _, ms in gaps), default=0),
                gap99=sorted(ms for _, ms in gaps)[int(len(gaps) * 0.99)] if gaps else 0,
                fps=len(gaps) / seconds if seconds > 0 else 0, catch_up=sum(int(r["catch_up"]) for r in rows))


def game_log(folder):
    path = f"{folder}/runner.log"
    text = open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else ""
    lines = [l.split("fzgx: ")[-1] for l in text.splitlines() if "fzgx" in l]
    rtts = [float(m.group(1)) for l in lines for m in [re.search(r"round trip ([0-9.]+) ms", l)] if m]
    bad = [l for l in lines if re.search(r"desync|differs from the majority|no official inputs|left the race|disconnected", l)]
    # the runner's line for every slow second says how busy the whole PC was: a race beside somebody's build is
    # no pacing measurement
    slow = [l for l in text.splitlines() if l.startswith("[slow]") and "race frame 0 " not in l]
    busy = sum(1 for l in slow for m in [re.search(r"PC (\d+)% busy", l)] if m and int(m.group(1)) >= 90)
    end = next((l for l in reversed(lines) if "stopping" in l or "ended" in l), "(no end line)")
    return dict(rtt=statistics.median(rtts) if rtts else None, rtt_max=max(rtts, default=None), bad=bad, end=end,
                slow=len(slow), busy=busy)


def span(a, b):
    return "-" if a is None or b is None else f"{(b - a) % 86400:.1f} s"


summary = []
for run in RUNS:
    folders = sorted(glob.glob(f"{W}/port/runs/{run}-[0-9]*/"), key=lambda p: int(p.rstrip("/").rsplit("-", 1)[1]))
    visits = []
    for folder in folders:
        races, other = door(folder + "door.jsonl")
        visits.append((folder.rstrip("/"), races, other))
    print(f"== {run}: {len(visits)} launcher(s)")
    matches = []
    for _, races, _ in visits:
        for r in races:
            if r.get("match") and r["match"] not in matches:
                matches.append(r["match"])
    for m in matches:
        in_it = [(i + 1, folder, next(r for r in races if r.get("match") == m), [r.get("match") for r in races].index(m) + 1)
                 for i, (folder, races, _) in enumerate(visits) if any(r.get("match") == m for r in races)]
        first = in_it[0][2]
        print(f"-- match {m}: {first.get('name')} (course {first.get('course')}), {first.get('laps')} lap(s), {first.get('seats')} seats "
              f"({first.get('cpu')} CPU), relay {first.get('relay')} {first.get('host') or '(the coordinator)'}")
        replays, stand, cells = [], [], []
        for i, folder, r, k in in_it:
            p = pictures(f"{folder}/race{k}")
            g = game_log(f"{folder}/race{k}")
            print(f"  launcher {i} (seat {r.get('seat')}, {r.get('machine')}): start vote to match {span(r.get('vote'), r.get('at_match'))}, "
                  f"match to the game running {span(r.get('at_match'), r.get('at_game'))}, to go {span(r.get('at_match'), r.get('at_go'))}, "
                  f"to the green light {span(r.get('at_match'), r.get('at_green'))}; start vote to the green light "
                  f"{span(r.get('vote'), r.get('at_green'))}; the game {r.get('end', 'did not close')} "
                  f"{span(r.get('at_green'), r.get('at_closed'))} after the green light")
            if p:
                depth = ", ".join(f"{d}: {n}" + (f" ({p['lost_by_depth'][d]} lost a picture)" if p['lost_by_depth'][d] else "")
                                  for d, n in sorted(p["by_depth"].items()))
                print(f"    race phase: {p['frames']} displayed frames, {p['pictures']} pictures ({p['fps']:.2f} a second), "
                      f"{p['rollbacks']} rollbacks (median depth {p['median']:.0f}, deepest {p['deepest']}; by depth {{{depth}}}), "
                      f"{p['catch_up']} catch-up steps")
                print(f"    pictures lost: {p['lost']} in {p['gaps']} gaps over 25 ms ({p['lost_rb']} of them after a rollback frame); "
                      f"gaps 99% {p['gap99']:.1f} ms, longest {p['gap_max']:.1f} ms; round trip the game measured: "
                      f"median {g['rtt']} ms, highest {g['rtt_max']} ms")
            if g["slow"]:
                print(f"    slow seconds while racing: {g['slow']}, of them with the whole PC 90% busy or more: {g['busy']}"
                      + ("  ** NOT A PACING MEASUREMENT: the PC was busy with something else **" if g["busy"] >= 5 else ""))
            for l in g["bad"][:4]:
                print(f"    ! {l[:200]}")
            print(f"    end: {g['end'][:140]}")
            found = glob.glob(f"{folder}/replays/*-{m}.fzrp")
            replays += found
            stand.append(r.get("standings"))
            cells.append((i, p, g))
        pair = None
        if replays:
            c = subprocess.run([f"{here}/../replay-compare.py", *replays], capture_output=True, text=True)
            print("  " + (c.stdout.rstrip() or c.stderr.rstrip()).replace("\n", "\n  "))
            pair = re.search(r"(\d+) steps in both; inputs (.*?); checksums (.*?);", c.stdout)
        have = [s for s in stand if s]
        same = len(have) == len(stand) and all(s == have[0] for s in have)
        print(f"  final standings from each launcher's own game: {'the same' if same else 'DIFFERENT or missing'} "
              f"({', '.join(str(len(s)) if s else 'none' for s in stand)} racers; first three {have[0][:3] if have else '-'})")
        summary.append(f"| {run} {m} | {first.get('name')}, {first.get('laps')} lap(s), {first.get('seats')} seats ({first.get('cpu')} CPU) | "
                       f"{len(replays)} | {pair.group(1) + ': inputs ' + pair.group(2) + ', checksums ' + pair.group(3) if pair else '-'} | "
                       + " / ".join(str(p["rollbacks"]) if p else "-" for _, p, _ in cells) + " | "
                       + " / ".join(f"{p['median']:.0f}, {p['deepest']}" if p else "-" for _, p, _ in cells) + " | "
                       + " / ".join((f"{p['lost']} ({p['lost_rb']})" + ("*" if g["busy"] >= 5 else "")) if p else "-" for _, p, g in cells) + " | "
                       + " / ".join(f"{g['rtt']}" for _, _, g in cells) + " | "
                       + f"{span(first.get('vote'), first.get('at_green'))} | {'the same' if same else 'NOT the same'} |")
    for i, (folder, races, other) in enumerate(visits):
        for at, name, v in other:
            text = json.dumps(v)
            print(f"  launcher {i + 1} {at} {name}: {text[:260]}")
    for f in sorted(glob.glob(f"{W}/port/scratch/qp/{run}.server.log")):
        lines = open(f, errors="replace").read().splitlines()
        for l in [l for l in lines if re.search(r"desync|never got ready|went silent|handed|ignored", l)][:8]:
            print(f"  server: {l[:200]}")
print("\n| Run, match | Race | Replays | Steps both recorded | Rollbacks (each game) | Depth: median, deepest | "
      "Pictures lost (after a rollback) | Round trip (ms) | Start vote to green light | Final standings |")
print("|---|---|---|---|---|---|---|---|---|---|")
print("\n".join(summary))
print("\n(*: the PC was 90% busy or more in five or more seconds of that game's race: no pacing measurement.)")
