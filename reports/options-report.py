#!/usr/bin/env python3
"""options-report.py RUN: what options-run.sh RUN showed of a player's controller options in an online race.

Reads the two games' recordings (<work>/port/runs/RUN-1 and RUN-2, race.fzrp) and logs (fzgx.log): what each game's
log says of its controller options; the 6-byte control records each game's own seat sent (a record is what the
game's input layer made of the pad with the player's options: byte 1 the steering, 4 the accelerator, 5 the brake);
whether both games recorded the same inputs and the same checksum for every step (replay-compare.py); the two bytes
of each recording's lineup that hold machine 0's control mode and port 1's scheme.
Its last line: "options RUN: PASS" when game 1 kept the stock options, game 2's records are those of its save's
(over the race's first 2,000 steps, which the pad script drives: the accelerator from its B button on at least
1,000 and never the brake, and a wider steering than game 1's from the same stick) and the two recordings are one race of at least 1,000 steps; else FAIL and why. Reads files only."""
import collections
import json
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402
import parts  # noqa: E402
sys.path.insert(0, parts.path_in("REPO_PROTOCOL", "protocol/generated"))   # the replay file's reader (protocol/replay.toml)
import replay_file  # noqa: E402

W = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT)
here = os.path.dirname(os.path.abspath(__file__))
DRIVEN = 2000   # steps of the race the pad script drives in any run (it drives 3,000 fields from about the go)


def recording(path):
    """The recorder's seat, the lineup, and its own seat's record for every step."""
    r = replay_file.read(path)
    json.loads(r.header)
    at = r.seats.index(r.seat) * replay_file.RECORD_SIZE
    return r.seat, r.lineup, [row[at:at + replay_file.RECORD_SIZE] for row, _ in r.steps]


def main(run):
    print(f"== {run}")
    problems, games = [], []
    for i in (1, 2):
        folder = f"{W}/port/runs/{run}-{i}"
        log = open(f"{folder}/fzgx.log", encoding="utf-8", errors="replace").read() if os.path.exists(f"{folder}/fzgx.log") else ""
        said = [line.split("fzgx: ", 1)[1] for line in log.splitlines() if "controller options" in line]
        seat, lineup, records = recording(f"{folder}/race.fzrp")
        steps, records = len(records), records[:DRIVEN]
        pedals = collections.Counter((r[4], r[5]) for r in records)
        steer = collections.Counter(struct.unpack("b", r[1:2])[0] for r in records)
        games.append({"said": said, "accelerating": sum(n for (a, b), n in pedals.items() if a == 100 and b == 0),
                      "braking": sum(n for (a, b), n in pedals.items() if b), "widest": max(map(abs, steer), default=0)})
        print(f"game {i}: seat {seat}, {steps} steps; of the first {len(records)}: accelerator 100 and no brake on "
              f"{games[-1]['accelerating']}, any brake on {games[-1]['braking']}; steering {dict(sorted(steer.items()))}; lineup's control mode "
              f"{lineup[120]}, scheme {lineup[121]}")
        for line in said:
            print(f"  log: {line}")
    one, two = games
    if not any("the player's own" in s for s in one["said"]) or any("written" in s for s in one["said"]):
        problems.append("game 1 (the pristine save) did not keep the stock options")
    if not any("written where the game held others: button settings" in s and "dead zones" in s for s in two["said"]):
        problems.append("game 2's log has no line of its options written")
    if two["accelerating"] < 1000 or two["braking"]:
        problems.append(f"game 2's B button was not its accelerator ({two['accelerating']} steps accelerating, {two['braking']} braking)")
    if one["accelerating"] < 1000 or one["braking"]:
        problems.append(f"game 1's A button was not its accelerator ({one['accelerating']} steps accelerating, {one['braking']} braking)")
    if not two["widest"] > one["widest"] > 0:
        problems.append(f"game 2's smaller dead zone does not show (steering up to {two['widest']}, game 1's up to {one['widest']})")
    compare = subprocess.run([f"{here}/../replay-compare.py"] + [f"{W}/port/runs/{run}-{i}/race.fzrp" for i in (1, 2)],
                             capture_output=True, text=True)
    print(compare.stdout.rstrip() or compare.stderr.rstrip())
    both = re.search(r"(\d+) steps in both", compare.stdout)
    if compare.returncode != 0 or not both or int(both.group(1)) < 1000:
        problems.append("the two recordings are not one race of 1,000 steps or more")
    server = f"{W}/port/scratch/pair/{run}.server.log"
    desyncs = sum("desync" in line for line in open(server, errors="replace")) if os.path.exists(server) else None
    print(f"the test server's desync lines: {'no log' if desyncs is None else desyncs}")
    if desyncs:
        problems.append(f"the test server logged {desyncs} desync line(s)")
    print(f"options {run}: " + ("PASS" if not problems else "FAIL: " + "; ".join(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
