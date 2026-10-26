#!/usr/bin/env python3
"""run-summary.py [--race-before FIELD] RUN [RUN2]: what a run of the port showed, from its probe log
(<work>/port/runs/RUN/probe.csv), in one form for every result table: the address the game's module loaded at, the
field at which each game mode first appears, the race frames reached, the time per field while racing, and the
runtime's shutdown line. With RUN2: the same for it, and the racers' hashes of the two runs compared per race frame
(the harness's gate, `hash_by_step`: the first field that shows each race frame; a shifted start is reported, not
failed).
  --race-before FIELD   the time per field is taken over the race's fields before this field of the run only: a run
              whose script asks for a picture at FIELD measures the game's pace up to there and not its own
              instrument (a screenshot can stall the game a quarter of a second, and the short fields with which
              the emulator catches up afterwards pull the mean down)
  PORT_WORK   the work folder (default: port/setup/work-folder.env's)
  RECOMP_KIT  a recomp-kit checkout whose tools/harness is used (default: this repository's port/gates/vendor/harness)
Reads files only."""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))


# the harness (its gate.py): this repository's copy, or a recomp-kit checkout's (RECOMP_KIT), as port/setup/lib.sh says
harness = (os.path.join(os.environ["RECOMP_KIT"], "tools", "harness") if os.environ.get("RECOMP_KIT")
           else os.path.join(here, "..", "vendor", "harness"))

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402

WORK = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT)
RACE_MODE = "2"   # the probe's mode column while a race is on


def race_fields(rows, before=None):
    """(the race's own fields, each one's time in ms) of a probe's rows; before: only fields below this field.
    A race's own fields: the race-frame counter goes up by one (while a course loads it stands still or holds
    another value), from the countdown on. The time of a field: the host clock from the field before."""
    frame = [int(r["race_frame"]) for r in rows]
    racing = [i for i in range(1, len(rows)) if rows[i]["mode"] == RACE_MODE and frame[i] == frame[i - 1] + 1
              and rows[i - 1]["qpc_us"] and (before is None or i < before)]
    return racing, [(int(rows[i]["qpc_us"]) - int(rows[i - 1]["qpc_us"])) / 1000 for i in racing]


def stood_fields(rows, racing):
    """[(field, its time in ms)] of the fields inside the race's span that are not the race's own: the race frame
    stood or stepped back (a stall, a rollback's frame). The mean, "max" and "over 24 ms" do not hold them."""
    own = set(racing)
    return [(i, (int(rows[i]["qpc_us"]) - int(rows[i - 1]["qpc_us"])) / 1000) for i in range(racing[0], racing[-1] + 1)
            if i not in own and rows[i]["qpc_us"] and rows[i - 1]["qpc_us"]] if racing else []


def race_line(rows, before=None):
    """The summary's line of the time per field while racing, or None when the run has no race field."""
    racing, times = race_fields(rows, before)
    if not times:
        return None
    frames = max(int(rows[i]["race_frame"]) for i in racing)
    stood = stood_fields(rows, racing)
    longest = max(stood, key=lambda field: field[1], default=None)
    return (f"  race: {len(times)} fields from field {racing[0]}, race frame up to {frames}; per field mean {sum(times) / len(times):.3f} ms, "
            f"max {max(times):.1f} ms, over 24 ms: {sum(t > 24 for t in times)}"
            + (f"; not counted: {len(stood)} fields on which the race frame did not go up by one, the longest "
               f"{longest[1]:.1f} ms at field {longest[0]}" if stood else "")
            + (f"; measured before field {before}" if before is not None else ""))


def summary(run, before=None):
    sys.path.insert(0, harness)
    import probelog
    folder = os.path.join(WORK, "port", "runs", run)
    rows = probelog.read(os.path.join(folder, "probe.csv"))
    modes, seen = [], set()
    for i, r in enumerate(rows):
        if r["mode"] not in seen:
            seen.add(r["mode"])
            modes.append(f"{r['mode']}@{i}")
    print(f"{run}: {len(rows)} fields; module {sorted({r['module'] for r in rows if r['module'] != '0'})}; "
          f"modes (first field) {' '.join(modes)}")
    line = race_line(rows, before)
    if line:
        print(line)
    text, shown = "", set()
    for log in ("fzgx.log", "stderr.txt"):   # a launcher run keeps the core's log as fzgx.log (launcher-run.sh)
        try:
            text += open(os.path.join(folder, log), encoding="utf-8", errors="replace").read()
        except OSError:
            pass
    for line in text.splitlines():
        if ("fzgx:" in line[:16] and line not in shown) or "shutdown:" in line:
            shown.add(line)
            print("  " + line[:230])
    return rows


def main(argv):
    before = None
    if argv and argv[0] == "--race-before":
        before, argv = int(argv[1]), argv[2:]
    a = summary(argv[0], before)
    if len(argv) > 1:
        import gate   # (the harness's, found by summary's path)
        b = summary(argv[1], before)
        ok = True
        for column in ("seat0_hash", "racers_hash"):
            result = gate.hash_by_step(a, b, column, "race_frame", 1)
            ok = ok and result["differing"] == 0
            print("  " + result["text"])
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
