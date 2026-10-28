#!/usr/bin/env python3
"""replay-compare.py [--same-length] A.fzrp B.fzrp [...]: are these replays one race? (the port-recomp notes 5.14)

Each game of a race records its own replay: for every final step the official inputs of the player seats and the
state checksum the game itself computed after that step. Two games stayed in sync exactly when, over the steps both
recorded, every row of inputs and every checksum is the same. Prints, for each file, its seats and steps, and for
each pair the steps compared, the first step whose inputs differ and the first whose checksum differs; a pair of
unequal lengths ends "LENGTHS DIFFER: A and B steps (file N is K short)".
Exit status 0 when every pair is equal over its common steps: a recording cut short is "equal" to a whole one that
way, so a gate that must know both games ran the whole race gives --same-length, with which unequal lengths fail
too (or reads the lengths and asks each game's log why: gate-judge.py). Reads files only; prints no header (a header
holds no token, but nothing of it is needed here). The file is read by the generated reader (protocol/replay.toml,
protocol/generated/replay_file.py). A compact file (version 8) keeps a step's whole checksum only at every 60th step
and the last, and the folded byte (its four bytes XORed) at every step: where either file of a pair has only the
byte, the bytes are compared (the reader's Checksum), so a compact file compares with a whole one or another compact
one at every step. A difference the byte cannot see (1 in 256) shows a step or a few later: a game that differed stays
different, and the next whole checksum is never more than 60 steps on."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "setup"))
import parts  # noqa: E402
sys.path.insert(0, parts.path_in("REPO_PROTOCOL", "protocol/generated"))   # the replay file's reader (protocol/replay.toml)
import replay_file  # noqa: E402


def read(path):
    r = replay_file.read(path)
    if not r.marked or not replay_file.played(r.version):
        sys.exit(f"{path}: not a version {', '.join(map(str, replay_file.VERSIONS + (replay_file.COMPACT_VERSION,)))} replay")
    if r.error:
        sys.exit(f"{path}: a compact replay that does not read: {r.error}")
    if r.header is None:
        sys.exit(f"{path}: ends inside its header")
    header = json.loads(r.header)
    if not r.frames_marked:
        sys.exit(f"{path}: no frames")
    return dict(path=path, header=header, seats=r.seats, seat=r.seat, steps=r.steps,
                results=json.loads(r.results) if r.results is not None else None, whole=r.whole, lineup=r.lineup_part,
                compact=r.compact)


def main(argv):
    strict = "--same-length" in argv
    files = [read(p) for p in argv if p != "--same-length"]
    for f in files:
        setup = f["header"].get("match", {}).get("setup", {})
        print(f"{'/'.join(f['path'].split('/')[-2:])}: seen from seat {f['seat']}, "
              f"{len(f['seats'])} player seats, {len(f['steps'])} steps{'' if f['whole'] else ' (cut inside a step)'}"
              f"{', compact' if f['compact'] else ''}, "
              f"course {setup.get('course')}, {setup.get('laps')} lap(s), engine {f['header'].get('engine', '-')}, "
              f"results {'yes' if f['results'] else 'no'}")
    ok = True
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            a, b = files[i], files[j]
            if a["seats"] != b["seats"]:
                print(f"  files {i + 1} and {j + 1}: other player seats: not one race")
                ok = False
                continue
            n = min(len(a["steps"]), len(b["steps"]))
            rows = next((t for t in range(n) if a["steps"][t][0] != b["steps"][t][0]), None)
            sums = next((t for t in range(n) if a["steps"][t][1] != b["steps"][t][1]), None)
            differing = sum(a["steps"][t][1] != b["steps"][t][1] for t in range(n))
            lineup = "the same lineup" if a["lineup"] == b["lineup"] else "ANOTHER lineup"
            results, length, la, lb = "", "", len(a["steps"]), len(b["steps"])
            if la != lb:
                length = f"; LENGTHS DIFFER: {la} and {lb} steps (file {(i if la < lb else j) + 1} is {abs(la - lb)} short)"
            if a["results"] and b["results"]:
                results = ", the same results" if a["results"] == b["results"] else ", OTHER results"
            print(f"  files {i + 1} and {j + 1}: {n} steps in both; inputs "
                  f"{'equal' if rows is None else f'differ first at step {rows}'}; checksums "
                  f"{'equal at every step' if sums is None else f'differ first at step {sums} ({differing} steps differ)'}; "
                  f"{lineup}{results}{length}")
            ok = ok and rows is None and sums is None and a["lineup"] == b["lineup"] and not (strict and length)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
