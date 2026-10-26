#!/usr/bin/env python3
"""smoothing-log.py DUMP.win: the rivals' smoothing log of a game (the image's memmap.SMOOTH_LOG, read from a
`debug.dump` of the data window): how far the offset a rollback's correction is faded out with pointed off the road,
and how far a rival's shadow was from its drawn body.

Every displayed race frame the image logs the machine on the road whose offset had the largest part along its own
up vector, and that part's size: what the image cuts, so the machine is drawn at its true height (smooth.py). On a
frame with a rollback it is the height by which the fresh correction would have lifted or sunk the machine. Printed:
the frames the log holds, those with a rollback, those on which the smoothing started over without an offset (a
frame more than 30 steps after the one before, and until 11 October a frame the time sync held: every rival is
drawn where it is; the race's first frame, which has no frame before it, is not counted), how large the part was on them (the middle, nine in ten, 99 in a
hundred, the largest; in the game's units, a machine being about 10 long), how many were over 1 and over 5, and
the ten largest with their step and seat. Then the same over every frame of the log for the largest distance along
the road between a rival's drawn body and its shadow (sites_shadow.py). Then the effects' counters
(sites_effects.py, at facts.EFFECTS_AT; the whole race, not only the log's frames): how many draws of a rival's
effects were moved with its body, how far each effect would have stood from the body without the move (the
offset) and how far it stands with it (what the move leaves), in classes of size and as the largest, and the draws
by kind. A game run with the tests' bits (the part left in, the shadows left where they were, the effects left
where the game draws them: the drawing as it was) says so in its first line, and its parts are then what was
drawn. Sizes in the log are the upper half of a float: up to 1 in 128 below the true one. Reads a file only."""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "facts", "generated"))
import facts  # noqa: E402

ADVANCED, ROLLBACK, PART_LEFT, SHADOWS_LEFT, EFFECTS_LEFT = 1, 2, 8, 16, 32   # an entry's flags
# The effects' counters, from facts.EFFECTS_AT (sites_effects.py, whose test holds these to its own): words
MOVED, LARGEST_BEFORE, LARGEST_AFTER, LEFT, BEFORE, AFTER, BY_KIND = 0, 4, 8, 12, 16, 80, 144
CLASSES, KINDS = 16, 40


def size(half):
    return struct.unpack(">f", struct.pack(">HH", half, 0))[0]


def spread(name, values):
    values = sorted(values)
    pick = lambda q: values[min(len(values) - 1, int(q * len(values)))]
    return (f"{name}: middle {pick(0.5):.2f}, nine in ten below {pick(0.9):.2f}, 99 in a hundred below {pick(0.99):.2f}, "
            f"largest {values[-1]:.2f}; over 1: {sum(v > 1 for v in values)}, over 5: {sum(v > 5 for v in values)}")


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[1], "rb") as f:
        win = f.read()
    at = facts.SMOOTH_LOG - facts.WINDOW
    frames = int.from_bytes(win[facts.SMOOTH_FRAMES_AT - facts.WINDOW:][:4], "big")
    held = min(frames, facts.SMOOTH_LOG_FRAMES)
    entries = []
    for k in range(frames - held + 1, frames + 1):                    # the log's place is the frame's count
        raw = win[at + 8 * (k % facts.SMOOTH_LOG_FRAMES):][:8]
        step, seat, flags, part, shadow = struct.unpack(">HBBHH", raw)
        entries.append((size(part), step, seat, flags, math.sqrt(max(0.0, size(shadow)))))
    rolled = sorted(e for e in entries if e[3] & ROLLBACK)
    was = [text for bit, text in ((PART_LEFT, "the part off the road left in"), (SHADOWS_LEFT, "the shadows left where they were"),
                                  (EFFECTS_LEFT, "the effects left where the game draws them"))
           if any(e[3] & bit for e in entries)]
    first = 1 if frames <= facts.SMOOTH_LOG_FRAMES else 0             # the race's first frame is in the log
    over = sum(not e[3] & ADVANCED for e in entries[first:])
    print(f"{len(entries)} frames in the log (of {frames} race frames), {len(rolled)} with a rollback, {over} on which "
          f"the smoothing started over" + (" (the drawing as it was: " + ", ".join(was) + ")" if was else ""))
    if rolled:
        print(spread("the part of the correction off the road, on frames with a rollback", [e[0] for e in rolled]))
        print("the ten largest: " + ", ".join(f"{part:.1f} (step {step}, seat {seat})" for part, step, seat, _, _ in rolled[:-11:-1]))
        print(spread("a drawn body to its shadow along the road, every frame", [e[4] for e in entries]))
        far = sorted(entries, key=lambda e: e[4])[:-6:-1]
        print("the five largest: " + ", ".join(f"{shadow:.1f} (step {step})" for _, step, _, _, shadow in far))
    effects(win[facts.EFFECTS_AT - facts.WINDOW:])
    return 0


def bound(k):
    """The lower bound of class k, in units: 0, then 2^(k-7)."""
    return 0.0 if k == 0 else 2.0 ** (k - 7)


def classes(counts):
    named = []
    for k, n in enumerate(counts):
        if n:
            upper = f" to {bound(k + 1):g}" if k + 1 < len(counts) else " up"
            named.append(f"{bound(k):g}{upper}: {n}")
    return ", ".join(named) or "none"


def effects(raw):
    """The effects' counters: printed when any effect of a rival was drawn with an offset."""
    word = lambda at: int.from_bytes(raw[at:at + 4], "big")
    real = lambda at: math.sqrt(max(0.0, struct.unpack(">f", raw[at:at + 4])[0]))
    moved, left = word(MOVED), word(LEFT)
    if not moved + left:
        return
    print(f"a rival's effects drawn while it had an offset: {moved} draws moved with its body, {left} left where the "
          f"game draws them")
    print(f"an effect to its drawn body without the move (the offset), in units: "
          f"{classes([word(BEFORE + 4 * k) for k in range(CLASSES)])}; largest {real(LARGEST_BEFORE):.2f}")
    print(f"an effect to its drawn body as drawn, in units: "
          f"{classes([word(AFTER + 4 * k) for k in range(CLASSES)])}; largest {real(LARGEST_AFTER):.4f}")
    print("draws by kind: " + ", ".join(f"{k}: {word(BY_KIND + 4 * k)}" for k in range(KINDS) if word(BY_KIND + 4 * k)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
