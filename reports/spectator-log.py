#!/usr/bin/env python3
"""spectator-log.py DUMP.win RB.csv [--all]: the spectator's log of a game (the image's memmap.SPEC_LOG, read from
a debug.dump of the data window) beside that game's rollback log, a line a displayed frame.

  DUMP.win   the data window as `debug.dump` wrote it late in the race (the port handbook, "Test the camera")
  RB.csv     the same game's rollback log (`debug.rollbackLog`; pair-run.sh writes RUN-2/rb.csv)
  --all      every frame; without it the frames around a change of choice and those where the cameras did not
             hold the choice

A line: the frame's place in the log, the step word after its steps, the rollback's depth on that frame, what the
spectator had chosen (the racer, the mode, the height) and what the game's cameras held: the camera mode
([.bss 0xF68]+0x48: 9 the TV cameras, 0 the chase camera), then with the TV cameras the racer they follow (live
camera +0x6, which the game's task takes from the word the image writes), the type and the variant in use, with the
chase camera its racer, view and state.

"Held": the cameras show what was chosen. With the TV cameras the racer they follow is the racer chosen, and with
a manual shot (modes 2 to 5) the type in use is the mode's and the variant in use the height; with the chase camera
its racer is the one chosen and its view the height plus 1. A choice takes up to SETTLE frames to show (a manual
shot's type is set up in the step of the choice and its height a step later; a type the game picks instead
becomes the mode on the next frame): a frame within SETTLE frames of a change of the choice or of the type in use
counts as settling, any other frame that does not hold is a fault. Then the totals: frames, changes of choice and
the frames between them (a press every N fields must give N), frames with a rollback, changes that fell on one,
frames settling, and the faults.

"Out": the racer the cameras follow is out of the race at the frame's end (the entry's bit; retired or broken
down). The racer asked for stays the player's choice when it goes out (a second bit says it is out): the cameras
are then on another racer and are not held to it. The cameras leave a racer in the step it goes out in, so no frame shows one while anybody still races; such
a frame is a fault too. Exit status 1 when there is a fault or the log is empty. Reads files only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "facts", "generated"))
import facts  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import logs  # noqa: E402  (the one reader of the rollback log)

WINDOW, LOG, ENTRIES, NEXT = facts.WINDOW, facts.SPEC_LOG, facts.SPEC_LOG_ENTRIES, facts.SPEC_LOGGED
MANUAL, CHASE = range(2, 6), 6           # the modes (memmap.SPEC_MODE): the four manual shots, the chase camera
SETTLE = 3                               # frames a choice may take to show


def entries(win):
    word = lambda a, n=4: int.from_bytes(win[a - WINDOW:a - WINDOW + n], "big")
    place = word(NEXT)
    raw = [win[LOG - WINDOW + 8 * i:LOG - WINDOW + 8 * i + 8] for i in range(ENTRIES)]
    full = place < ENTRIES and any(raw[place])        # the log went round: the oldest entry is at the next place
    order = list(range(place, ENTRIES)) + list(range(place)) if full else list(range(min(place, ENTRIES)))
    return [dict(step=int.from_bytes(raw[i][:2], "big"), racer=raw[i][2], mode=raw[i][3] >> 4, camera=raw[i][3] & 15,
                 height=raw[i][4] & 0x3F, out=raw[i][4] >> 7, asked_out=raw[i][4] >> 6 & 1, a=raw[i][5], b=raw[i][6],
                 c=raw[i][7]) for i in order]


def held(e):
    """Do the cameras show what was chosen? The racer asked for only while it races: when it is out (the entry's
    second bit) the cameras are on another, which must be racing (the first bit, a fault of its own)."""
    racer = e["asked_out"] or e["a"] == e["racer"]
    if e["mode"] == CHASE:
        return e["camera"] == 0 and racer and e["b"] == e["height"] + 1
    if e["camera"] != 9:
        return False
    return racer and (e["mode"] not in MANUAL or (e["b"], e["c"]) == (e["mode"] - 2, e["height"]))


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    dump, rollbacks, every = argv[1], argv[2], "--all" in argv[3:]
    with open(dump, "rb") as f:
        log = entries(f.read())
    if not log:
        print("the log is empty: this game never spectated")
        return 1
    rows = logs.rollback_log(rollbacks)
    # a log entry holds the step word after its frame's steps: the next frame's first step in the rollback log
    after = {}
    for row, following in zip(rows, rows[1:]):
        after.setdefault(int(following["step"]) & 0xFFFF, []).append(int(row["depth"]))
    met, changes, moved, lines = {}, [], [], []
    for k, e in enumerate(log):
        depths = after.get(e["step"], [])
        n = met.get(e["step"], 0)
        met[e["step"]] = n + 1
        e["depth"] = depths[min(n, len(depths) - 1)] if depths else -1
        e["held"] = held(e)
        before = log[k - 1] if k else e
        if (e["racer"], e["mode"], e["height"]) != (before["racer"], before["mode"], before["height"]):
            changes.append(k)
        if (e["camera"], e["b"] if e["camera"] == 9 else 0) != (before["camera"], before["b"] if before["camera"] == 9 else 0):
            moved.append(k)                           # the cameras, or the TV cameras' type in use, changed
    settling = {j for k in changes + moved for j in range(k - 1, k + SETTLE)}
    for e in log[:SETTLE]:
        e["held"] = True                              # the log's first frames: the switch to the TV cameras
    near = {j for k in changes for j in range(k - 2, k + 3)}
    for k, e in enumerate(log):
        e["fault"] = not e["held"] and k not in settling
        if every or k in near or not e["held"] or e["out"] or e["asked_out"] != (log[k - 1]["asked_out"] if k else 0):
            mark = "" if e["held"] else "   <-- NOT HELD" if e["fault"] else "   (settling)"
            mark += "   <-- FOLLOWS A RACER WHO IS OUT" if e["out"] else "   (the racer asked for is out)" if e["asked_out"] else ""
            lines.append(f"frame {k:5d} step {e['step']:5d} depth {e['depth']:2d} | chosen: racer {e['racer']:2d} mode "
                         f"{e['mode']} height {e['height']:2d} | game: camera mode {e['camera']}, {e['a']:3d} "
                         f"{e['b']:3d} {e['c']:3d}{mark}")
    print("\n".join(lines))
    gaps = [b - a for a, b in zip(changes, changes[1:])]
    rolled = [e["depth"] > 0 for e in log]
    lost = sum(e["fault"] for e in log)
    unsettled = sum(not e["held"] and not e["fault"] for e in log)
    print(f"{len(log)} frames logged, steps {log[0]['step']} to {log[-1]['step']}; {len(changes)} changes of choice, "
          f"frames between them {({g: gaps.count(g) for g in sorted(set(gaps))})}; frames with a rollback {sum(rolled)} "
          f"(deepest {max(e['depth'] for e in log)}), changes on one {sum(rolled[k] for k in changes)}, changes with "
          f"one in the 17 frames after {sum(any(rolled[k:k + 18]) for k in changes)}; frames with no line in the "
          f"rollback log {sum(e['depth'] < 0 for e in log)}; frames settling after a change: {unsettled}; frames where the "
          f"cameras did not hold the choice: {lost}; frames where they followed a racer who is out: {sum(e['out'] for e in log)}; "
          f"frames with the racer asked for out and the cameras on another: {sum(e['asked_out'] and not e['out'] for e in log)}")
    return 1 if lost or any(e["out"] for e in log) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
