#!/usr/bin/env python3
"""pair-report.py RUN [RUN...]: did the two games of pair-run.sh RUN run one race? (the port-recomp notes 5.14)

For each run: the two games' replays compared step by step (replay-compare.py: every final step's inputs and the
checksum each game computed for it), each game's rollbacks and their depths from its rollback log (rb.csv), what
each game's log says of desyncs, lateness and the end, the test server's desync lines, and the pictures' pacing
during the race from each game's pacing log. One table row per run at the end. Reads files only."""
import bisect
import collections
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the pacing log and the rollback log)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402

W = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT)
here = os.path.dirname(os.path.abspath(__file__))
table = []
for run in sys.argv[1:]:
    print(f"== {run}")
    replays = [f"{W}/port/runs/{run}-{i}/race.fzrp" for i in (1, 2)]
    compare = subprocess.run([f"{here}/../replay-compare.py", *replays], capture_output=True, text=True)
    print(compare.stdout.rstrip() or compare.stderr.rstrip())
    pair = re.search(r"(\d+) steps in both; inputs (.*?); checksums (.*?);", compare.stdout)
    games = []
    for i in (1, 2):
        d = f"{W}/port/runs/{run}-{i}"
        log = open(f"{d}/stderr.txt", encoding="utf-8", errors="replace").read() if os.path.exists(f"{d}/stderr.txt") else ""
        lines = [l for l in log.splitlines() if "fzgx" in l]
        session = next((l for l in lines if "network session" in l), "")
        last = next((l for l in reversed(lines) if "rollbacks" in l and "step" in l), "")
        bad = [l for l in lines if re.search(r"desync|differs from the majority|TEST:|no official inputs|left the race", l)]
        end = next((l for l in reversed(lines) if "stopping" in l or "ended" in l), "(no end line: stopped by the test)")
        rows = logs.rollback_log(f"{d}/rb.csv")
        depths = [int(r["depth"]) for r in rows if int(r["depth"]) > 0]
        hist = collections.Counter(depths)
        periods = [(int(b["at_us"]) - int(a["at_us"])) / 1000 for a, b in zip(rows, rows[1:])]
        late = sum(p > 25 for p in periods)
        # the pictures (the pacing log's P records: the present call's start): gaps over 25 ms (a field and a half)
        # during the race phase, and how many rollback frames were followed by one within 60 ms
        shown = sorted(int(p[2]) for p in logs.pacing(f"{d}/pace.csv")["P"]) if rows else []
        t0, t1 = (int(rows[0]["at_us"]), int(rows[-1]["at_us"])) if rows else (0, 0)
        gaps = [(b, (b - a) / 1000) for a, b in zip(shown, shown[1:]) if t0 < b <= t1]
        long_gaps = [t for t, ms in gaps if ms > 25]
        dropped = 0
        for r in rows:
            if int(r["depth"]) > 0:
                at = int(r["at_us"])
                k = bisect.bisect_right(long_gaps, at)
                dropped += k < len(long_gaps) and long_gaps[k] - at <= 60000
        gap99 = sorted(ms for _, ms in gaps)[int(len(gaps) * 0.99)] if gaps else 0
        g = dict(rollbacks=len(depths), frames=len(rows), deepest=max(depths, default=0),
                 median=statistics.median(depths) if depths else 0, late=late, long_gaps=len(long_gaps),
                 dropped=dropped, gap99=gap99, pictures=len(gaps),
                 resim=sum(int(r["extra"]) for r in rows), catch=sum(int(r["catch_up"]) for r in rows))
        games.append(g)
        print(f"  game {i}: {session.split('fzgx: ')[-1]}")
        print(f"    race phase: {g['frames']} displayed frames, {g['rollbacks']} rollbacks (median depth {g['median']:.0f}, "
              f"deepest {g['deepest']}; by depth {dict(sorted(hist.items()))}), {g['resim']} further steps in all "
              f"({g['catch']} of them catch-up), frames more than 25 ms after the one before: {late}")
        print(f"    pictures in the race phase: {g['pictures']}, gaps 99% {g['gap99']:.1f} ms, over 25 ms: {g['long_gaps']}; "
              f"rollback frames followed by such a gap within 60 ms: {g['dropped']} of {g['rollbacks']}")
        print(f"    last report: {last.split('fzgx: ')[-1][:210]}")
        for l in bad[:6]:
            print(f"    ! {l.split('fzgx: ')[-1][:200]}")
        print(f"    end: {end.split('fzgx: ')[-1][:120]}")
    server = f"{W}/port/scratch/pair/{run}.server.log"
    desync = [l for l in open(server, errors="replace").read().splitlines() if "desync" in l] if os.path.exists(server) else []
    for l in desync[:4]:
        print(f"  server: {l[:200]}")
    table.append(f"| {run} | {pair.group(1) if pair else '-'} | {pair.group(2) if pair else '-'} | "
                 f"{pair.group(3) if pair else '-'} | " + " / ".join(str(g["rollbacks"]) for g in games) + " | " +
                 " / ".join(f"{g['median']:.0f}, {g['deepest']}" for g in games) + " | " +
                 " / ".join(f"{g['dropped']} of {g['rollbacks']}" for g in games) + " | " +
                 " / ".join(f"{g['gap99']:.1f}" for g in games) + f" | {len(desync)} |")
print("\n| Run | Steps both recorded | Inputs | Checksums | Rollbacks (game 1 / 2) | Depth: median, deepest | "
      "Rollback frames followed by a picture gap over 25 ms | Picture gaps, 99% (ms) | Desyncs the server reported |")
print("|---|---|---|---|---|---|---|---|---|")
print("\n".join(table))
