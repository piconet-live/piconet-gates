#!/usr/bin/env python3
"""generator-log.py A.win B.win: the race's two generator words in two games of one race, step by step (the image's
memmap.GENERATOR_LOG, read from `debug.dump`s of the two games' data windows at one step).

  A.win, B.win   each game's data window as `debug.dump` wrote it before the same step (pair-run.sh:
                 DEBUG='"dump":{"step":N,"prefix":...}' with a prefix for each game, DEBUG1 and DEBUG2)

After every step the image writes the executable's generator (0x801A63C0) and the effects' (main.rel .data 0x1D628)
into the log, 8 bytes at step & (GENERATOR_LOG_STEPS - 1); a step run again after a rollback writes its entry again.
Compared here: the steps both logs hold that were final in both games when the dumps were taken (below each
game's FINAL_STEPS: run with the official inputs), so no entry of a prediction is read. One line for each word:
steps compared, steps differing, the first. Exit status 0 when both words are equal at every step compared, 1 when
one differs or nothing can be compared. Reads files only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "facts", "generated"))
import facts  # noqa: E402

WORDS = ("the executable's generator", "the effects' generator")


def read(path):
    """A dump's step word, its final steps, and its log as {step: (word, word)} for the steps the log still holds."""
    with open(path, "rb") as f:
        win = f.read()
    word = lambda a: int.from_bytes(win[a - facts.WINDOW:a - facts.WINDOW + 4], "big")
    step, final, steps = word(facts.STEP_AT), word(facts.FINAL_STEPS_AT), facts.GENERATOR_LOG_STEPS
    log = {}
    for s in range(max(0, step - steps), step):
        at = facts.GENERATOR_LOG + 8 * (s & (steps - 1))
        log[s] = (word(at), word(at + 4))
    return step, final, log


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    (step_a, final_a, a), (step_b, final_b, b) = read(argv[1]), read(argv[2])
    print(f"A: before step {step_a}, final below {final_a}; B: before step {step_b}, final below {final_b}")
    steps = sorted(s for s in a if s in b and s < min(final_a, final_b))
    if not steps:
        print("no step is in both logs and final in both games: nothing compared")
        return 1
    worst = 0
    for k, name in enumerate(WORDS):
        differing = [s for s in steps if a[s][k] != b[s][k]]
        first = f", first at step {differing[0]} ({a[differing[0]][k]:08X} and {b[differing[0]][k]:08X})" if differing else ""
        print(f"{name}: steps {steps[0]} to {steps[-1]} compared ({len(steps)}), {len(differing)} differ{first}")
        worst |= bool(differing)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
