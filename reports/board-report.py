#!/usr/bin/env python3
"""board-report.py RUN_FOLDER: the verdict of board-run.sh (protocol/formats.md section 8). Reads the launcher's lines
(RUN/stdout.txt, a JSON object a line: {"event": "board", "values": {...}}) and the game's launch file
(RUN/game-launch.json): the board was taken; the phases reached the countdown and the race; race snapshots arrived;
the game's 12 s stand was judged a freeze (after 10 s) and its end seen; the game's own freeze report came as an
event; the board's last line is there; the launch file names the board and no live feed. Prints what it found and,
last, "board RUN: PASS" or "board RUN: FAIL: why" (exit 1). Reads only."""
import json
import os
import sys


def judge(folder):
    lines = []
    try:
        with open(os.path.join(folder, "stdout.txt"), encoding="utf-8", errors="replace") as f:
            for raw in f:
                try:
                    value = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(value, dict) and value.get("event") == "board":
                    lines.append(value.get("values") or {})
    except OSError:
        return ["no stdout.txt"], {}
    found = {
        "taken": any(v.get("taken") is True for v in lines),
        "phases": [v["phase"] for v in lines if "phase" in v and "frozen" not in v and "ended" not in v],
        "snapshots": [v["snapshot"] for v in lines if "snapshot" in v],
        "frozen": [(v["frozen"], v.get("stood"), v.get("phase")) for v in lines if "frozen" in v],
        "events": [v["kind"] for v in lines if "kind" in v],
        "ended": next((v for v in lines if v.get("ended")), None),
    }
    wrong = []
    if not found["taken"]:
        wrong.append("the board was not taken")
    for phase in ("Countdown", "Racing"):
        if phase not in found["phases"]:
            wrong.append(f"no phase {phase}")
    if len(found["snapshots"]) < 2:
        wrong.append("fewer than two snapshot lines")
    frozen = found["frozen"]
    if not frozen or frozen[0][0] is not True or (frozen[0][1] or 0) < 10:
        wrong.append("the stand was not judged a freeze after 10 s")
    elif not any(f[0] is False for f in frozen[1:]):
        wrong.append("the game moving again was not seen")
    if "Stands" not in found["events"]:
        wrong.append("no Stands event (the game's own freeze report)")
    if not found["ended"]:
        wrong.append("no last line")
    try:
        with open(os.path.join(folder, "game-launch.json"), encoding="utf-8") as f:
            launch = json.load(f)
        if not str(launch.get("board", "")).endswith(".board") or "live" in launch.get("match", {}):
            wrong.append("the launch file names no board, or a live feed")
    except (OSError, ValueError):
        wrong.append("no game-launch.json")
    return wrong, found


def main(args):
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    folder = args[0]
    wrong, found = judge(folder)
    for key, value in found.items():
        print(f"{key}: {value}")
    name = os.path.basename(os.path.normpath(folder))
    print(f"board {name}: " + ("PASS" if not wrong else "FAIL: " + "; ".join(wrong)))
    return 0 if not wrong else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
